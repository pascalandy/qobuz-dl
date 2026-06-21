from urllib.error import HTTPError, URLError

import pytest

from qobuz_dl import http


class FakeHeaders(dict):
    def items(self):
        return super().items()


class FakeResponse:
    def __init__(self, *, status=200, headers=None, body=b"", chunks=None):
        self.status = status
        self.headers = FakeHeaders(headers or {})
        self._body = body
        self._chunks = list(chunks or [])
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def getcode(self):
        return self.status

    def close(self):
        return None

    def read(self, size=-1):
        self.read_sizes.append(size)
        if size == -1:
            body = self._body
            self._body = b""
            return body
        if self._chunks:
            return self._chunks.pop(0)
        return b""


def test_get_appends_query_params_and_passes_headers(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return FakeResponse(
            headers={"content-type": "application/json"}, body=b'{"ok": true}'
        )

    monkeypatch.setattr(http, "urlopen", fake_urlopen)

    response = http.get(
        "https://api.example.test/search?existing=1",
        params={"query": "alpha beta", "limit": 2},
        headers={"X-Test": "yes"},
        timeout=7,
    )

    assert captured == {
        "url": "https://api.example.test/search?existing=1&query=alpha+beta&limit=2",
        "headers": {"X-test": "yes"},
        "timeout": 7,
    }
    assert response.status_code == 200
    assert response.headers == {"content-type": "application/json"}
    assert response.content == b'{"ok": true}'


def test_get_returns_http_error_response_and_raise_for_status_raises(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            404,
            "Not Found",
            FakeHeaders({"content-type": "text/plain"}),
            FakeResponse(body=b"missing"),
        )

    monkeypatch.setattr(http, "urlopen", fake_urlopen)

    response = http.get("https://api.example.test/missing")

    assert response.status_code == 404
    assert response.headers == {"content-type": "text/plain"}
    assert response.content == b"missing"
    with pytest.raises(http.HttpStatusError) as exc_info:
        response.raise_for_status()
    assert exc_info.value.status_code == 404
    assert exc_info.value.body == b"missing"


def test_get_maps_url_error_to_http_request_error(monkeypatch):
    def fake_urlopen(request, timeout):
        raise URLError("network unavailable")

    monkeypatch.setattr(http, "urlopen", fake_urlopen)

    with pytest.raises(http.HttpRequestError, match="network unavailable"):
        http.get("https://api.example.test/unavailable")


def test_get_maps_malformed_url_to_http_request_error():
    with pytest.raises(http.HttpRequestError, match="unknown url type"):
        http.get("www.last.fm/user/example/library/playlists/1")


def test_http_client_uses_configured_headers_and_timeout(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return FakeResponse(body=b"{}")

    monkeypatch.setattr(http, "urlopen", fake_urlopen)

    client = http.HttpClient(headers={"X-App-Id": "123456789"}, timeout=13)
    response = client.get("https://api.example.test/album/get", params={"album_id": 1})

    assert captured == {
        "url": "https://api.example.test/album/get?album_id=1",
        "headers": {"X-app-id": "123456789"},
        "timeout": 13,
    }
    assert response.status_code == 200


def test_stream_download_writes_chunks_calls_progress_and_returns_byte_count(
    tmp_path, monkeypatch
):
    captured = {}
    progress_calls = []

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return FakeResponse(
            headers={"content-length": "6"},
            chunks=[b"ab", b"cd", b"ef"],
        )

    monkeypatch.setattr(http, "urlopen", fake_urlopen)
    target = tmp_path / "track.flac"

    byte_count = http.stream_download(
        "https://media.example.test/track.flac",
        target,
        headers={"Authorization": "Bearer token"},
        timeout=11,
        chunk_size=2,
        progress=lambda size, downloaded, total: progress_calls.append(
            (size, downloaded, total)
        ),
    )

    assert captured == {
        "url": "https://media.example.test/track.flac",
        "headers": {"Authorization": "Bearer token"},
        "timeout": 11,
    }
    assert target.read_bytes() == b"abcdef"
    assert progress_calls == [(2, 2, 6), (2, 4, 6), (2, 6, 6)]
    assert byte_count == 6


def test_stream_download_maps_malformed_url_to_http_request_error(tmp_path):
    target = tmp_path / "track.flac"

    with pytest.raises(http.HttpRequestError, match="unknown url type"):
        http.stream_download("media.example.test/track.flac", target)

    assert not target.exists()


def test_stream_download_http_status_error_does_not_create_target(
    tmp_path, monkeypatch
):
    def fake_urlopen(request, timeout):
        return FakeResponse(status=503, body=b"temporarily unavailable")

    monkeypatch.setattr(http, "urlopen", fake_urlopen)
    target = tmp_path / "unavailable.flac"

    with pytest.raises(http.HttpStatusError) as exc_info:
        http.stream_download("https://media.example.test/unavailable.flac", target)

    assert exc_info.value.status_code == 503
    assert exc_info.value.body == b"temporarily unavailable"
    assert not target.exists()


def test_stream_download_succeeds_when_content_length_is_missing(tmp_path, monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeResponse(chunks=[b"abc", b"def"])

    monkeypatch.setattr(http, "urlopen", fake_urlopen)
    target = tmp_path / "unknown-length.flac"

    byte_count = http.stream_download("https://media.example.test/unknown.flac", target)

    assert target.read_bytes() == b"abcdef"
    assert byte_count == 6


def test_stream_download_raises_connection_error_on_content_length_mismatch(
    tmp_path, monkeypatch
):
    def fake_urlopen(request, timeout):
        return FakeResponse(headers={"content-length": "5"}, chunks=[b"abc"])

    monkeypatch.setattr(http, "urlopen", fake_urlopen)
    target = tmp_path / "short.flac"

    with pytest.raises(ConnectionError, match="File download was interrupted"):
        http.stream_download("https://media.example.test/short.flac", target)

    assert target.read_bytes() == b"abc"
