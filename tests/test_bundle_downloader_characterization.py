import base64

import pytest

from qobuz_dl.bundle import Bundle
from qobuz_dl.downloader import download_with_progress
from qobuz_dl.exceptions import BundleError


class FakeHTTPResponse:
    def __init__(self, *, text="", content_length=None):
        self.text = text
        self.headers = {}
        if content_length is not None:
            self.headers["content-length"] = str(content_length)

    def raise_for_status(self):
        return None


class FakeBundleSession:
    def __init__(self):
        self.urls = []
        self.responses = [
            FakeHTTPResponse(
                text='<script src="/resources/1.2.3-a123/bundle.js"></script>'
            ),
            FakeHTTPResponse(text=make_fake_bundle_js()),
        ]

    def get(self, url):
        self.urls.append(url)
        return self.responses.pop(0)


def encoded_secret_chunks(secret):
    encoded = base64.standard_b64encode(secret.encode()).decode() + ("A" * 44)
    return encoded[:6], encoded[6:12], encoded[12:]


def make_fake_bundle_js():
    america_seed, america_info, america_extras = encoded_secret_chunks("america-secret")
    europe_seed, europe_info, europe_extras = encoded_secret_chunks("europe-secret")
    return (
        'production:{api:{appId:"123456789",appSecret:"0123456789abcdef0123456789abcdef"}};'
        f'a.initialSeed("{america_seed}",window.utimezone.america);'
        f'b.initialSeed("{europe_seed}",window.utimezone.europe);'
        f'name:"x/America",info:"{america_info}",extras:"{america_extras}";'
        f'name:"x/Europe",info:"{europe_info}",extras:"{europe_extras}";'
    )


def test_bundle_extracts_app_id_and_compact_fake_secrets(monkeypatch):
    sessions = []

    def fake_session_factory():
        session = FakeBundleSession()
        sessions.append(session)
        return session

    monkeypatch.setattr("qobuz_dl.bundle.HttpClient", fake_session_factory)

    bundle = Bundle()

    assert sessions[0].urls == [
        "https://play.qobuz.com/login",
        "https://play.qobuz.com/resources/1.2.3-a123/bundle.js",
    ]
    assert bundle.get_app_id() == "123456789"
    assert bundle.get_secrets() == {
        "europe": "europe-secret",
        "america": "america-secret",
    }


def test_bundle_raises_bundle_error_when_login_page_has_no_bundle_url(monkeypatch):
    class EmptyPageSession:
        def get(self, url):
            return FakeHTTPResponse(text="<html><body>no scripts here</body></html>")

    monkeypatch.setattr("qobuz_dl.bundle.HttpClient", EmptyPageSession)

    with pytest.raises(BundleError, match="bundle URL"):
        Bundle()


def test_download_with_progress_writes_streamed_content(tmp_path, monkeypatch):
    target = tmp_path / "track.flac.tmp"
    requested = []

    def fake_stream_download(url, target_path, *, progress=None):
        requested.append((url, target_path))
        target_path.write_bytes(b"abcdef")
        if progress is not None:
            progress(3, 3, 6)
            progress(3, 6, 6)
        return 6

    monkeypatch.setattr(
        "qobuz_dl.downloader.http.stream_download", fake_stream_download
    )

    download_with_progress("https://media.example.test/file", target, "track")

    assert requested == [("https://media.example.test/file", target)]
    assert target.read_bytes() == b"abcdef"


def test_download_with_progress_throttles_progress_logging(
    tmp_path, monkeypatch, caplog
):
    target = tmp_path / "track.flac.tmp"

    def fake_stream_download(url, target_path, *, progress=None):
        target_path.write_bytes(b"x" * 2048)
        if progress is not None:
            progress(1024, 1024, 2 * 1024 * 1024)
            progress(1024, 2048, 2 * 1024 * 1024)
            progress(1024 * 1024 - 2048, 1024 * 1024, 2 * 1024 * 1024)
            progress(1024 * 1024, 2 * 1024 * 1024, 2 * 1024 * 1024)
        return 2048

    monkeypatch.setattr(
        "qobuz_dl.downloader.http.stream_download", fake_stream_download
    )
    caplog.set_level("INFO", logger="qobuz_dl.downloader")

    download_with_progress("https://media.example.test/file", target, "track")

    assert [
        record.getMessage()
        for record in caplog.records
        if record.name == "qobuz_dl.downloader"
    ] == [
        "\x1b[36m1048576/2097152 /// track\x1b[0m",
        "\x1b[36m2097152/2097152 /// track\x1b[0m",
    ]


def test_download_with_progress_raises_connection_error_when_stream_is_short(
    tmp_path, monkeypatch
):
    target = tmp_path / "track.flac.tmp"

    def fake_stream_download(url, target_path, *, progress=None):
        target_path.write_bytes(b"abc")
        raise ConnectionError("File download was interrupted for " + str(target_path))

    monkeypatch.setattr(
        "qobuz_dl.downloader.http.stream_download", fake_stream_download
    )

    with pytest.raises(ConnectionError, match="File download was interrupted"):
        download_with_progress("https://media.example.test/file", target, "track")

    assert not target.exists()
