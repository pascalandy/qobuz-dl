import base64
import hashlib
import json
import logging
import os
import platform
import socket
import stat
import sys
import tempfile
import traceback
from urllib.parse import parse_qs, urlsplit

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TALB, TIT2, TPE1, TRCK

from qobuz_dl import downloader, metadata
from qobuz_dl.downloader import DownloadResult
from qobuz_dl.live_verification import (
    ACTIVATION_ENV,
    ACTIVATION_VALUE,
    BundleCredentials,
    RealBackend,
    RuntimeFacts,
    main,
)

SENTINEL = "raw-secret-sentinel"
AUTHORIZED_TRACK_ID = "123456"
SIGNED_URL = "https://media.example.test/authorized.mp3?token=do-not-publish"
PLAYABLE_FLAC = base64.b64decode(
    "ZkxhQwAAACIAoACgAAAAAAFVAfQA8AAAAKAAAAAAAAAAAAAAAAAAAAAAhAAALAwAAABM"
    "YXZmNjMuMS4xMDEBAAAAFAAAAGVuY29kZXI9TGF2ZjYzLjEuMTAx//hkCACfNwAAAEEt"
)


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
        self.signed_response = {"url": SIGNED_URL}
        self.searches = []
        self.signed_requests = []

    def search_tracks(self, query, limit):
        self.searches.append((query, limit))
        return {"tracks": {"items": list(self.search_items)}}

    def get_track_url(self, track_id, quality):
        self.signed_requests.append((track_id, quality))
        return dict(self.signed_response)

    def get_track_meta(self, track_id):
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
    frame = b"\xff\xfb\x90\x64" + (b"\x00" * 413)
    return frame * 10


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
            return _json_response({"url": SIGNED_URL})
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
                "bitrate_kbps": 128,
            },
        },
        "result": "passed",
        "reason": "ok",
        "phases": {
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
    assert len(searches) == 1
    assert len(signed) == 3
    assert all(call[1]["track_id"] == [AUTHORIZED_TRACK_ID] for call in signed)


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
        (b"tags only", "media", "final_media_invalid"),
        (_mpeg_audio(), "metadata", "metadata_invalid"),
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


def test_cleanup_failure_overrides_success_and_writes_failed_report(
    tmp_path, monkeypatch, capsys
):
    backend = FakeBackend()
    _install_media_only_http(monkeypatch)

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
