from __future__ import annotations

import argparse
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

from qobuz_dl import downloader, qopy
from qobuz_dl.bundle import Bundle
from qobuz_dl.core import QobuzDL

ACTIVATION_ENV = "QOBUZ_DL_LIVE"
ACTIVATION_VALUE = "I_UNDERSTAND_THIS_USES_QOBUZ"

_ROOT = Path(__file__).resolve().parents[1]
_QUALITY_CHOICES = (5, 6, 7, 27)
_PHASES = (
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
_REQUIRED_INPUTS = (
    "QOBUZ_DL_LIVE_EMAIL",
    "QOBUZ_DL_LIVE_PASSWORD",
    "QOBUZ_DL_LIVE_TRACK_ID",
    "QOBUZ_DL_LIVE_SEARCH_QUERY",
    "QOBUZ_DL_LIVE_QUALITY",
    "QOBUZ_DL_LIVE_REPORT",
)
_LIMITS = (
    "one explicitly authorized Qobuz track",
    "temporary config and download destination removed after verification",
    "no Last.fm requests",
    "live execution belongs to issue #48",
)


@dataclass(frozen=True)
class LiveInputs:
    email: str
    password: str
    track_id: str
    search_query: str
    quality: int
    report_path: Path


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
    def __init__(self, phase: str, reason: str) -> None:
        super().__init__(reason)
        self.phase = phase
        self.reason = reason


class _ControlledInterruption(Exception):
    pass


class RealBackend:
    def runtime_facts(self) -> RuntimeFacts:
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


def _read_inputs(environ: Mapping[str, str]) -> LiveInputs:
    missing = [name for name in _REQUIRED_INPUTS if not environ.get(name)]
    if missing:
        raise InputError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    try:
        quality = int(environ["QOBUZ_DL_LIVE_QUALITY"])
    except ValueError:
        raise InputError("QOBUZ_DL_LIVE_QUALITY must be 5, 6, 7, or 27") from None
    if quality not in _QUALITY_CHOICES:
        raise InputError("QOBUZ_DL_LIVE_QUALITY must be 5, 6, 7, or 27")

    query = environ["QOBUZ_DL_LIVE_SEARCH_QUERY"].strip()
    if len(query) < 3:
        raise InputError(
            "QOBUZ_DL_LIVE_SEARCH_QUERY must contain at least 3 characters"
        )

    track_id = environ["QOBUZ_DL_LIVE_TRACK_ID"].strip()
    if not track_id:
        raise InputError("QOBUZ_DL_LIVE_TRACK_ID must not be blank")

    report_path = Path(environ["QOBUZ_DL_LIVE_REPORT"])
    if not report_path.is_absolute():
        raise InputError("QOBUZ_DL_LIVE_REPORT must be an absolute JSON path")
    if report_path.suffix.lower() != ".json":
        raise InputError("QOBUZ_DL_LIVE_REPORT must end in .json")
    if not report_path.parent.is_dir():
        raise InputError("QOBUZ_DL_LIVE_REPORT parent directory must exist")

    return LiveInputs(
        email=environ["QOBUZ_DL_LIVE_EMAIL"],
        password=environ["QOBUZ_DL_LIVE_PASSWORD"],
        track_id=track_id,
        search_query=query,
        quality=quality,
        report_path=report_path,
    )


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
    except Exception:
        raise VerificationFailure(
            "interruption", "interruption_request_failed"
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


def _flac_has_audio_payload(path: Path) -> bool:
    file_size = path.stat().st_size
    with path.open("rb") as stream:
        if stream.read(4) != b"fLaC":
            return False
        offset = 4
        while True:
            header = stream.read(4)
            if len(header) != 4:
                return False
            block_length = int.from_bytes(header[1:4], "big")
            offset += 4 + block_length
            if offset > file_size:
                return False
            stream.seek(block_length, os.SEEK_CUR)
            if header[0] & 0x80:
                return offset < file_size


def _media_quality(path: Path) -> tuple[ObtainedQuality, object]:
    if path.suffix.lower() == ".flac":
        audio = FLAC(path)
        bit_depth = audio.info.bits_per_sample
        sampling_rate = audio.info.sample_rate
        if (
            bit_depth <= 0
            or sampling_rate <= 0
            or audio.info.length <= 0
            or not _flac_has_audio_payload(path)
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
    runtime: RuntimeFacts,
    inputs: LiveInputs,
    obtained: ObtainedQuality | None,
    phases: Mapping[str, str],
    result: str,
    reason: str,
) -> dict:
    return {
        "schema_version": 1,
        "sha": runtime.sha,
        "platform": {
            "system": runtime.system,
            "machine": runtime.machine,
            "python": runtime.python,
        },
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


def _write_report(path: Path, report: Mapping) -> None:
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
    backend,
    *,
    temporary_directory_factory=tempfile.TemporaryDirectory,
) -> VerificationOutcome:
    with _contained_backend_output():
        runtime = backend.runtime_facts()
        phases = {phase: "pending" for phase in _PHASES}
        obtained = None
        current_phase = "bundle"
        result = "failed"
        reason = "unexpected_error"
        temporary_directory = None
        stages_passed = False

        try:
            temporary_directory = temporary_directory_factory(prefix="qobuz-dl-live-")
            workspace = Path(temporary_directory.name)
            config_path = workspace / "config.ini"
            destination = workspace / "downloads"
            interruption_destination = workspace / "interruption"
            destination.mkdir(mode=0o700)
            interruption_destination.mkdir(mode=0o700)

            credentials = backend.bundle_credentials()
            _write_private_config(config_path, inputs, credentials)
            phases["bundle"] = "passed"

            current_phase = "login"
            client = backend.login(config_path)
            phases["login"] = "passed"

            current_phase = "search"
            search_response = client.search_tracks(inputs.search_query, 50)
            authorized_track_count = _authorized_track_count(
                search_response, inputs.track_id
            )
            if authorized_track_count == 0:
                raise VerificationFailure("search", "authorized_track_not_found")
            if authorized_track_count != 1:
                raise VerificationFailure("search", "authorized_track_ambiguous")
            phases["search"] = "passed"

            current_phase = "signed_url"
            signed_response = client.get_track_url(inputs.track_id, inputs.quality)
            signed_url = _signed_media_url(signed_response)
            phases["signed_url"] = "passed"

            current_phase = "interruption"
            _probe_controlled_interruption(
                signed_url,
                interruption_destination,
            )
            phases["interruption"] = "passed"

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
                raise VerificationFailure("download", "download_failed")
            phases["download"] = "passed"

            current_phase = "media"
            final_path = _validated_final_path(download_result, destination)
            try:
                obtained, audio = _media_quality(final_path)
            except VerificationFailure:
                raise
            except Exception:
                raise VerificationFailure("media", "final_media_invalid") from None
            phases["media"] = "passed"

            current_phase = "metadata"
            reference = client.get_track_meta(inputs.track_id)
            expected_metadata = _expected_metadata(reference, inputs.track_id)
            if not _metadata_matches(audio, final_path, expected_metadata):
                raise VerificationFailure("metadata", "metadata_mismatch")
            phases["metadata"] = "passed"
            stages_passed = True
        except VerificationFailure as error:
            current_phase = error.phase
            reason = error.reason
            phases[current_phase] = "failed"
        except KeyboardInterrupt:
            reason = "interrupted"
            phases[current_phase] = "failed"
        except Exception:
            reason = "unexpected_error"
            phases[current_phase] = "failed"
        finally:
            if temporary_directory is not None:
                try:
                    temporary_directory.cleanup()
                except (Exception, KeyboardInterrupt):
                    current_phase = "cleanup"
                    reason = "cleanup_failed"
                    phases["cleanup"] = "failed"
                    stages_passed = False
                else:
                    phases["cleanup"] = "passed"

        if stages_passed and phases["cleanup"] == "passed":
            result = "passed"
            reason = "ok"

        for phase, status in phases.items():
            if status == "pending":
                phases[phase] = "skipped"
        _write_report(
            inputs.report_path,
            _report(runtime, inputs, obtained, phases, result, reason),
        )
        return VerificationOutcome(
            passed=result == "passed",
            phase="complete" if result == "passed" else current_phase,
            reason=reason,
        )


def main(
    argv=None,
    *,
    environ: Mapping[str, str] | None = None,
    backend_factory=RealBackend,
    temporary_directory_factory=tempfile.TemporaryDirectory,
) -> int:
    parser = argparse.ArgumentParser(
        description="Verify one explicitly authorized Qobuz track.",
        epilog=(
            f"Set {ACTIVATION_ENV}={ACTIVATION_VALUE}.\n"
            "Supply these variables through a private environment or secret manager:\n"
            "  QOBUZ_DL_LIVE_EMAIL\n"
            "  QOBUZ_DL_LIVE_PASSWORD\n"
            "  QOBUZ_DL_LIVE_TRACK_ID\n"
            "  QOBUZ_DL_LIVE_SEARCH_QUERY\n"
            "  QOBUZ_DL_LIVE_QUALITY\n"
            "  QOBUZ_DL_LIVE_REPORT\n"
            "Use an absolute .json path for QOBUZ_DL_LIVE_REPORT. "
            "Do not put the password in command arguments."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    if environ.get(ACTIVATION_ENV) != ACTIVATION_VALUE:
        print(
            f"Live Qobuz verification is disabled. Set {ACTIVATION_ENV} to the "
            "documented activation value and run `just live-qobuz`.",
            file=sys.stderr,
        )
        return 2

    try:
        inputs = _read_inputs(environ)
    except InputError as error:
        print(f"Live Qobuz verification input error: {error}", file=sys.stderr)
        return 2

    try:
        with _contained_backend_output():
            backend = backend_factory()
            outcome = verify(
                inputs,
                backend,
                temporary_directory_factory=temporary_directory_factory,
            )
    except (Exception, KeyboardInterrupt):
        print(
            "Live Qobuz verification failed [report:report_write_failed]. "
            "No report was written.",
            file=sys.stderr,
        )
        return 1

    print(
        "Live Qobuz verification "
        + ("passed" if outcome.passed else "failed")
        + f" [{outcome.phase}:{outcome.reason}]. Sanitized report written.",
        file=sys.stderr,
    )
    return 0 if outcome.passed else 1
