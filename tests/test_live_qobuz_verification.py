import base64
import hashlib
import json
import logging
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TALB, TIT2, TPE1, TRCK

from qobuz_dl import db, downloader, live_verification, metadata
from qobuz_dl.downloader import DownloadResult
from qobuz_dl.live_verification import (
    ACTIVATION_ENV,
    ACTIVATION_VALUE,
    BundleCredentials,
    RealBackend,
    RuntimeFacts,
    _flac_frame_offset,
    main,
)

SENTINEL = "raw-secret-sentinel"
AUTHORIZED_TRACK_ID = "123456"
SIGNED_URL = "https://media.example.test/authorized.mp3?token=do-not-publish"
PLAYABLE_FLAC = base64.b64decode(
    "ZkxhQwAAACIAoACgAAAAAAFVAfQA8AAAAKAAAAAAAAAAAAAAAAAAAAAAhAAALAwAAABM"
    "YXZmNjMuMS4xMDEBAAAAFAAAAGVuY29kZXI9TGF2ZjYzLjEuMTAx//hkCACfNwAAAEEt"
)
PLAYABLE_FLAC_METADATA = PLAYABLE_FLAC[:-12]
PLAYABLE_FLAC_FRAME = PLAYABLE_FLAC[-12:]
PLAYABLE_FLAC_HEADER = PLAYABLE_FLAC_FRAME[:7]


@pytest.fixture(autouse=True)
def forbid_network_sockets(monkeypatch):
    def forbidden_socket(*args, **kwargs):
        pytest.fail("the offline live-verification test opened a socket")

    monkeypatch.setattr(socket, "socket", forbidden_socket)
    monkeypatch.setattr(socket, "create_connection", forbidden_socket)


class RecordingEnvironment(dict):
    def __init__(self, values):
        super().__init__(values)
        self.reads = []

    def get(self, key, default=None):
        self.reads.append(key)
        return super().get(key, default)


class FakeUrlResponse:
    def __init__(self, *, body=b"", chunks=None):
        self.status = 200
        self.headers = {}
        self.body = body
        self.chunks = None if chunks is None else list(chunks)
        if self.chunks is not None:
            self.headers["content-length"] = str(sum(map(len, self.chunks)))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback_object):
        return False

    def getcode(self):
        return self.status

    def read(self, size=-1):
        if self.chunks is not None and size != -1:
            return self.chunks.pop(0) if self.chunks else b""
        body = self.body
        self.body = b""
        return body


class InterruptingUrlResponse(FakeUrlResponse):
    def read(self, size=-1):
        if self.chunks:
            return self.chunks.pop(0)
        raise KeyboardInterrupt(SENTINEL)


class FakeClient:
    def __init__(self, track_id=AUTHORIZED_TRACK_ID):
        self.track_id = track_id
        self.search_items = [{"id": track_id}]
        self.signed_response = {
            "url": SIGNED_URL,
            "format_id": 5,
            "mime_type": "audio/mpeg",
            "sampling_rate": 44.1,
        }
        self.searches = []
        self.signed_requests = []
        self.metadata_requests = []
        self.metadata_responses = []

    def search_tracks(self, query, limit):
        self.searches.append((query, limit))
        return {"tracks": {"items": list(self.search_items)}}

    def get_track_url(self, track_id, quality):
        self.signed_requests.append((track_id, quality))
        return dict(self.signed_response)

    def get_track_meta(self, track_id):
        self.metadata_requests.append(track_id)
        if self.metadata_responses:
            return self.metadata_responses.pop(0)
        return _track_metadata(track_id)


class FakeBackend:
    def __init__(self, track_id=AUTHORIZED_TRACK_ID):
        self.client = FakeClient(track_id)
        self.config_snapshot = None
        self.config_mode = None
        self.download_destination = None

    def runtime_facts(self):
        return RuntimeFacts(
            sha="0123456789abcdef0123456789abcdef01234567",
            system="Linux",
            machine="x86_64",
            python="3.13.7",
        )

    def bundle_credentials(self):
        return BundleCredentials(
            app_id="123456789",
            secrets=("secret-one", "secret-two"),
        )

    def login(self, config_path):
        self.config_snapshot = config_path.read_text(encoding="utf-8")
        self.config_mode = stat.S_IMODE(config_path.stat().st_mode)
        return self.client

    def download_track(self, client, track_id, destination, quality):
        self.download_destination = destination
        return RealBackend().download_track(client, track_id, destination, quality)


def _live_environment(tmp_path, **replacements):
    values = {
        ACTIVATION_ENV: ACTIVATION_VALUE,
        "QOBUZ_DL_LIVE_EMAIL": "listener@example.test",
        "QOBUZ_DL_LIVE_PASSWORD": "plain-text-password",
        "QOBUZ_DL_LIVE_TRACK_ID": AUTHORIZED_TRACK_ID,
        "QOBUZ_DL_LIVE_SEARCH_QUERY": "authorized artist track",
        "QOBUZ_DL_LIVE_QUALITY": "5",
        "QOBUZ_DL_LIVE_REPORT": str(tmp_path / "live-report.json"),
    }
    values.update(replacements)
    return RecordingEnvironment(values)


def _mpeg_audio():
    frame = b"\xff\xfb\xe0\x64" + (b"\x00" * 1040)
    return frame * 10


def _install_cbr_mp3_inspection(monkeypatch):
    class ParsedMp3:
        class info:
            sample_rate = 44100
            bitrate = 320000
            bitrate_mode = db.BitrateMode.CBR

    monkeypatch.setattr(db, "MP3", lambda _stream: ParsedMp3())


def _write_tagged_media(path, codec, tags):
    if codec == "mp3":
        path.write_bytes(_mpeg_audio())
        audio = ID3()
        audio.add(TIT2(encoding=3, text=tags["title"]))
        audio.add(TPE1(encoding=3, text=tags["artist"]))
        audio.add(TALB(encoding=3, text=tags["album"]))
        audio.add(TRCK(encoding=3, text=tags["track"]))
        audio.save(path)
        return

    path.write_bytes(PLAYABLE_FLAC)
    audio = FLAC(path)
    audio["TITLE"] = tags["title"]
    audio["ARTIST"] = tags["artist"]
    audio["ALBUM"] = tags["album"]
    audio["TRACKNUMBER"] = tags["track"]
    audio.save()


def _write_tagged_flac_payload(path, payload):
    path.write_bytes(PLAYABLE_FLAC_METADATA + payload)
    audio = FLAC(path)
    audio["TITLE"] = "Authorized track"
    audio["ARTIST"] = "Authorized artist"
    audio["ALBUM"] = "Authorized album"
    audio["TRACKNUMBER"] = "1"
    audio.save()


def _set_flac_streaminfo(
    path, *, min_blocksize=None, max_blocksize=None, total_samples=None
):
    raw = bytearray(path.read_bytes())
    if min_blocksize is not None:
        raw[8:10] = min_blocksize.to_bytes(2, "big")
    if max_blocksize is not None:
        raw[10:12] = max_blocksize.to_bytes(2, "big")
    if total_samples is not None:
        stream_parameters = int.from_bytes(raw[18:26], "big")
        stream_parameters &= ~((1 << 36) - 1)
        stream_parameters |= total_samples
        raw[18:26] = stream_parameters.to_bytes(8, "big")
    path.write_bytes(raw)


def _rewrite_flac_metadata_block_count(path, count):
    raw = path.read_bytes()
    blocks = []
    offset = 4
    while True:
        header = raw[offset : offset + 4]
        block_length = int.from_bytes(header[1:4], "big")
        end = offset + 4 + block_length
        blocks.append(bytes((header[0] & 0x7F,)) + raw[offset + 1 : end])
        offset = end
        if header[0] & 0x80:
            break
    while len(blocks) < count:
        blocks.insert(-1, b"\x01\x00\x00\x00")
    blocks[-1] = bytes((blocks[-1][0] | 0x80,)) + blocks[-1][1:]
    path.write_bytes(b"fLaC" + b"".join(blocks) + raw[offset:])


def _duplicate_flac_streaminfo(path):
    raw = path.read_bytes()
    streaminfo_end = 4 + 4 + 34
    streaminfo = bytes((raw[4] & 0x7F,)) + raw[5:streaminfo_end]
    path.write_bytes(raw[:streaminfo_end] + streaminfo + raw[streaminfo_end:])


def _raw_flac_with_metadata_blocks(block_count, trailing=PLAYABLE_FLAC_FRAME):
    streaminfo = PLAYABLE_FLAC[8:42]
    if block_count == 1:
        blocks = [b"\x80\x00\x00\x22" + streaminfo]
    else:
        blocks = [b"\x00\x00\x00\x22" + streaminfo]
        blocks.extend(b"\x01\x00\x00\x00" for _ in range(block_count - 2))
        blocks.append(b"\x81\x00\x00\x00")
    return b"fLaC" + b"".join(blocks) + trailing


def _test_flac_crc8(data):
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def _test_flac_frame(
    *,
    first=0xFF,
    second=0xF8,
    block_size_code=6,
    sample_rate_code=4,
    channel_code=0,
    bit_depth_code=4,
    reserved_bit=0,
    coded_number=b"\x00",
    block_extension=None,
    sample_rate_extension=None,
    corrupt_crc=False,
    body=b"\x00\x00\x00\x41\x2d",
):
    if block_extension is None:
        block_extension = b"\x9f" if block_size_code == 6 else b""
    if sample_rate_extension is None:
        sample_rate_extension = {
            12: b"\x08",
            13: b"\x1f\x40",
            14: b"\x03\x20",
        }.get(sample_rate_code, b"")
    header = bytes(
        (
            first,
            second,
            (block_size_code << 4) | sample_rate_code,
            (channel_code << 4) | (bit_depth_code << 1) | reserved_bit,
        )
    )
    header += coded_number + block_extension + sample_rate_extension
    crc = _test_flac_crc8(header) ^ int(corrupt_crc)
    return header + bytes((crc,)) + body


def _track_metadata(track_id=AUTHORIZED_TRACK_ID):
    album = {
        "artist": {"name": "Authorized artist"},
        "title": "Authorized album",
        "release_date_original": "2026-01-02",
        "image": {"large": "https://image.example.test/cover.jpg"},
        "genres_list": ["Pop/Rock"],
        "tracks_count": 1,
        "label": {"name": "Authorized label"},
    }
    return {
        "id": track_id,
        "title": "Authorized track",
        "track_number": 1,
        "media_number": 1,
        "maximum_bit_depth": 16,
        "maximum_sampling_rate": 44.1,
        "performer": {"name": "Authorized artist"},
        "album": album,
        "copyright": "(P) 2026 Authorized label",
    }


def _track_metadata_with_album_tracks_count(value):
    result = _track_metadata()
    result["album"]["tracks_count"] = value
    return result


def _encoded_secret_chunks(secret):
    encoded = base64.standard_b64encode(secret.encode()).decode() + ("A" * 44)
    return encoded[:6], encoded[6:12], encoded[12:]


def _bundle_javascript():
    america_seed, america_info, america_extras = _encoded_secret_chunks(
        "america-secret"
    )
    europe_seed, europe_info, europe_extras = _encoded_secret_chunks("europe-secret")
    return (
        'production:{api:{appId:"123456789",'
        'appSecret:"0123456789abcdef0123456789abcdef"}};'
        f'a.initialSeed("{america_seed}",window.utimezone.america);'
        f'b.initialSeed("{europe_seed}",window.utimezone.europe);'
        f'name:"x/America",info:"{america_info}",extras:"{america_extras}";'
        f'name:"x/Europe",info:"{europe_info}",extras:"{europe_extras}";'
    )


def _json_response(payload):
    return FakeUrlResponse(body=json.dumps(payload).encode())


def _install_full_fake_http(monkeypatch, *, first_chunks=None, final_audio=None):
    _install_cbr_mp3_inspection(monkeypatch)
    calls = []
    media_responses = [
        FakeUrlResponse(chunks=first_chunks or [b"first bytes", b"unused"]),
        FakeUrlResponse(chunks=[final_audio or _mpeg_audio()]),
    ]

    def fake_urlopen(request, timeout):
        url = request.full_url
        parsed = urlsplit(url)
        params = parse_qs(parsed.query)
        calls.append((parsed.path, params))
        print(SENTINEL)
        print(SENTINEL, file=sys.stderr)
        logging.getLogger("live-test").error(SENTINEL)

        if url == "https://play.qobuz.com/login":
            return FakeUrlResponse(
                body=b'<script src="/resources/1.2.3-a123/bundle.js"></script>'
            )
        if url == "https://play.qobuz.com/resources/1.2.3-a123/bundle.js":
            return FakeUrlResponse(body=_bundle_javascript().encode())
        if parsed.path.endswith("/user/login"):
            return _json_response(
                {
                    "user": {"credential": {"parameters": {"short_label": "Studio"}}},
                    "user_auth_token": "user-token-secret",
                }
            )
        if parsed.path.endswith("/track/search"):
            return _json_response({"tracks": {"items": [{"id": AUTHORIZED_TRACK_ID}]}})
        if parsed.path.endswith("/track/getFileUrl"):
            return _json_response(
                {
                    "url": SIGNED_URL,
                    "format_id": 5,
                    "mime_type": "audio/mpeg",
                    "sampling_rate": 44.1,
                }
            )
        if parsed.path.endswith("/track/get"):
            return _json_response(_track_metadata())
        if parsed.netloc == "media.example.test":
            return media_responses.pop(0)
        raise AssertionError(f"unexpected request path {parsed.path}")

    monkeypatch.setattr("qobuz_dl.http.urlopen", fake_urlopen)
    return calls


def _install_media_only_http(
    monkeypatch,
    *,
    first_chunks=None,
    final_audio=None,
    final_response=None,
):
    responses = [
        FakeUrlResponse(
            chunks=[b"first bytes", b"unused"] if first_chunks is None else first_chunks
        ),
        final_response or FakeUrlResponse(chunks=[final_audio or _mpeg_audio()]),
    ]

    def fake_urlopen(request, timeout):
        assert request.full_url == SIGNED_URL
        return responses.pop(0)

    monkeypatch.setattr("qobuz_dl.http.urlopen", fake_urlopen)


def _report(tmp_path):
    return json.loads((tmp_path / "live-report.json").read_text(encoding="utf-8"))


def test_default_gate_reads_no_inputs_and_constructs_no_backend(capsys):
    environment = RecordingEnvironment({})

    def forbidden_backend():
        raise AssertionError("the disabled verifier constructed its network backend")

    assert main([], environ=environment, backend_factory=forbidden_backend) == 2
    assert environment.reads == [ACTIVATION_ENV]
    assert capsys.readouterr().err.startswith("Live Qobuz verification is disabled.")


def test_help_and_unsupported_arguments_do_not_read_environment(capsys):
    environment = RecordingEnvironment({})

    with pytest.raises(SystemExit) as help_exit:
        main(["--help"], environ=environment)
    assert help_exit.value.code == 0
    assert ACTIVATION_VALUE in capsys.readouterr().out
    assert environment.reads == []

    with pytest.raises(SystemExit) as unsupported_exit:
        main(["--unknown"], environ=environment)
    assert unsupported_exit.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err
    assert environment.reads == []


@pytest.mark.parametrize(
    "replacements",
    [
        {"QOBUZ_DL_LIVE_EMAIL": ""},
        {"QOBUZ_DL_LIVE_QUALITY": "9"},
        {"QOBUZ_DL_LIVE_TRACK_ID": "   "},
        {"QOBUZ_DL_LIVE_SEARCH_QUERY": "ab"},
        {"QOBUZ_DL_LIVE_REPORT": "relative.json"},
        {"QOBUZ_DL_LIVE_REPORT": "/tmp/report.txt"},
        {"QOBUZ_DL_LIVE_REPORT": "/missing-live-parent/report.json"},
    ],
)
def test_invalid_inputs_fail_before_backend_or_secret_output(
    tmp_path, capsys, replacements
):
    environment = _live_environment(tmp_path, **replacements)

    def forbidden_backend():
        raise AssertionError("invalid inputs constructed the network backend")

    assert main([], environ=environment, backend_factory=forbidden_backend) == 2
    error = capsys.readouterr().err
    assert error.startswith("Live Qobuz verification input error:")
    assert "listener@example.test" not in error
    assert "plain-text-password" not in error


def test_runtime_failure_writes_sanitized_report_before_sensitive_work(
    tmp_path, capsys
):
    sensitive_calls = []
    temporary_calls = []

    class RuntimeFailureBackend(FakeBackend):
        def runtime_facts(self):
            print(SENTINEL)
            print(SENTINEL, file=sys.stderr)
            raise RuntimeError(SENTINEL)

        def bundle_credentials(self):
            sensitive_calls.append("bundle")
            return super().bundle_credentials()

    def recording_temporary_directory(*args, **kwargs):
        temporary_calls.append((args, kwargs))
        return tempfile.TemporaryDirectory(*args, **kwargs)

    assert (
        main(
            [],
            environ=_live_environment(tmp_path),
            backend_factory=RuntimeFailureBackend,
            temporary_directory_factory=recording_temporary_directory,
        )
        == 1
    )

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Live Qobuz verification failed [runtime:runtime_unavailable]. "
        "Sanitized report written.\n"
    )
    report = _report(tmp_path)
    assert report["sha"] is None
    assert report["platform"] is None
    assert report["reason"] == "runtime_unavailable"
    assert next(iter(report["phases"])) == "runtime"
    assert report["phases"]["runtime"] == "failed"
    assert all(
        status == "skipped"
        for phase, status in report["phases"].items()
        if phase != "runtime"
    )
    assert sensitive_calls == []
    assert temporary_calls == []
    assert SENTINEL not in output.err
    assert SENTINEL not in json.dumps(report)


def test_runtime_facts_accept_the_verifier_worktree_root():
    runtime = RealBackend().runtime_facts()
    top_level = subprocess.run(
        ("git", "rev-parse", "--show-toplevel"),
        cwd=live_verification._ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    sha = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=live_verification._ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert Path(top_level).resolve() == live_verification._ROOT.resolve()
    assert runtime.sha == sha
    assert re.fullmatch(r"[0-9a-f]{40}", runtime.sha)


@pytest.mark.parametrize(
    "failure",
    [
        "source-archive",
        "nested-copy",
        "malformed-sha",
        "missing-git",
        "system-collector",
        "machine-collector",
        "python-collector",
        "backend-construction",
    ],
)
def test_runtime_provenance_failures_are_sanitized_before_sensitive_work(
    tmp_path, monkeypatch, capsys, failure
):
    backend = RealBackend()
    sensitive_calls = []
    temporary_calls = []

    def forbidden_bundle():
        sensitive_calls.append("bundle")
        raise AssertionError(SENTINEL)

    monkeypatch.setattr(backend, "bundle_credentials", forbidden_bundle)

    def backend_factory():
        return backend

    if failure == "source-archive":
        archive = tmp_path / "archive"
        archive.mkdir()
        monkeypatch.setattr(live_verification, "_ROOT", archive)
    elif failure == "nested-copy":
        enclosing = tmp_path / "enclosing"
        nested = enclosing / "nested-copy"
        nested.mkdir(parents=True)
        subprocess.run(
            ("git", "init", "--quiet", str(enclosing)),
            check=True,
            capture_output=True,
        )
        monkeypatch.setattr(live_verification, "_ROOT", nested)
    elif failure == "malformed-sha":

        def malformed_sha(command, **kwargs):
            output = (
                str(live_verification._ROOT)
                if "--show-toplevel" in command
                else SENTINEL
            )
            return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

        monkeypatch.setattr(live_verification.subprocess, "run", malformed_sha)
    elif failure == "missing-git":

        def missing_git(*args, **kwargs):
            raise FileNotFoundError(SENTINEL)

        monkeypatch.setattr(live_verification.subprocess, "run", missing_git)
    elif failure.endswith("-collector"):
        collector_name = {
            "system-collector": "system",
            "machine-collector": "machine",
            "python-collector": "python_version",
        }[failure]

        def failed_collector():
            print(SENTINEL)
            print(SENTINEL, file=sys.stderr)
            raise RuntimeError(SENTINEL)

        monkeypatch.setattr(
            live_verification.platform, collector_name, failed_collector
        )
    else:

        def failed_backend_factory():
            print(SENTINEL)
            raise RuntimeError(SENTINEL)

        backend_factory = failed_backend_factory

    def recording_temporary_directory(*args, **kwargs):
        temporary_calls.append((args, kwargs))
        return tempfile.TemporaryDirectory(*args, **kwargs)

    assert (
        main(
            [],
            environ=_live_environment(tmp_path),
            backend_factory=backend_factory,
            temporary_directory_factory=recording_temporary_directory,
        )
        == 1
    )

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Live Qobuz verification failed [runtime:runtime_unavailable]. "
        "Sanitized report written.\n"
    )
    report = _report(tmp_path)
    assert report["sha"] is None
    assert report["platform"] is None
    assert report["reason"] == "runtime_unavailable"
    assert report["phases"] == {
        phase: "failed" if phase == "runtime" else "skipped"
        for phase in report["phases"]
    }
    assert sensitive_calls == []
    assert temporary_calls == []
    assert SENTINEL not in output.err
    assert SENTINEL not in json.dumps(report)


def test_runtime_keyboard_interrupt_is_sanitized_without_sensitive_work(
    tmp_path, capsys
):
    sensitive_calls = []
    temporary_calls = []

    class InterruptedRuntimeBackend(FakeBackend):
        def runtime_facts(self):
            raise KeyboardInterrupt(SENTINEL)

        def bundle_credentials(self):
            sensitive_calls.append("bundle")
            return super().bundle_credentials()

    def recording_temporary_directory(*args, **kwargs):
        temporary_calls.append((args, kwargs))
        return tempfile.TemporaryDirectory(*args, **kwargs)

    assert (
        main(
            [],
            environ=_live_environment(tmp_path),
            backend_factory=InterruptedRuntimeBackend,
            temporary_directory_factory=recording_temporary_directory,
        )
        == 1
    )

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Live Qobuz verification failed [runtime:interrupted]. "
        "Sanitized report written.\n"
    )
    report = _report(tmp_path)
    assert report["sha"] is None
    assert report["platform"] is None
    assert report["reason"] == "interrupted"
    assert report["phases"]["runtime"] == "failed"
    assert report["phases"]["cleanup"] == "skipped"
    assert sensitive_calls == []
    assert temporary_calls == []
    assert SENTINEL not in output.err
    assert SENTINEL not in json.dumps(report)


def test_fake_http_drives_the_complete_production_path_and_sanitized_report(
    tmp_path, monkeypatch, capsys
):
    calls = _install_full_fake_http(monkeypatch)
    environment = _live_environment(tmp_path)
    backend = RealBackend()
    runtime = backend.runtime_facts()
    observations = {}
    real_login = backend.login
    real_download = backend.download_track

    def recording_login(config_path):
        observations["config"] = config_path.read_text(encoding="utf-8")
        observations["config_mode"] = stat.S_IMODE(config_path.stat().st_mode)
        observations["config_path"] = config_path
        return real_login(config_path)

    def recording_download(client, track_id, destination, quality):
        observations["destination"] = destination
        return real_download(client, track_id, destination, quality)

    monkeypatch.setattr(backend, "login", recording_login)
    monkeypatch.setattr(backend, "download_track", recording_download)

    assert main([], environ=environment, backend_factory=lambda: backend) == 0

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Live Qobuz verification passed [complete:ok]. Sanitized report written.\n"
    )
    report_path = tmp_path / "live-report.json"
    report = _report(tmp_path)
    assert report == {
        "schema_version": 1,
        "sha": runtime.sha,
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "quality": {
            "requested": 5,
            "obtained": {
                "format": "MP3",
                "bit_depth": None,
                "sampling_rate": 44100,
                "bitrate_kbps": 320,
            },
        },
        "result": "passed",
        "reason": "ok",
        "phases": {
            "runtime": "passed",
            "bundle": "passed",
            "login": "passed",
            "search": "passed",
            "signed_url": "passed",
            "interruption": "passed",
            "download": "passed",
            "media": "passed",
            "metadata": "passed",
            "cleanup": "passed",
        },
        "limits": [
            "one explicitly authorized Qobuz track",
            "temporary config and download destination removed after verification",
            "no Last.fm requests",
            "FLAC checks cover only the initial frame header, STREAMINFO consistency, and remaining bytes",
            "FLAC audio is not decoded and complete-file integrity is not verified",
            "live execution belongs to issue #48",
        ],
    }
    if os.name == "posix":
        assert stat.S_IMODE(report_path.stat().st_mode) == 0o600
    assert list(tmp_path.glob(".live-report.json.*.tmp")) == []

    serialized = report_path.read_text(encoding="utf-8")
    for forbidden in (
        SENTINEL,
        "listener@example.test",
        "plain-text-password",
        AUTHORIZED_TRACK_ID,
        "authorized artist track",
        "europe-secret",
        "user-token-secret",
        "do-not-publish",
        str(observations["config_path"]),
        str(observations["destination"]),
    ):
        assert forbidden not in serialized
    assert "plain-text-password" not in observations["config"]
    assert (
        hashlib.md5(b"plain-text-password", usedforsecurity=False).hexdigest()
        in observations["config"]
    )
    if os.name == "posix":
        assert observations["config_mode"] == 0o600
    assert not observations["config_path"].exists()
    assert not observations["destination"].exists()

    api_calls = [call for call in calls if "/api.json/" in call[0]]
    searches = [call for call in api_calls if call[0].endswith("/track/search")]
    signed = [call for call in api_calls if call[0].endswith("/track/getFileUrl")]
    metadata_requests = [call for call in api_calls if call[0].endswith("/track/get")]
    assert len(searches) == 1
    assert len(signed) == 3
    assert all(call[1]["track_id"] == [AUTHORIZED_TRACK_ID] for call in signed)
    assert len(metadata_requests) == 2
    assert all(
        call[1]["track_id"] == [AUTHORIZED_TRACK_ID] for call in metadata_requests
    )


@pytest.mark.parametrize(
    "email",
    ["user%tag@example.com", "user%%tag@example.com", "user%(app_id)s@example.com"],
)
def test_percent_email_survives_private_config_and_exact_login_forwarding(
    tmp_path, monkeypatch, email
):
    calls = _install_full_fake_http(monkeypatch)
    environment = _live_environment(tmp_path, QOBUZ_DL_LIVE_EMAIL=email)

    assert main([], environ=environment, backend_factory=RealBackend) == 0

    login_calls = [call for call in calls if call[0].endswith("/user/login")]
    assert len(login_calls) == 1
    assert login_calls[0][1]["email"] == [email]
    serialized = json.dumps(_report(tmp_path))
    assert email not in serialized
    assert AUTHORIZED_TRACK_ID not in serialized


@pytest.mark.parametrize("codec", ["mp3", "flac"])
@pytest.mark.parametrize("field", ["title", "artist", "album", "track"])
def test_each_wrong_nonempty_tag_fails_metadata_verification(
    tmp_path, monkeypatch, capsys, codec, field
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)
    observed = {
        "title": "Authorized track",
        "artist": "Authorized artist",
        "album": "Authorized album",
        "track": "1/1" if codec == "mp3" else "1",
    }
    observed[field] = "2/9" if field == "track" else f"Other {field}"

    def wrong_track_download(client, track_id, destination, quality):
        final = destination / f"track.{codec}"
        _write_tagged_media(final, codec, observed)
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = wrong_track_download
    environment = _live_environment(
        tmp_path,
        QOBUZ_DL_LIVE_QUALITY="5" if codec == "mp3" else "27",
    )

    assert main([], environ=environment, backend_factory=lambda: backend) == 1

    report = _report(tmp_path)
    assert report["reason"] == "metadata_mismatch"
    assert report["phases"]["metadata"] == "failed"
    output = capsys.readouterr()
    serialized = json.dumps(report)
    assert f'"{AUTHORIZED_TRACK_ID}"' not in serialized
    assert observed[field] not in serialized
    assert observed[field] not in output.err
    assert backend.client.metadata_requests == [AUTHORIZED_TRACK_ID]


@pytest.mark.parametrize("codec", ["mp3", "flac"])
def test_metadata_comparison_accepts_nfc_work_version_artist_fallback_and_track_shape(
    tmp_path, monkeypatch, codec
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)
    reference = _track_metadata()
    reference["title"] = "Cafe\u0301"
    reference["version"] = "Live"
    reference["work"] = "Suite"
    reference["performer"] = {"name": ""}
    reference["album"]["artist"]["name"] = "Fallback artist"
    reference["album"]["tracks_count"] = 12
    backend.client.metadata_responses = [reference]

    def matching_download(client, track_id, destination, quality):
        final = destination / f"track.{codec}"
        _write_tagged_media(
            final,
            codec,
            {
                "title": "Suite: Café (Live)",
                "artist": "Fallback artist",
                "album": "Authorized album",
                "track": "01/12" if codec == "mp3" else "01",
            },
        )
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = matching_download
    environment = _live_environment(
        tmp_path,
        QOBUZ_DL_LIVE_QUALITY="5" if codec == "mp3" else "27",
    )

    assert main([], environ=environment, backend_factory=lambda: backend) == 0
    assert backend.client.metadata_requests == [AUTHORIZED_TRACK_ID]


@pytest.mark.parametrize("codec", ["mp3", "flac"])
@pytest.mark.parametrize("tracks_count_state", ["missing", "none"])
@pytest.mark.parametrize(
    ("observed_track", "expected_exit", "expected_reason"),
    [("1/999", 1, "metadata_mismatch"), ("01", 0, "ok")],
)
def test_track_denominator_requires_an_authoritative_total_but_numerator_does_not(
    tmp_path,
    monkeypatch,
    codec,
    tracks_count_state,
    observed_track,
    expected_exit,
    expected_reason,
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)
    reference = _track_metadata()
    if tracks_count_state == "missing":
        reference["album"].pop("tracks_count")
    else:
        reference["album"]["tracks_count"] = None
    backend.client.metadata_responses = [reference]

    def tagged_download(client, track_id, destination, quality):
        final = destination / f"track.{codec}"
        _write_tagged_media(
            final,
            codec,
            {
                "title": "Authorized track",
                "artist": "Authorized artist",
                "album": "Authorized album",
                "track": observed_track,
            },
        )
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = tagged_download
    environment = _live_environment(
        tmp_path,
        QOBUZ_DL_LIVE_QUALITY="5" if codec == "mp3" else "27",
    )

    assert (
        main([], environ=environment, backend_factory=lambda: backend) == expected_exit
    )
    assert _report(tmp_path)["reason"] == expected_reason
    assert backend.client.metadata_requests == [AUTHORIZED_TRACK_ID]


@pytest.mark.parametrize("codec", ["mp3", "flac"])
def test_additional_tag_values_and_wrong_track_total_are_rejected(
    tmp_path, monkeypatch, codec
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)

    def extra_value_download(client, track_id, destination, quality):
        final = destination / f"track.{codec}"
        _write_tagged_media(
            final,
            codec,
            {
                "title": ["Authorized track", "Other title"],
                "artist": "Authorized artist",
                "album": "Authorized album",
                "track": "1/9",
            },
        )
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = extra_value_download
    environment = _live_environment(
        tmp_path,
        QOBUZ_DL_LIVE_QUALITY="5" if codec == "mp3" else "27",
    )

    assert main([], environ=environment, backend_factory=lambda: backend) == 1
    assert _report(tmp_path)["reason"] == "metadata_mismatch"


@pytest.mark.parametrize("codec", ["mp3", "flac"])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "authorized track"),
        ("title", "Authorized track "),
        ("title", "Authorized track!"),
        ("track", "true"),
        ("track", "-1"),
        ("track", "1.5"),
        ("track", "not-a-track"),
        ("track", "1/0"),
        ("track", "1/9"),
    ],
)
def test_metadata_comparison_preserves_text_and_rejects_malformed_track_numbers(
    tmp_path, monkeypatch, codec, field, value
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)
    observed = {
        "title": "Authorized track",
        "artist": "Authorized artist",
        "album": "Authorized album",
        "track": "1/1",
    }
    observed[field] = value

    def altered_download(client, track_id, destination, quality):
        final = destination / f"track.{codec}"
        _write_tagged_media(final, codec, observed)
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = altered_download
    environment = _live_environment(
        tmp_path,
        QOBUZ_DL_LIVE_QUALITY="5" if codec == "mp3" else "27",
    )

    assert main([], environ=environment, backend_factory=lambda: backend) == 1
    assert _report(tmp_path)["reason"] == "metadata_mismatch"


def _without_key(mapping, key):
    result = dict(mapping)
    result.pop(key)
    return result


@pytest.mark.parametrize(
    "reference",
    [
        {**_track_metadata(), "id": "other-track-id"},
        _without_key(_track_metadata(), "title"),
        {**_track_metadata(), "track_number": True},
        {**_track_metadata(), "track_number": -1},
        {**_track_metadata(), "track_number": 1.5},
        _track_metadata_with_album_tracks_count(False),
        _track_metadata_with_album_tracks_count(-1),
        _track_metadata_with_album_tracks_count(1.5),
    ],
)
def test_invalid_authoritative_metadata_fails_without_value_or_id_leakage(
    tmp_path, monkeypatch, capsys, reference
):
    backend = FakeBackend()
    backend.client.metadata_responses = [reference]
    _install_media_only_http(monkeypatch)

    def valid_download(client, track_id, destination, quality):
        final = destination / "track.mp3"
        _write_tagged_media(
            final,
            "mp3",
            {
                "title": "Authorized track",
                "artist": "Authorized artist",
                "album": "Authorized album",
                "track": "1/1",
            },
        )
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = valid_download

    assert (
        main([], environ=_live_environment(tmp_path), backend_factory=lambda: backend)
        == 1
    )

    output = capsys.readouterr()
    report = _report(tmp_path)
    assert report["reason"] == "metadata_reference_invalid"
    assert report["phases"]["metadata"] == "failed"
    assert "other-track-id" not in output.err
    assert "other-track-id" not in json.dumps(report)
    assert backend.client.metadata_requests == [AUTHORIZED_TRACK_ID]


@pytest.mark.parametrize(
    ("search_items", "reason"),
    [
        ([], "authorized_track_not_found"),
        (
            [{"id": AUTHORIZED_TRACK_ID}, {"id": AUTHORIZED_TRACK_ID}],
            "authorized_track_ambiguous",
        ),
    ],
)
def test_search_requires_exactly_one_authorized_track(
    tmp_path, monkeypatch, search_items, reason
):
    backend = FakeBackend()
    backend.client.search_items = search_items
    _install_media_only_http(monkeypatch)

    assert (
        main([], environ=_live_environment(tmp_path), backend_factory=lambda: backend)
        == 1
    )

    report = _report(tmp_path)
    assert report["reason"] == reason
    assert report["phases"]["search"] == "failed"
    assert report["phases"]["signed_url"] == "skipped"


@pytest.mark.parametrize(
    ("signed_response", "reason"),
    [
        ({}, "signed_media_invalid"),
        ({"sample": True, "url": SIGNED_URL}, "authorized_track_is_sample"),
    ],
)
def test_signed_response_rejects_missing_url_and_demo(
    tmp_path, monkeypatch, signed_response, reason
):
    backend = FakeBackend()
    backend.client.signed_response = signed_response
    _install_media_only_http(monkeypatch)

    assert (
        main([], environ=_live_environment(tmp_path), backend_factory=lambda: backend)
        == 1
    )

    report = _report(tmp_path)
    assert report["reason"] == reason
    assert report["phases"]["signed_url"] == "failed"
    assert report["phases"]["interruption"] == "skipped"


def test_zero_byte_interruption_probe_fails_before_download(tmp_path, monkeypatch):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch, first_chunks=[])

    assert (
        main([], environ=_live_environment(tmp_path), backend_factory=lambda: backend)
        == 1
    )

    report = _report(tmp_path)
    assert report["reason"] == "interruption_not_observed"
    assert report["phases"]["interruption"] == "failed"
    assert report["phases"]["download"] == "skipped"


def test_interruption_detects_disabled_production_cleanup(tmp_path, monkeypatch):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)
    monkeypatch.setattr(downloader.os, "remove", lambda path: None)

    assert (
        main([], environ=_live_environment(tmp_path), backend_factory=lambda: backend)
        == 1
    )

    report = _report(tmp_path)
    assert report["reason"] == "interruption_cleanup_failed"
    assert report["phases"]["interruption"] == "failed"
    assert report["phases"]["download"] == "skipped"


def test_backend_output_and_raw_request_failure_are_contained(tmp_path, capsys):
    class FailingBackend(FakeBackend):
        def bundle_credentials(self):
            print(SENTINEL)
            print(SENTINEL, file=sys.stderr)
            logging.getLogger("live-test").error(SENTINEL)
            try:
                raise RuntimeError(SENTINEL)
            except RuntimeError:
                traceback.print_exc()
                raise

    assert (
        main([], environ=_live_environment(tmp_path), backend_factory=FailingBackend)
        == 1
    )

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Live Qobuz verification failed [bundle:unexpected_error]. "
        "Sanitized report written.\n"
    )
    assert SENTINEL not in output.err
    assert SENTINEL not in json.dumps(_report(tmp_path))


def test_progress_output_is_contained(tmp_path, monkeypatch, capsys):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)
    _install_cbr_mp3_inspection(monkeypatch)
    real_download = downloader.download_with_progress

    def noisy_download(
        url, target, description, *, retry_rate_limited=False, after_write=None
    ):
        def noisy_progress(size, downloaded, total):
            print(SENTINEL)
            print(SENTINEL, file=sys.stderr)
            logging.getLogger("live-progress-test").error(SENTINEL)
            if after_write is not None:
                after_write(size, downloaded, total)

        return real_download(
            url,
            target,
            description,
            retry_rate_limited=retry_rate_limited,
            after_write=noisy_progress,
        )

    monkeypatch.setattr(downloader, "download_with_progress", noisy_download)

    assert (
        main([], environ=_live_environment(tmp_path), backend_factory=lambda: backend)
        == 0
    )

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Live Qobuz verification passed [complete:ok]. Sanitized report written.\n"
    )
    assert SENTINEL not in output.err
    assert SENTINEL not in json.dumps(_report(tmp_path))


def test_keyboard_interrupt_is_sanitized_after_temporary_cleanup(tmp_path, capsys):
    class InterruptedBackend(FakeBackend):
        def bundle_credentials(self):
            raise KeyboardInterrupt(SENTINEL)

    assert (
        main(
            [],
            environ=_live_environment(tmp_path),
            backend_factory=InterruptedBackend,
        )
        == 1
    )

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Live Qobuz verification failed [bundle:interrupted]. Sanitized report written.\n"
    )
    report = _report(tmp_path)
    assert report["reason"] == "interrupted"
    assert report["phases"]["bundle"] == "failed"


def test_keyboard_interrupt_during_final_download_is_sanitized_and_cleaned(
    tmp_path, monkeypatch, capsys
):
    backend = FakeBackend()
    _install_media_only_http(
        monkeypatch,
        final_response=InterruptingUrlResponse(chunks=[b"first media bytes"]),
    )

    assert (
        main([], environ=_live_environment(tmp_path), backend_factory=lambda: backend)
        == 1
    )

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Live Qobuz verification failed [download:interrupted]. "
        "Sanitized report written.\n"
    )
    report = _report(tmp_path)
    assert report["reason"] == "interrupted"
    assert report["phases"]["download"] == "failed"
    assert backend.download_destination is not None
    assert not backend.download_destination.exists()


def test_tagging_exception_output_is_contained(tmp_path, monkeypatch, capsys):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)

    def failing_tagger(*args, **kwargs):
        print(SENTINEL)
        print(SENTINEL, file=sys.stderr)
        logging.getLogger("live-test").error(SENTINEL)
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(metadata, "tag_mp3", failing_tagger)

    assert (
        main([], environ=_live_environment(tmp_path), backend_factory=lambda: backend)
        == 1
    )

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Live Qobuz verification failed [download:download_failed]. "
        "Sanitized report written.\n"
    )
    assert SENTINEL not in output.err
    assert SENTINEL not in json.dumps(_report(tmp_path))


@pytest.mark.parametrize("result_shape", ["outside", "multiple"])
def test_finalized_path_must_be_exactly_one_file_inside_destination(
    tmp_path, monkeypatch, result_shape
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)

    def invalid_download(client, track_id, destination, quality):
        outside = tmp_path / "outside.mp3"
        outside.write_bytes(_mpeg_audio())
        if result_shape == "outside":
            paths = (str(outside),)
        else:
            second = tmp_path / "second.mp3"
            second.write_bytes(_mpeg_audio())
            paths = (str(outside), str(second))
        return DownloadResult("finalized", "downloaded", paths)

    backend.download_track = invalid_download

    assert (
        main([], environ=_live_environment(tmp_path), backend_factory=lambda: backend)
        == 1
    )

    report = _report(tmp_path)
    expected = (
        "final_media_outside_destination"
        if result_shape == "outside"
        else "download_result_invalid"
    )
    assert report["reason"] == expected


@pytest.mark.parametrize(
    ("audio_bytes", "expected_phase", "expected_reason"),
    [
        pytest.param(b"tags only", "media", "final_media_invalid", id="tags-only"),
        pytest.param(
            _mpeg_audio(),
            "metadata",
            "metadata_mismatch",
            id="audio-without-tags",
        ),
    ],
)
def test_mp3_requires_playable_audio_and_required_tags(
    tmp_path, monkeypatch, audio_bytes, expected_phase, expected_reason
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)

    def incomplete_download(client, track_id, destination, quality):
        final = destination / "track.mp3"
        final.write_bytes(audio_bytes)
        if audio_bytes == b"tags only":
            tags = ID3()
            tags.add(TIT2(encoding=3, text="Title"))
            tags.add(TPE1(encoding=3, text="Artist"))
            tags.add(TALB(encoding=3, text="Album"))
            tags.add(TRCK(encoding=3, text="1"))
            tags.save(final)
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = incomplete_download

    assert (
        main([], environ=_live_environment(tmp_path), backend_factory=lambda: backend)
        == 1
    )

    report = _report(tmp_path)
    assert report["reason"] == expected_reason
    assert report["phases"][expected_phase] == "failed"


def test_flac_quality_comes_from_the_completed_media(tmp_path, monkeypatch):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)

    def flac_download(client, track_id, destination, quality):
        final = destination / "track.flac"
        final.write_bytes(PLAYABLE_FLAC)
        audio = FLAC(final)
        audio["TITLE"] = "Authorized track"
        audio["ARTIST"] = "Authorized artist"
        audio["ALBUM"] = "Authorized album"
        audio["TRACKNUMBER"] = "1"
        audio.save()
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = flac_download
    environment = _live_environment(tmp_path, QOBUZ_DL_LIVE_QUALITY="27")

    assert main([], environ=environment, backend_factory=lambda: backend) == 0

    assert _report(tmp_path)["quality"] == {
        "requested": 27,
        "obtained": {
            "format": "FLAC",
            "bit_depth": 16,
            "sampling_rate": 8000,
            "bitrate_kbps": None,
        },
    }


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_playable_flac_fixture_decodes_independently():
    completed = subprocess.run(
        (
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "null",
            "-",
        ),
        input=PLAYABLE_FLAC,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")


def test_flac_metadata_traversal_stops_at_the_last_block(tmp_path):
    trailing = b"not-another-metadata-block"
    raw = _raw_flac_with_metadata_blocks(2, trailing=trailing)
    path = tmp_path / "last-block.flac"
    path.write_bytes(raw)

    offset, file_size = _flac_frame_offset(path)

    assert raw[offset:] == trailing
    assert file_size == len(raw)


@pytest.mark.parametrize(
    "tail",
    [
        pytest.param(b"\x81\x00", id="truncated-header"),
        pytest.param(b"\x81\x00\x00\x04\x00\x00", id="overrunning-length"),
    ],
)
def test_flac_metadata_traversal_rejects_truncated_blocks(tmp_path, tail):
    raw = _raw_flac_with_metadata_blocks(1)
    first_block = bytes((raw[4] & 0x7F,)) + raw[5:42]
    path = tmp_path / "truncated-metadata.flac"
    path.write_bytes(b"fLaC" + first_block + tail)

    with pytest.raises(ValueError):
        _flac_frame_offset(path)


def test_flac_metadata_traversal_rejects_duplicate_streaminfo(tmp_path):
    streaminfo = PLAYABLE_FLAC[8:42]
    path = tmp_path / "duplicate-streaminfo.flac"
    path.write_bytes(
        b"fLaC"
        + b"\x00\x00\x00\x22"
        + streaminfo
        + b"\x80\x00\x00\x22"
        + streaminfo
        + PLAYABLE_FLAC_FRAME
    )

    with pytest.raises(ValueError):
        _flac_frame_offset(path)


def test_flac_metadata_traversal_accepts_128_blocks_and_rejects_129(tmp_path):
    accepted = tmp_path / "128-blocks.flac"
    accepted.write_bytes(_raw_flac_with_metadata_blocks(128))
    rejected = tmp_path / "129-blocks.flac"
    rejected.write_bytes(_raw_flac_with_metadata_blocks(129))

    offset, file_size = _flac_frame_offset(accepted)

    assert accepted.read_bytes()[offset:] == PLAYABLE_FLAC_FRAME
    assert file_size == accepted.stat().st_size
    with pytest.raises(ValueError):
        _flac_frame_offset(rejected)


def test_flac_with_declared_samples_but_no_audio_payload_is_rejected(
    tmp_path, monkeypatch
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)

    def metadata_only_flac_download(client, track_id, destination, quality):
        final = destination / "track.flac"
        streaminfo = bytearray(34)
        streaminfo[0:2] = (4096).to_bytes(2, "big")
        streaminfo[2:4] = (4096).to_bytes(2, "big")
        value = (192000 << 44) | (1 << 41) | (23 << 36) | 192000
        streaminfo[10:18] = value.to_bytes(8, "big")
        final.write_bytes(
            b"fLaC" + bytes([0x80]) + (34).to_bytes(3, "big") + streaminfo
        )
        audio = FLAC(final)
        audio["TITLE"] = "Authorized track"
        audio["ARTIST"] = "Authorized artist"
        audio["ALBUM"] = "Authorized album"
        audio["TRACKNUMBER"] = "1"
        audio.save()
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = metadata_only_flac_download
    environment = _live_environment(tmp_path, QOBUZ_DL_LIVE_QUALITY="27")

    assert main([], environ=environment, backend_factory=lambda: backend) == 1

    report = _report(tmp_path)
    assert report["reason"] == "final_media_invalid"
    assert report["phases"]["media"] == "failed"


@pytest.mark.parametrize(
    ("max_blocksize", "total_samples"),
    [
        pytest.param(160, 40_000, id="maximum-block-size"),
        pytest.param(32_768, 160, id="total-samples"),
    ],
)
def test_flac_rejects_frame_block_larger_than_streaminfo_bounds(
    tmp_path, monkeypatch, max_blocksize, total_samples
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)

    def contradictory_flac_download(client, track_id, destination, quality):
        final = destination / "track.flac"
        _write_tagged_flac_payload(final, _test_flac_frame(block_size_code=15))
        _set_flac_streaminfo(
            final,
            max_blocksize=max_blocksize,
            total_samples=total_samples,
        )
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = contradictory_flac_download

    assert (
        main(
            [],
            environ=_live_environment(tmp_path, QOBUZ_DL_LIVE_QUALITY="27"),
            backend_factory=lambda: backend,
        )
        == 1
    )
    report = _report(tmp_path)
    assert report["reason"] == "final_media_invalid"
    assert report["phases"]["media"] == "failed"


@pytest.mark.parametrize(
    ("block_count", "expected_status"),
    [
        pytest.param(128, 0, id="maximum-accepted"),
        pytest.param(129, 1, id="first-rejected"),
    ],
)
def test_flac_metadata_block_limit_is_enforced_by_the_verifier(
    tmp_path, monkeypatch, block_count, expected_status
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)

    def many_metadata_blocks_download(client, track_id, destination, quality):
        final = destination / "track.flac"
        _write_tagged_flac_payload(final, PLAYABLE_FLAC_FRAME)
        _rewrite_flac_metadata_block_count(final, block_count)
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = many_metadata_blocks_download

    status = main(
        [],
        environ=_live_environment(tmp_path, QOBUZ_DL_LIVE_QUALITY="27"),
        backend_factory=lambda: backend,
    )

    assert status == expected_status
    report = _report(tmp_path)
    if expected_status:
        assert report["reason"] == "final_media_invalid"
        assert report["phases"]["media"] == "failed"
    else:
        assert report["result"] == "passed"


def test_flac_duplicate_streaminfo_is_rejected_by_the_verifier(tmp_path, monkeypatch):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)

    def duplicate_streaminfo_download(client, track_id, destination, quality):
        final = destination / "track.flac"
        _write_tagged_flac_payload(final, PLAYABLE_FLAC_FRAME)
        _duplicate_flac_streaminfo(final)
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = duplicate_streaminfo_download

    assert (
        main(
            [],
            environ=_live_environment(tmp_path, QOBUZ_DL_LIVE_QUALITY="27"),
            backend_factory=lambda: backend,
        )
        == 1
    )
    report = _report(tmp_path)
    assert report["reason"] == "final_media_invalid"
    assert report["phases"]["media"] == "failed"


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff",
        b"not-a-frame" * 4,
        b"prefix" + PLAYABLE_FLAC_FRAME,
        PLAYABLE_FLAC_HEADER,
    ],
)
def test_flac_requires_a_complete_initial_frame_header_and_remaining_frame_bytes(
    tmp_path, monkeypatch, payload
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)

    def malformed_flac_download(client, track_id, destination, quality):
        backend.download_destination = destination
        final = destination / "track.flac"
        _write_tagged_flac_payload(final, payload)
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = malformed_flac_download
    environment = _live_environment(tmp_path, QOBUZ_DL_LIVE_QUALITY="27")

    assert main([], environ=environment, backend_factory=lambda: backend) == 1

    report = _report(tmp_path)
    assert report["reason"] == "final_media_invalid"
    assert report["phases"]["media"] == "failed"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(_test_flac_frame(first=0xFE), id="sync-first-byte"),
        pytest.param(_test_flac_frame(second=0xFA), id="sync-reserved-bit"),
        pytest.param(_test_flac_frame(block_size_code=0), id="reserved-block-size"),
        pytest.param(_test_flac_frame(sample_rate_code=15), id="reserved-sample-rate"),
        pytest.param(_test_flac_frame(channel_code=11), id="reserved-channel"),
        pytest.param(_test_flac_frame(bit_depth_code=3), id="reserved-bit-depth"),
        pytest.param(_test_flac_frame(reserved_bit=1), id="reserved-header-bit"),
        pytest.param(_test_flac_frame(coded_number=b"\x80"), id="invalid-number-lead"),
        pytest.param(
            _test_flac_frame(coded_number=b"\xc2A"),
            id="invalid-number-continuation",
        ),
        pytest.param(_test_flac_frame(coded_number=b"\xc0\x80"), id="overlong-number"),
        pytest.param(
            _test_flac_frame(coded_number=b"\x01"), id="nonzero-initial-number"
        ),
        pytest.param(
            _test_flac_frame(block_size_code=7, block_extension=b"\xff\xff"),
            id="forbidden-65536-block-size",
        ),
        pytest.param(
            _test_flac_frame(sample_rate_code=12, sample_rate_extension=b"\x00"),
            id="zero-khz-sample-rate",
        ),
        pytest.param(
            _test_flac_frame(sample_rate_code=13, sample_rate_extension=b"\x00\x00"),
            id="zero-hz-sample-rate",
        ),
        pytest.param(
            _test_flac_frame(sample_rate_code=14, sample_rate_extension=b"\x00\x00"),
            id="zero-tens-hz-sample-rate",
        ),
        pytest.param(_test_flac_frame(corrupt_crc=True), id="invalid-crc"),
        pytest.param(
            _test_flac_frame(sample_rate_code=9),
            id="streaminfo-sample-rate-mismatch",
        ),
        pytest.param(
            _test_flac_frame(channel_code=1), id="streaminfo-channel-mismatch"
        ),
        pytest.param(
            _test_flac_frame(bit_depth_code=6), id="streaminfo-bit-depth-mismatch"
        ),
        pytest.param(_test_flac_frame(body=b"\x00"), id="header-with-one-body-byte"),
        pytest.param(
            _test_flac_frame(body=b"\x00\x00"), id="header-with-two-body-bytes"
        ),
    ],
)
def test_flac_rejects_malformed_initial_frame_fields(
    tmp_path, monkeypatch, capsys, payload
):
    private_track_id = "private-track-id-47"
    backend = FakeBackend(private_track_id)
    _install_media_only_http(monkeypatch)

    def malformed_flac_download(client, track_id, destination, quality):
        backend.download_destination = destination
        final = destination / "track.flac"
        _write_tagged_flac_payload(final, payload)
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = malformed_flac_download
    environment = _live_environment(
        tmp_path,
        QOBUZ_DL_LIVE_QUALITY="27",
        QOBUZ_DL_LIVE_TRACK_ID=private_track_id,
    )

    assert main([], environ=environment, backend_factory=lambda: backend) == 1

    report = _report(tmp_path)
    assert report["reason"] == "final_media_invalid"
    assert report["phases"]["media"] == "failed"
    assert backend.download_destination is not None
    assert not backend.download_destination.exists()
    sanitized = capsys.readouterr().err + json.dumps(report)
    assert SENTINEL not in sanitized
    assert SIGNED_URL not in sanitized
    assert private_track_id not in sanitized


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(b"\xff", id="sync"),
        pytest.param(b"\xff\xf8", id="sync-fields"),
        pytest.param(b"\xff\xf8\x64", id="coded-fields"),
        pytest.param(b"\xff\xf8\x64\x08", id="coded-number"),
        pytest.param(b"\xff\xf8\x64\x08\xc2", id="number-continuation"),
        pytest.param(b"\xff\xf8\x64\x08\x00", id="block-size-extension"),
        pytest.param(b"\xff\xf8\x74\x08\x00\x00", id="two-byte-block-size-extension"),
        pytest.param(b"\xff\xf8\x6c\x08\x00\x9f", id="khz-sample-rate-extension"),
        pytest.param(b"\xff\xf8\x6d\x08\x00\x9f\x1f", id="hz-sample-rate-extension"),
        pytest.param(
            b"\xff\xf8\x6e\x08\x00\x9f\x03", id="tens-hz-sample-rate-extension"
        ),
        pytest.param(PLAYABLE_FLAC_HEADER[:-1], id="header-crc"),
    ],
)
def test_flac_rejects_each_truncated_initial_frame_field(
    tmp_path, monkeypatch, payload
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)

    def truncated_flac_download(client, track_id, destination, quality):
        final = destination / "track.flac"
        _write_tagged_flac_payload(final, payload)
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = truncated_flac_download

    assert (
        main(
            [],
            environ=_live_environment(tmp_path, QOBUZ_DL_LIVE_QUALITY="27"),
            backend_factory=lambda: backend,
        )
        == 1
    )
    assert _report(tmp_path)["reason"] == "final_media_invalid"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(_test_flac_frame(body=b"\x00\x00\x00"), id="minimum-body"),
        pytest.param(
            _test_flac_frame(block_size_code=7, block_extension=b"\x00\x9f"),
            id="two-byte-block-size",
        ),
        pytest.param(_test_flac_frame(sample_rate_code=0), id="streaminfo-sample-rate"),
        pytest.param(_test_flac_frame(sample_rate_code=12), id="khz-sample-rate"),
        pytest.param(_test_flac_frame(sample_rate_code=13), id="hz-sample-rate"),
        pytest.param(_test_flac_frame(sample_rate_code=14), id="tens-hz-sample-rate"),
        pytest.param(_test_flac_frame(bit_depth_code=0), id="streaminfo-bit-depth"),
        pytest.param(_test_flac_frame(second=0xF9), id="variable-block-strategy"),
    ],
)
def test_flac_accepts_structurally_valid_initial_frame_headers(
    tmp_path, monkeypatch, payload
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)

    def minimal_structural_flac_download(client, track_id, destination, quality):
        final = destination / "track.flac"
        _write_tagged_flac_payload(final, payload)
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = minimal_structural_flac_download

    assert (
        main(
            [],
            environ=_live_environment(tmp_path, QOBUZ_DL_LIVE_QUALITY="27"),
            backend_factory=lambda: backend,
        )
        == 0
    )


@pytest.mark.parametrize(
    ("payload", "max_blocksize", "total_samples"),
    [
        pytest.param(
            _test_flac_frame(block_size_code=6, block_extension=b"\x9f"),
            160,
            1_000,
            id="equal-maximum-block-size",
        ),
        pytest.param(
            _test_flac_frame(block_size_code=6, block_extension=b"\x9f"),
            1_000,
            160,
            id="equal-total-samples",
        ),
        pytest.param(
            _test_flac_frame(block_size_code=6, block_extension=b"\x00"),
            160,
            160,
            id="shorter-than-streaminfo-minimum",
        ),
    ],
)
def test_flac_accepts_frame_block_size_boundaries(
    tmp_path, monkeypatch, payload, max_blocksize, total_samples
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)

    def boundary_flac_download(client, track_id, destination, quality):
        final = destination / "track.flac"
        _write_tagged_flac_payload(final, payload)
        _set_flac_streaminfo(
            final,
            min_blocksize=160,
            max_blocksize=max_blocksize,
            total_samples=total_samples,
        )
        return DownloadResult("finalized", "downloaded", (str(final),))

    backend.download_track = boundary_flac_download

    assert (
        main(
            [],
            environ=_live_environment(tmp_path, QOBUZ_DL_LIVE_QUALITY="27"),
            backend_factory=lambda: backend,
        )
        == 0
    )


def test_cleanup_failure_overrides_success_and_writes_failed_report(
    tmp_path, monkeypatch, capsys
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)
    _install_cbr_mp3_inspection(monkeypatch)

    class FailingCleanupDirectory:
        def __init__(self, prefix):
            self.directory = tempfile.TemporaryDirectory(prefix=prefix)
            self.name = self.directory.name

        def cleanup(self):
            self.directory.cleanup()
            raise OSError(SENTINEL)

    assert (
        main(
            [],
            environ=_live_environment(tmp_path),
            backend_factory=lambda: backend,
            temporary_directory_factory=FailingCleanupDirectory,
        )
        == 1
    )

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Live Qobuz verification failed [cleanup:cleanup_failed]. "
        "Sanitized report written.\n"
    )
    report = _report(tmp_path)
    assert report["result"] == "failed"
    assert report["reason"] == "cleanup_failed"
    assert report["phases"]["metadata"] == "passed"
    assert report["phases"]["cleanup"] == "failed"
    assert backend.download_destination is not None
    assert not backend.download_destination.exists()


def test_atomic_report_failure_preserves_previous_report(tmp_path, monkeypatch, capsys):
    report_path = tmp_path / "live-report.json"
    report_path.write_text('{"previous": true}\n', encoding="utf-8")

    def failing_replace(source, destination):
        raise OSError(SENTINEL)

    monkeypatch.setattr(os, "replace", failing_replace)

    class FailingBackend(FakeBackend):
        def bundle_credentials(self):
            raise RuntimeError(SENTINEL)

    assert (
        main([], environ=_live_environment(tmp_path), backend_factory=FailingBackend)
        == 1
    )

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Live Qobuz verification failed [report:report_write_failed]. "
        "No report was written.\n"
    )
    assert report_path.read_text(encoding="utf-8") == '{"previous": true}\n'
    assert list(tmp_path.glob(".live-report.json.*.tmp")) == []


def test_runtime_report_write_failure_preserves_previous_report(
    tmp_path, monkeypatch, capsys
):
    report_path = tmp_path / "live-report.json"
    report_path.write_text('{"previous": true}\n', encoding="utf-8")

    def failing_replace(source, destination):
        raise OSError(SENTINEL)

    monkeypatch.setattr(os, "replace", failing_replace)

    class RuntimeFailureBackend(FakeBackend):
        def runtime_facts(self):
            raise RuntimeError(SENTINEL)

        def bundle_credentials(self):
            raise AssertionError("runtime failure reached credentials")

    assert (
        main(
            [],
            environ=_live_environment(tmp_path),
            backend_factory=RuntimeFailureBackend,
        )
        == 1
    )

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Live Qobuz verification failed [report:report_write_failed]. "
        "No report was written.\n"
    )
    assert SENTINEL not in output.err
    assert report_path.read_text(encoding="utf-8") == '{"previous": true}\n'
    assert list(tmp_path.glob(".live-report.json.*.tmp")) == []
