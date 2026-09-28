from __future__ import annotations

import configparser
import hashlib
import json
import logging
import os
import platform
import re
import subprocess
import sys
import tempfile
import unicodedata
from collections.abc import Mapping
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from mutagen.flac import FLAC
from mutagen.mp3 import MP3

from qobuz_dl import downloader, http, qopy
from qobuz_dl.bundle import Bundle
from qobuz_dl.console import (
    ExitCode,
    Parser,
    Terminated,
    epilog,
    format_command,
    interruption_exit_code,
    read_secret,
    sigterm_raises,
)
from qobuz_dl.core import QobuzDL

ACTIVATION_ENV = "QOBUZ_DL_LIVE"
ACTIVATION_VALUE = "I_UNDERSTAND_THIS_USES_QOBUZ"
PROG = "live_qobuz.py"
COMMAND = "just live-qobuz"
RETIRED_PASSWORD_ENV = "QOBUZ_DL_LIVE_PASSWORD"

_ROOT = Path(__file__).resolve().parents[1]
_QUALITY_CHOICES = (5, 6, 7, 27)
_PHASES = (
    "runtime",
    "bundle",
    "login",
    "search",
    "signed_url",
    "interruption",
    "download",
    "media",
    "metadata",
    "cleanup",
)
# Each input: (argparse destination, flag, environment fallback). The password
# fallback names a file; the secret itself never travels through a variable.
_INPUTS = (
    ("email", "--email", "QOBUZ_DL_LIVE_EMAIL"),
    ("password_file", "--password-file", "QOBUZ_DL_LIVE_PASSWORD_FILE"),
    ("track_id", "--track-id", "QOBUZ_DL_LIVE_TRACK_ID"),
    ("query", "--query", "QOBUZ_DL_LIVE_SEARCH_QUERY"),
    ("quality", "--quality", "QOBUZ_DL_LIVE_QUALITY"),
    ("output", "--output", "QOBUZ_DL_LIVE_REPORT"),
)
_LIMITS = (
    "one explicitly authorized Qobuz track",
    "temporary config and download destination removed after verification",
    "no Last.fm requests",
    "FLAC checks cover only the initial frame header, STREAMINFO consistency, and remaining bytes",
    "FLAC audio is not decoded and complete-file integrity is not verified",
    "live execution belongs to issue #48",
)
_MAX_FLAC_METADATA_BLOCKS = 128
_MAX_FLAC_FRAME_HEADER_BYTES = 10
_FLAC_SAMPLE_RATES = {
    1: 88200,
    2: 176400,
    3: 192000,
    4: 8000,
    5: 16000,
    6: 22050,
    7: 24000,
    8: 32000,
    9: 44100,
    10: 48000,
    11: 96000,
}
_FLAC_BIT_DEPTHS = {1: 8, 2: 12, 4: 16, 5: 20, 6: 24, 7: 32}


@dataclass(frozen=True)
class LiveInputs:
    email: str
    password: str
    track_id: str
    search_query: str
    quality: int
    report_path: Path | None


@dataclass(frozen=True)
class BundleCredentials:
    app_id: str
    secrets: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeFacts:
    sha: str
    system: str
    machine: str
    python: str


@dataclass(frozen=True)
class ObtainedQuality:
    format: str
    bit_depth: int | None
    sampling_rate: int
    bitrate_kbps: int | None


@dataclass(frozen=True)
class VerificationOutcome:
    passed: bool
    phase: str
    reason: str
    # A failure caused only by a temporary condition, such as a timeout.
    retryable: bool = False
    # Set when SIGINT or SIGTERM arrived, whatever else went wrong.
    interruption: ExitCode | None = None


@dataclass(frozen=True)
class ExpectedMetadata:
    title: str
    artist: str
    album: str
    track_number: int
    album_tracks_count: int | None


class InputError(Exception):
    pass


class VerificationFailure(Exception):
    def __init__(self, phase: str, reason: str, *, retryable: bool = False) -> None:
        super().__init__(reason)
        self.phase = phase
        self.reason = reason
        self.retryable = retryable


class _ControlledInterruption(Exception):
    pass


class _ReportWriteFailure(Exception):
    def __init__(self, interruption: ExitCode | None = None) -> None:
        super().__init__("report_write_failed")
        self.interruption = interruption


class RealBackend:
    def runtime_facts(self) -> RuntimeFacts:
        top_level = subprocess.run(
            ("git", "rev-parse", "--show-toplevel"),
            cwd=_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not top_level or Path(top_level).resolve() != _ROOT.resolve():
            raise ValueError("verifier root is not the Git top-level")
        completed = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        sha = completed.stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("git did not return a full commit SHA")
        return RuntimeFacts(
            sha=sha,
            system=platform.system(),
            machine=platform.machine(),
            python=platform.python_version(),
        )

    def bundle_credentials(self) -> BundleCredentials:
        bundle = Bundle()
        return BundleCredentials(
            app_id=str(bundle.get_app_id()),
            secrets=tuple(bundle.get_secrets().values()),
        )

    def login(self, config_path: Path):
        config = configparser.ConfigParser(interpolation=None)
        with config_path.open(encoding="utf-8") as stream:
            config.read_file(stream)
        values = config[config.default_section]
        return qopy.Client(
            values["email"],
            values["password"],
            values["app_id"],
            tuple(secret for secret in values["secrets"].split(",") if secret),
            secret_test_track_id=values["track_id"],
        )

    def download_track(self, client, track_id: str, destination: Path, quality: int):
        qobuz = QobuzDL(
            directory=str(destination),
            quality=quality,
            embed_art=False,
            quality_fallback=True,
            no_cover=True,
            downloads_db=None,
        )
        qobuz.client = client
        return qobuz.download_from_id(track_id, album=False)


def _read_inputs(environ: Mapping[str, str], arguments, stdin) -> LiveInputs:
    values = {}
    for destination, _flag, name in _INPUTS:
        value = getattr(arguments, destination)
        values[destination] = value if value is not None else environ.get(name)
    if not values["password_file"] and environ.get(RETIRED_PASSWORD_ENV):
        raise InputError(
            f"{RETIRED_PASSWORD_ENV} is no longer read; put the password on the "
            "first line of a private file and pass --password-file PATH, or pipe "
            "it with --password-file -"
        )
    missing = [
        f"{flag} (or {name})"
        for destination, flag, name in _INPUTS
        if not values[destination]
    ]
    if missing:
        raise InputError("missing required inputs: " + ", ".join(missing))

    try:
        quality = int(values["quality"])
    except ValueError:
        raise InputError("--quality must be 5, 6, 7, or 27") from None
    if quality not in _QUALITY_CHOICES:
        raise InputError("--quality must be 5, 6, 7, or 27")

    query = values["query"].strip()
    if len(query) < 3:
        raise InputError("--query must contain at least 3 characters")

    track_id = values["track_id"].strip()
    if not track_id:
        raise InputError("--track-id must not be blank")

    report_path = None
    if values["output"] != "-":
        report_path = Path(values["output"])
        if not report_path.is_absolute():
            raise InputError("--output must be an absolute .json path, or -")
        if report_path.suffix.lower() != ".json":
            raise InputError("--output must end in .json")
        if not report_path.parent.is_dir():
            raise InputError("--output parent directory must exist")

    return LiveInputs(
        email=values["email"],
        password=_read_password(values["password_file"], stdin),
        track_id=track_id,
        search_query=query,
        quality=quality,
        report_path=report_path,
    )


def _read_password(source: str, stdin) -> str:
    try:
        return read_secret(source, stdin)
    except (OSError, UnicodeError):
        raise InputError("--password-file could not be read") from None
    except ValueError:
        raise InputError(
            "--password-file must hold the password on its first line"
        ) from None


def _write_private_config(
    path: Path,
    inputs: LiveInputs,
    credentials: BundleCredentials,
) -> None:
    if not credentials.app_id or not credentials.secrets:
        raise VerificationFailure("bundle", "bundle_credentials_invalid")
    if any(not secret for secret in credentials.secrets):
        raise VerificationFailure("bundle", "bundle_credentials_invalid")

    config = configparser.ConfigParser(interpolation=None)
    config[config.default_section] = {
        "email": inputs.email,
        "password": hashlib.md5(
            inputs.password.encode("utf-8"), usedforsecurity=False
        ).hexdigest(),
        "app_id": credentials.app_id,
        "secrets": ",".join(credentials.secrets),
        "track_id": inputs.track_id,
    }
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        config.write(stream)
        stream.flush()
        os.fsync(stream.fileno())


def _authorized_track_count(response, track_id: str) -> int:
    try:
        items = response["tracks"]["items"]
    except (KeyError, TypeError):
        raise VerificationFailure("search", "search_response_invalid") from None
    if not isinstance(items, list):
        raise VerificationFailure("search", "search_response_invalid")
    return sum(
        1
        for item in items
        if isinstance(item, Mapping) and str(item.get("id")) == track_id
    )


def _signed_media_url(response) -> str:
    if not isinstance(response, Mapping):
        raise VerificationFailure("signed_url", "signed_media_invalid")
    if "sample" in response:
        raise VerificationFailure("signed_url", "authorized_track_is_sample")

    url = response.get("url")
    if not isinstance(url, str) or not url:
        raise VerificationFailure("signed_url", "signed_media_invalid")
    return url


def _probe_controlled_interruption(url: str, destination: Path):
    target = destination / ".qdl-interruption.tmp"
    received = 0

    def stop_after_first_bytes(size, downloaded, total):
        nonlocal received
        received = downloaded
        if size > 0 and downloaded > 0:
            raise _ControlledInterruption

    try:
        downloader.download_with_progress(
            url,
            target,
            target.name,
            after_write=stop_after_first_bytes,
        )
    except _ControlledInterruption:
        pass
    except KeyboardInterrupt:
        raise
    except Exception as error:
        raise VerificationFailure(
            "interruption",
            "interruption_request_failed",
            retryable=http.is_retryable(error),
        ) from None

    if received <= 0:
        raise VerificationFailure("interruption", "interruption_not_observed")
    if tuple(destination.iterdir()):
        raise VerificationFailure("interruption", "interruption_cleanup_failed")


def _validated_final_path(result, destination: Path) -> Path:
    if result.state != "finalized" or result.reason != "downloaded":
        raise VerificationFailure("download", "download_failed")
    if len(result.finalized_paths) != 1:
        raise VerificationFailure("download", "download_result_invalid")

    final_path = Path(result.finalized_paths[0]).resolve()
    destination = destination.resolve()
    try:
        final_path.relative_to(destination)
    except ValueError:
        raise VerificationFailure("media", "final_media_outside_destination") from None
    if not final_path.is_file() or final_path.stat().st_size <= 0:
        raise VerificationFailure("media", "final_media_missing")
    return final_path


def _flac_frame_offset(path: Path) -> tuple[int, int]:
    file_size = path.stat().st_size
    with path.open("rb") as stream:
        if stream.read(4) != b"fLaC":
            raise ValueError
        offset = 4
        for block_index in range(_MAX_FLAC_METADATA_BLOCKS):
            header = stream.read(4)
            if len(header) != 4:
                raise ValueError
            block_type = header[0] & 0x7F
            block_length = int.from_bytes(header[1:4], "big")
            if block_type == 127:
                raise ValueError
            if block_index == 0 and (block_type != 0 or block_length != 34):
                raise ValueError
            if block_index > 0 and block_type == 0:
                raise ValueError
            offset += 4 + block_length
            if offset > file_size:
                raise ValueError
            stream.seek(block_length, os.SEEK_CUR)
            if header[0] & 0x80:
                return offset, file_size
    raise ValueError


def _flac_crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def _read_flac_uint(data: bytes, offset: int, length: int) -> tuple[int, int]:
    end = offset + length
    if end > len(data):
        raise ValueError
    return int.from_bytes(data[offset:end], "big"), end


def _flac_block_size(code: int, data: bytes, offset: int) -> tuple[int, int]:
    if code == 0:
        raise ValueError
    if code == 1:
        return 192, offset
    if 2 <= code <= 5:
        return 576 << (code - 2), offset
    if code == 6:
        stored, offset = _read_flac_uint(data, offset, 1)
        return stored + 1, offset
    if code == 7:
        stored, offset = _read_flac_uint(data, offset, 2)
        if stored == 0xFFFF:
            raise ValueError
        return stored + 1, offset
    return 256 << (code - 8), offset


def _flac_sample_rate(
    code: int, data: bytes, offset: int, stream_rate: int
) -> tuple[int, int]:
    if code == 0:
        return stream_rate, offset
    if code in _FLAC_SAMPLE_RATES:
        return _FLAC_SAMPLE_RATES[code], offset
    if code == 15:
        raise ValueError
    length = 1 if code == 12 else 2
    stored, offset = _read_flac_uint(data, offset, length)
    if stored == 0:
        raise ValueError
    if code == 12:
        return stored * 1000, offset
    if code == 14:
        return stored * 10, offset
    return stored, offset


def _flac_frame_header_valid(path: Path, stream_info) -> bool:
    try:
        frame_offset, file_size = _flac_frame_offset(path)
        remaining = file_size - frame_offset
        with path.open("rb") as stream:
            stream.seek(frame_offset)
            data = stream.read(min(remaining, _MAX_FLAC_FRAME_HEADER_BYTES))

        if len(data) < 4 or data[0] != 0xFF or (data[1] & 0xFE) != 0xF8:
            raise ValueError
        block_size_code = data[2] >> 4
        sample_rate_code = data[2] & 0x0F
        channel_code = data[3] >> 4
        bit_depth_code = (data[3] >> 1) & 0x07
        if data[3] & 0x01 or channel_code > 10 or bit_depth_code == 3:
            raise ValueError

        if len(data) < 5 or data[4] != 0:
            raise ValueError
        block_size, offset = _flac_block_size(block_size_code, data, 5)
        if block_size > stream_info.max_blocksize or (
            stream_info.total_samples > 0 and block_size > stream_info.total_samples
        ):
            raise ValueError
        sample_rate, offset = _flac_sample_rate(
            sample_rate_code, data, offset, stream_info.sample_rate
        )
        channel_count = channel_code + 1 if channel_code <= 7 else 2
        bit_depth = (
            stream_info.bits_per_sample
            if bit_depth_code == 0
            else _FLAC_BIT_DEPTHS[bit_depth_code]
        )
        if (
            sample_rate != stream_info.sample_rate
            or channel_count != stream_info.channels
            or bit_depth != stream_info.bits_per_sample
        ):
            raise ValueError

        stored_crc, crc_offset = _read_flac_uint(data, offset, 1)
        if stored_crc != _flac_crc8(data[:offset]):
            raise ValueError
        return file_size - (frame_offset + crc_offset) >= 3
    except (KeyError, OSError, ValueError):
        return False


def _media_quality(path: Path) -> tuple[ObtainedQuality, object]:
    if path.suffix.lower() == ".flac":
        audio = FLAC(path)
        bit_depth = audio.info.bits_per_sample
        sampling_rate = audio.info.sample_rate
        if (
            bit_depth <= 0
            or sampling_rate <= 0
            or audio.info.length <= 0
            or not _flac_frame_header_valid(path, audio.info)
        ):
            raise VerificationFailure("media", "final_media_invalid")
        return (
            ObtainedQuality(
                format="FLAC",
                bit_depth=bit_depth,
                sampling_rate=sampling_rate,
                bitrate_kbps=None,
            ),
            audio,
        )
    if path.suffix.lower() == ".mp3":
        audio = MP3(path)
        bitrate = audio.info.bitrate
        sampling_rate = audio.info.sample_rate
        if bitrate <= 0 or sampling_rate <= 0 or audio.info.length <= 0:
            raise VerificationFailure("media", "final_media_invalid")
        return (
            ObtainedQuality(
                format="MP3",
                bit_depth=None,
                sampling_rate=sampling_rate,
                bitrate_kbps=round(bitrate / 1000),
            ),
            audio,
        )
    raise VerificationFailure("media", "final_media_invalid")


def _positive_decimal(value) -> int:
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        number = int(value)
    else:
        raise ValueError
    if number <= 0:
        raise ValueError
    return number


def _expected_metadata(response, authorized_track_id: str) -> ExpectedMetadata:
    try:
        if not isinstance(response, Mapping):
            raise ValueError
        response_id = response["id"]
        if isinstance(response_id, bool) or str(response_id) != authorized_track_id:
            raise ValueError

        title = response["title"]
        if not isinstance(title, str) or not title:
            raise ValueError
        version = response.get("version")
        if version:
            if not isinstance(version, str):
                raise ValueError
            title = f"{title} ({version})"
        work = response.get("work")
        if work:
            if not isinstance(work, str):
                raise ValueError
            title = f"{work}: {title}"

        album = response["album"]
        if not isinstance(album, Mapping):
            raise ValueError
        album_title = album["title"]
        album_artist = album["artist"]
        if (
            not isinstance(album_title, str)
            or not album_title
            or not isinstance(album_artist, Mapping)
        ):
            raise ValueError
        album_artist_name = album_artist["name"]
        if not isinstance(album_artist_name, str) or not album_artist_name:
            raise ValueError

        performer = response.get("performer")
        if performer is not None and not isinstance(performer, Mapping):
            raise ValueError
        performer_name = performer.get("name") if performer is not None else None
        if performer_name is not None and not isinstance(performer_name, str):
            raise ValueError
        artist = performer_name or album_artist_name

        track_number = _positive_decimal(response["track_number"])
        tracks_count_value = album.get("tracks_count")
        album_tracks_count = (
            _positive_decimal(tracks_count_value)
            if tracks_count_value is not None
            else None
        )
    except (KeyError, TypeError, ValueError):
        raise VerificationFailure("metadata", "metadata_reference_invalid") from None

    return ExpectedMetadata(
        title=unicodedata.normalize("NFC", title),
        artist=unicodedata.normalize("NFC", artist),
        album=unicodedata.normalize("NFC", album_title),
        track_number=track_number,
        album_tracks_count=album_tracks_count,
    )


def _single_metadata_text(value) -> str:
    values = value.text if hasattr(value, "text") else value
    if (
        not isinstance(values, (list, tuple))
        or len(values) != 1
        or not isinstance(values[0], str)
        or not values[0]
    ):
        raise ValueError
    return unicodedata.normalize("NFC", values[0])


def _track_number_matches(value: str, expected: ExpectedMetadata) -> bool:
    match = re.fullmatch(r"([0-9]+)(?:/([0-9]+))?", value)
    if not match:
        return False
    try:
        numerator = _positive_decimal(match.group(1))
        denominator = (
            _positive_decimal(match.group(2)) if match.group(2) is not None else None
        )
    except ValueError:
        return False
    if numerator != expected.track_number:
        return False
    return denominator is None or (
        expected.album_tracks_count is not None
        and denominator == expected.album_tracks_count
    )


def _metadata_matches(audio, path: Path, expected: ExpectedMetadata) -> bool:
    if path.suffix.lower() == ".flac":
        values = {
            "title": audio.get("TITLE"),
            "artist": audio.get("ARTIST"),
            "album": audio.get("ALBUM"),
            "track": audio.get("TRACKNUMBER"),
        }
    else:
        tags = audio.tags
        if tags is None:
            return False
        values = {
            "title": tags.get("TIT2"),
            "artist": tags.get("TPE1"),
            "album": tags.get("TALB"),
            "track": tags.get("TRCK"),
        }
    try:
        observed = {
            name: _single_metadata_text(value) for name, value in values.items()
        }
    except (TypeError, ValueError):
        return False
    return (
        observed["title"] == expected.title
        and observed["artist"] == expected.artist
        and observed["album"] == expected.album
        and _track_number_matches(observed["track"], expected)
    )


def _report(
    runtime: RuntimeFacts | None,
    inputs: LiveInputs,
    obtained: ObtainedQuality | None,
    phases: Mapping[str, str],
    result: str,
    reason: str,
) -> dict:
    return {
        "schema_version": 1,
        "sha": None if runtime is None else runtime.sha,
        "platform": (
            None
            if runtime is None
            else {
                "system": runtime.system,
                "machine": runtime.machine,
                "python": runtime.python,
            }
        ),
        "quality": {
            "requested": inputs.quality,
            "obtained": (
                {
                    "format": obtained.format,
                    "bit_depth": obtained.bit_depth,
                    "sampling_rate": obtained.sampling_rate,
                    "bitrate_kbps": obtained.bitrate_kbps,
                }
                if obtained is not None
                else None
            ),
        },
        "result": result,
        "reason": reason,
        "phases": dict(phases),
        "limits": list(_LIMITS),
    }


def _write_report(path: Path | None, report: Mapping) -> None:
    if path is None:
        sys.stdout.write(json.dumps(report, ensure_ascii=True, indent=2) + "\n")
        sys.stdout.flush()
        return
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.chmod(temporary_path, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def _contained_backend_output():
    sink = StringIO()
    previous_logging_disable = logging.root.manager.disable
    logging.disable(sys.maxsize)
    try:
        with redirect_stdout(sink), redirect_stderr(sink):
            yield
    finally:
        logging.disable(previous_logging_disable)


def verify(
    inputs: LiveInputs,
    backend_factory,
    *,
    temporary_directory_factory=tempfile.TemporaryDirectory,
    progress=None,
) -> VerificationOutcome:
    phases = {phase: "pending" for phase in _PHASES}
    runtime: RuntimeFacts | None = None
    obtained = None
    current_phase = "runtime"
    result = "failed"
    reason = "unexpected_error"
    retryable = False
    interruption: ExitCode | None = None
    temporary_directory = None
    stages_passed = False

    def passed(phase):
        phases[phase] = "passed"
        if progress is not None:
            progress(phase)

    with _contained_backend_output():
        try:
            backend = backend_factory()
            runtime = backend.runtime_facts()
            passed("runtime")

            current_phase = "bundle"
            temporary_directory = temporary_directory_factory(prefix="qobuz-dl-live-")
            workspace = Path(temporary_directory.name)
            config_path = workspace / "config.ini"
            destination = workspace / "downloads"
            interruption_destination = workspace / "interruption"
            destination.mkdir(mode=0o700)
            interruption_destination.mkdir(mode=0o700)

            credentials = backend.bundle_credentials()
            _write_private_config(config_path, inputs, credentials)
            passed("bundle")

            current_phase = "login"
            client = backend.login(config_path)
            passed("login")

            current_phase = "search"
            search_response = client.search_tracks(inputs.search_query, 50)
            authorized_track_count = _authorized_track_count(
                search_response, inputs.track_id
            )
            if authorized_track_count == 0:
                raise VerificationFailure("search", "authorized_track_not_found")
            if authorized_track_count != 1:
                raise VerificationFailure("search", "authorized_track_ambiguous")
            passed("search")

            current_phase = "signed_url"
            signed_response = client.get_track_url(inputs.track_id, inputs.quality)
            signed_url = _signed_media_url(signed_response)
            passed("signed_url")

            current_phase = "interruption"
            _probe_controlled_interruption(
                signed_url,
                interruption_destination,
            )
            passed("interruption")

            current_phase = "download"
            download_result = backend.download_track(
                client,
                inputs.track_id,
                destination,
                inputs.quality,
            )
            if (
                download_result.state != "finalized"
                or download_result.reason != "downloaded"
            ):
                raise VerificationFailure(
                    "download",
                    "download_failed",
                    retryable=download_result.retryable,
                )
            passed("download")

            current_phase = "media"
            final_path = _validated_final_path(download_result, destination)
            try:
                obtained, audio = _media_quality(final_path)
            except VerificationFailure:
                raise
            except Exception:
                raise VerificationFailure("media", "final_media_invalid") from None
            passed("media")

            current_phase = "metadata"
            reference = client.get_track_meta(inputs.track_id)
            expected_metadata = _expected_metadata(reference, inputs.track_id)
            if not _metadata_matches(audio, final_path, expected_metadata):
                raise VerificationFailure("metadata", "metadata_mismatch")
            passed("metadata")
            stages_passed = True
        except VerificationFailure as error:
            if current_phase == "runtime":
                reason = "runtime_unavailable"
            else:
                current_phase = error.phase
                reason = error.reason
                retryable = error.retryable
            phases[current_phase] = "failed"
        except KeyboardInterrupt as error:
            interruption = interruption_exit_code(error)
            reason = "terminated" if isinstance(error, Terminated) else "interrupted"
            phases[current_phase] = "failed"
        except Exception as error:
            if current_phase == "runtime":
                reason = "runtime_unavailable"
            else:
                reason = "unexpected_error"
                retryable = http.is_retryable(error)
            phases[current_phase] = "failed"
        finally:
            if temporary_directory is not None:
                try:
                    temporary_directory.cleanup()
                except (Exception, KeyboardInterrupt) as error:
                    if isinstance(error, KeyboardInterrupt) and interruption is None:
                        interruption = interruption_exit_code(error)
                    current_phase = "cleanup"
                    reason = "cleanup_failed"
                    retryable = False
                    phases["cleanup"] = "failed"
                    stages_passed = False
                else:
                    passed("cleanup")

        if stages_passed and phases["cleanup"] == "passed":
            result = "passed"
            reason = "ok"

        for phase, status in phases.items():
            if status == "pending":
                phases[phase] = "skipped"
        report = _report(runtime, inputs, obtained, phases, result, reason)
        outcome = VerificationOutcome(
            passed=result == "passed",
            phase="complete" if result == "passed" else current_phase,
            reason=reason,
            retryable=retryable and interruption is None,
            interruption=interruption,
        )

    try:
        _write_report(inputs.report_path, report)
    except KeyboardInterrupt as error:
        raise _ReportWriteFailure(
            outcome.interruption or interruption_exit_code(error)
        ) from None
    except Exception:
        raise _ReportWriteFailure(outcome.interruption) from None
    return outcome


def build_parser() -> Parser:
    parser = Parser(
        prog=PROG,
        command=COMMAND,
        description=(
            "Verify one explicitly authorized Qobuz track against the live "
            "service: bundle, login, search, signed URL, interrupted and "
            "complete downloads, media, metadata, and cleanup. Writes a "
            "sanitized JSON report and prints its path on stdout."
        ),
        epilog=epilog(
            (
                "pass show qobuz | just live-qobuz --password-file - "
                "--output /tmp/live.json",
                "just live-qobuz --password-file ~/.qobuz-password --output - "
                "| jq .result",
                "QOBUZ_DL_LIVE_TRACK_ID=123 just live-qobuz --verbose",
            ),
            {
                ExitCode.OK: "verification passed; report written",
                ExitCode.FAILURE: "verification failed; report written unless "
                "stderr says otherwise",
                ExitCode.USAGE: "verification disabled, or an input is missing "
                "or invalid",
                ExitCode.INTERRUPTED: "interrupted (SIGINT)",
                ExitCode.TERMINATED: "terminated (SIGTERM)",
            },
            notes=(
                f"Requires {ACTIVATION_ENV}={ACTIVATION_VALUE}.",
                "Each input flag falls back to an environment variable:",
                *(f"  {flag:<16} {name}" for _dest, flag, name in _INPUTS),
                f"{RETIRED_PASSWORD_ENV} is retired: it would put the secret in",
                "the environment. Never pass the password as an argument.",
            ),
        ),
    )
    parser.add_argument("--email", help="Qobuz account email")
    parser.add_argument(
        "--password-file",
        metavar="PATH",
        help="file whose first line is the account password, or - to read stdin",
    )
    parser.add_argument("--track-id", metavar="ID", help="authorized Qobuz track ID")
    parser.add_argument(
        "--query",
        metavar="TEXT",
        help="search text that finds exactly one copy of the authorized track",
    )
    parser.add_argument(
        "--quality",
        metavar="QUALITY",
        help="requested quality: 5, 6, 7, or 27",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="absolute .json path for the sanitized report, or - for stdout",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="report each passed phase on stderr",
    )
    return parser


# Inputs that identify the account or the track; a hint never repeats them.
_PRIVATE_FLAGS = ("--email", "--track-id", "--query")


def _join_flags(flags) -> str:
    if len(flags) <= 2:
        return " and ".join(flags)
    return ", ".join(flags[:-1]) + f", and {flags[-1]}"


def _rerun_line(argv, label="rerun") -> str:
    """The command to run next, with --verbose and without private input values.

    Flags whose values were dropped are named, so the reader supplies them
    again; inputs from the environment need nothing.
    """
    kept, dropped = [], []
    arguments = iter(argv)
    for argument in arguments:
        name = argument.split("=", 1)[0]
        if argument in ("-v", "--verbose"):
            continue
        if name in _PRIVATE_FLAGS:
            if name not in dropped:
                dropped.append(name)
            if "=" not in argument:
                next(arguments, None)
            continue
        kept.append(argument)
    command = format_command((*COMMAND.split(), "--verbose", *kept))
    if not dropped:
        return f"{label}: {command}"
    return f"{label} with the same {_join_flags(dropped)}: {command}"


def main(
    argv=None,
    *,
    environ: Mapping[str, str] | None = None,
    backend_factory=RealBackend,
    temporary_directory_factory=tempfile.TemporaryDirectory,
    stdin=None,
) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    arguments = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    # Bound before the backend redirects sys.stderr into its sink.
    stderr = sys.stderr
    if environ.get(ACTIVATION_ENV) != ACTIVATION_VALUE:
        return parser.usage_error(
            "live Qobuz verification is disabled; set "
            f"{ACTIVATION_ENV}={ACTIVATION_VALUE} to run it"
        )

    def report_progress(phase):
        print(f"{PROG}: {phase} passed", file=stderr, flush=True)

    try:
        with sigterm_raises():
            try:
                inputs = _read_inputs(
                    environ, arguments, sys.stdin if stdin is None else stdin
                )
            except InputError as error:
                return parser.usage_error(str(error))
            outcome = verify(
                inputs,
                backend_factory,
                temporary_directory_factory=temporary_directory_factory,
                progress=report_progress if arguments.verbose else None,
            )
    except _ReportWriteFailure as failure:
        if failure.interruption is not None:
            print(
                f"{PROG}: interrupted [report:report_write_failed]; "
                "no report was written",
                file=stderr,
            )
            return failure.interruption
        print(
            f"{PROG}: verification failed [report:report_write_failed]; "
            f"no report was written\n{_rerun_line(argv)}",
            file=stderr,
        )
        return ExitCode.FAILURE
    except KeyboardInterrupt as interruption:
        print(f"{PROG}: interrupted; no report was written", file=stderr)
        return interruption_exit_code(interruption)
    except Exception:
        print(
            f"{PROG}: verification failed [complete:unexpected_error]; "
            f"no report was written\n{_rerun_line(argv)}",
            file=stderr,
        )
        return ExitCode.FAILURE

    if inputs.report_path is not None:
        print(inputs.report_path)
    status = f"[{outcome.phase}:{outcome.reason}]"
    if outcome.interruption is not None:
        print(f"{PROG}: interrupted {status}; sanitized report written", file=stderr)
        return outcome.interruption
    if outcome.passed:
        if arguments.verbose:
            print(
                f"{PROG}: verification passed {status}; sanitized report written",
                file=stderr,
            )
        return ExitCode.OK
    print(
        f"{PROG}: verification failed {status}; sanitized report written\n"
        f"{_rerun_line(argv)}",
        file=stderr,
    )
    return ExitCode.FAILURE
