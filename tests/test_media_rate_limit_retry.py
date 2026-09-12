import os
from inspect import signature
from pathlib import Path
from urllib.error import HTTPError

import pytest

from qobuz_dl import downloader, http
from qobuz_dl.core import QobuzDL
from qobuz_dl.db import handle_download_id


class FakeHeaders(dict):
    def items(self):
        return super().items()


class StreamResponse:
    def __init__(self, *, status=200, headers=None, reads=(), close_error=None):
        self.status = status
        self.headers = FakeHeaders(headers or {})
        self._reads = list(reads)
        self._close_error = close_error
        self.read_calls = 0
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False

    def getcode(self):
        return self.status

    def close(self):
        self.closed = True
        if self._close_error is not None:
            raise self._close_error

    def read(self, size=-1):
        self.read_calls += 1
        if not self._reads:
            return b""
        value = self._reads.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


class RejectedBody:
    def __init__(self):
        self.read_calls = 0
        self.closed = False

    def read(self, size=-1):
        self.read_calls += 1
        raise AssertionError("a rejected 429 body must remain unread")

    def close(self):
        self.closed = True


def _returned_429():
    response = StreamResponse(status=429, headers={"rEtRy-AfTeR": "0"})
    return response, response


def _raised_429():
    body = RejectedBody()
    error = HTTPError(
        "https://media.example.test/track.flac",
        429,
        "Too Many Requests",
        FakeHeaders({"rEtRy-AfTeR": "0"}),
        body,
    )
    return error, body


def _install_urlopen_sequence(monkeypatch, outcomes):
    requests = []
    remaining = list(outcomes)

    def fake_urlopen(request, timeout):
        requests.append(request)
        outcome = remaining.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(http, "urlopen", fake_urlopen)
    return requests, remaining


def _stream_media(url, target, **kwargs):
    if "retry_rate_limited" in signature(http.stream_download).parameters:
        kwargs["retry_rate_limited"] = True
    return http.stream_download(url, target, **kwargs)


def _track(track_id="track-1", title="Single Track", track_number=1):
    return {
        "id": track_id,
        "title": title,
        "performer": {"name": "Track Artist"},
        "album": {"artist": {"name": "Album Artist"}},
        "maximum_bit_depth": 24,
        "maximum_sampling_rate": 96,
        "track_number": track_number,
        "media_number": 1,
        "version": None,
    }


def _album_meta(tracks):
    return {
        "id": "album-1",
        "streamable": True,
        "release_type": "album",
        "title": "Album Title",
        "artist": {"name": "Album Artist"},
        "release_date_original": "2024-02-03",
        "image": {"large": "https://img.example.test/cover.jpg"},
        "tracks": {"items": tracks},
        "tracks_count": len(tracks),
        "genres_list": ["Rock"],
        "label": {"name": "Label"},
        "copyright": "",
        "goodies": [{"url": "https://img.example.test/booklet.pdf"}],
    }


def _track_meta():
    return {
        **_track(),
        "album": {
            "id": "track-album",
            "title": "Track Album",
            "artist": {"name": "Album Artist"},
            "release_date_original": "2024-02-03",
            "image": {"large": "https://img.example.test/cover.jpg"},
            "tracks_count": 1,
            "genres_list": ["Rock"],
        },
        "copyright": "",
    }


class DownloadClient:
    def __init__(self, *, tracks=None):
        self.album_meta = _album_meta(tracks or [_track()])
        self.track_meta = _track_meta()

    def get_album_meta(self, item_id):
        assert item_id == "album-1"
        return self.album_meta

    def get_track_meta(self, item_id):
        assert item_id == "track-1"
        return self.track_meta

    def get_track_url(self, item_id, fmt_id):
        assert fmt_id == 27
        return {
            "url": f"https://media.example.test/{item_id}.flac",
            "sampling_rate": 96,
            "bit_depth": 24,
        }


def _rename_tag(filename, root_dir, final_file, *args):
    os.replace(filename, final_file)


def _album_directory(root):
    return root / "Album Artist - Album Title (2024) [24B-96kHz]"


def _track_directory(root):
    return root / "Album Artist - Track Album (2024) [24B-96kHz]"


def test_only_audio_downloads_enable_rate_limit_retry(tmp_path, monkeypatch):
    calls = []

    def fake_download_with_progress(
        url, target, description, *, retry_rate_limited=False
    ):
        calls.append((url, retry_rate_limited))
        Path(target).write_bytes(b"downloaded bytes")

    monkeypatch.setattr(
        downloader, "download_with_progress", fake_download_with_progress
    )
    monkeypatch.setattr(downloader.metadata, "tag_flac", _rename_tag)

    result = downloader.Download(
        DownloadClient(),
        "album-1",
        str(tmp_path),
        27,
    ).download_release()

    assert result.state == "finalized"
    assert calls == [
        ("https://img.example.test/cover.jpg", False),
        ("https://img.example.test/booklet.pdf", False),
        ("https://media.example.test/track-1.flac", True),
    ]


@pytest.mark.parametrize("rate_limit", [_returned_429, _raised_429])
def test_media_429_then_success_matches_a_direct_download(
    tmp_path, monkeypatch, rate_limit
):
    direct_target = tmp_path / "direct.flac"
    retried_target = tmp_path / "retried.flac"
    direct_progress = []
    retried_progress = []
    direct = StreamResponse(headers={"content-length": "6"}, reads=[b"abc", b"def"])
    direct_requests, direct_remaining = _install_urlopen_sequence(monkeypatch, [direct])

    direct_count = http.stream_download(
        "https://media.example.test/track.flac",
        direct_target,
        chunk_size=3,
        progress=lambda size, downloaded, total: direct_progress.append(
            (size, downloaded, total)
        ),
    )

    rejected, rejected_resource = rate_limit()
    accepted = StreamResponse(headers={"content-length": "6"}, reads=[b"abc", b"def"])
    retried_requests, retried_remaining = _install_urlopen_sequence(
        monkeypatch, [rejected, accepted]
    )
    retried_count = _stream_media(
        "https://media.example.test/track.flac",
        retried_target,
        chunk_size=3,
        progress=lambda size, downloaded, total: retried_progress.append(
            (size, downloaded, total)
        ),
    )

    assert retried_target.read_bytes() == direct_target.read_bytes() == b"abcdef"
    assert retried_count == direct_count == 6
    assert retried_progress == direct_progress == [(3, 3, 6), (3, 6, 6)]
    assert len(direct_requests) == 1
    assert len(retried_requests) == 2
    assert direct_remaining == []
    assert retried_remaining == []
    assert rejected_resource.read_calls == 0
    assert rejected_resource.closed is True


def test_direct_stream_download_does_not_retry_a_returned_429(tmp_path, monkeypatch):
    target = tmp_path / "direct.flac"
    rejected, _resource = _returned_429()
    unused = StreamResponse(reads=[b"must not be used"])
    requests, remaining = _install_urlopen_sequence(monkeypatch, [rejected, unused])

    with pytest.raises(http.HttpStatusError) as exc_info:
        http.stream_download("https://media.example.test/track.flac", target)

    assert exc_info.value.status_code == 429
    assert len(requests) == 1
    assert remaining == [unused]
    assert not target.exists()


@pytest.mark.parametrize(
    ("reads", "expected_bytes"),
    [
        ([OSError("failed before the first byte")], b""),
        ([b"first response", OSError("stream interrupted")], b"first response"),
    ],
)
def test_accepted_stream_failure_never_retries_or_mixes_responses(
    tmp_path, monkeypatch, reads, expected_bytes
):
    target = tmp_path / "track.flac"
    failed = StreamResponse(reads=reads)
    fallback = StreamResponse(reads=[b"second response"])
    requests, remaining = _install_urlopen_sequence(monkeypatch, [failed, fallback])

    with pytest.raises(http.HttpRequestError, match="failed|interrupted"):
        _stream_media("https://media.example.test/track.flac", target)

    assert target.read_bytes() == expected_bytes
    assert len(requests) == 1
    assert remaining == [fallback]
    assert all(
        name.lower() != "range"
        for request in requests
        for name, _value in request.header_items()
    )


def test_progress_failure_that_looks_like_429_does_not_retry(tmp_path, monkeypatch):
    target = tmp_path / "track.flac"
    accepted = StreamResponse(reads=[b"accepted bytes"])
    fallback = StreamResponse(reads=[b"must not be used"])
    requests, remaining = _install_urlopen_sequence(monkeypatch, [accepted, fallback])
    callback_error = http.HttpStatusError(429, b"callback sentinel")

    def fail_progress(size, downloaded, total):
        raise callback_error

    with pytest.raises(http.HttpStatusError) as exc_info:
        _stream_media(
            "https://media.example.test/track.flac",
            target,
            progress=fail_progress,
        )

    assert exc_info.value is callback_error
    assert target.read_bytes() == b"accepted bytes"
    assert len(requests) == 1
    assert remaining == [fallback]


def test_write_failure_after_response_acceptance_does_not_retry(tmp_path, monkeypatch):
    target = tmp_path / "track.flac"
    accepted = StreamResponse(reads=[b"accepted bytes"])
    fallback = StreamResponse(reads=[b"must not be used"])
    requests, remaining = _install_urlopen_sequence(monkeypatch, [accepted, fallback])
    real_open = open

    class FailingWriter:
        def __init__(self):
            self.file = real_open(target, "wb")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            self.file.close()
            return False

        def write(self, chunk):
            raise OSError("target write failed")

    def fail_target_open(path, mode):
        assert Path(path) == target
        assert mode == "wb"
        return FailingWriter()

    monkeypatch.setattr("builtins.open", fail_target_open)

    with pytest.raises(http.HttpRequestError, match="target write failed"):
        _stream_media("https://media.example.test/track.flac", target)

    assert target.read_bytes() == b""
    assert len(requests) == 1
    assert remaining == [fallback]


def test_accepted_response_close_failure_does_not_retry(tmp_path, monkeypatch):
    target = tmp_path / "track.flac"
    accepted = StreamResponse(
        reads=[b"accepted bytes"],
        close_error=OSError("response close failed"),
    )
    fallback = StreamResponse(reads=[b"must not be used"])
    requests, remaining = _install_urlopen_sequence(monkeypatch, [accepted, fallback])

    with pytest.raises(http.HttpRequestError, match="response close failed"):
        _stream_media("https://media.example.test/track.flac", target)

    assert target.read_bytes() == b"accepted bytes"
    assert accepted.closed is True
    assert len(requests) == 1
    assert remaining == [fallback]


@pytest.mark.parametrize(
    "response",
    [
        StreamResponse(headers={"content-length": "5"}, reads=[b"abc"]),
        StreamResponse(reads=[b"abc", OSError("stream interrupted")]),
    ],
    ids=["content-length", "stream-read"],
)
def test_media_integrity_errors_clean_owned_files_without_retry(
    tmp_path, monkeypatch, response
):
    requests, remaining = _install_urlopen_sequence(
        monkeypatch,
        [response, StreamResponse(reads=[b"must not be used"])],
    )
    monkeypatch.setattr(downloader.metadata, "tag_flac", _rename_tag)

    result = downloader.Download(
        DownloadClient(),
        "track-1",
        str(tmp_path),
        27,
        no_cover=True,
    ).download_track()

    directory = _track_directory(tmp_path)
    assert result.state == "failed"
    assert result.reason == "request_error"
    assert len(requests) == 1
    assert len(remaining) == 1
    assert not list(directory.glob(".*.tmp"))
    assert not list(directory.glob("*.flac"))


def test_media_retry_exhaustion_is_an_ordinary_partial_download_result(
    tmp_path, monkeypatch
):
    tracks = [
        _track("track-1", "Opening", 1),
        _track("track-2", "Finale", 2),
    ]
    first = StreamResponse(headers={"content-length": "5"}, reads=[b"first"])
    attempts = [_returned_429() for _attempt in range(3)]
    rejected = [outcome for outcome, _resource in attempts]
    requests, remaining = _install_urlopen_sequence(monkeypatch, [first, *rejected])
    monkeypatch.setattr(downloader.metadata, "tag_flac", _rename_tag)
    database = tmp_path / "downloads.sqlite"
    qdl = QobuzDL(
        directory=tmp_path / "music",
        quality=27,
        no_cover=True,
        downloads_db=database,
    )
    client = DownloadClient(tracks=tracks)
    client.album_meta.pop("goodies")
    qdl.client = client

    result = qdl.download_from_id("album-1", album=True)

    directory = _album_directory(tmp_path / "music")
    first_final = directory / "01. Opening.flac"
    second_final = directory / "02. Finale.flac"
    assert result.state == "failed"
    assert result.reason == "request_error"
    assert result.finalized_paths == (str(first_final),)
    assert first_final.read_bytes() == b"first"
    assert not second_final.exists()
    assert not list(directory.glob(".*.tmp"))
    assert handle_download_id(database, "album-1") is None
    assert [request.full_url for request in requests] == [
        "https://media.example.test/track-1.flac",
        "https://media.example.test/track-2.flac",
        "https://media.example.test/track-2.flac",
        "https://media.example.test/track-2.flac",
    ]
    assert remaining == []
    assert all(resource.closed for _outcome, resource in attempts)
    assert all(resource.read_calls == 0 for _outcome, resource in attempts)


def test_media_retry_cancellation_leaves_no_final_or_temporary_file(
    tmp_path, monkeypatch
):
    rejected, resource = _returned_429()
    interrupt = KeyboardInterrupt("retry cancelled")
    requests, remaining = _install_urlopen_sequence(monkeypatch, [rejected, interrupt])
    database = tmp_path / "downloads.sqlite"
    qdl = QobuzDL(
        directory=tmp_path / "music",
        quality=27,
        no_cover=True,
        downloads_db=database,
    )
    qdl.client = DownloadClient()

    with pytest.raises(KeyboardInterrupt, match="retry cancelled"):
        qdl.download_from_id("track-1", album=False)

    directory = _track_directory(tmp_path / "music")
    assert len(requests) == 2
    assert remaining == []
    assert not list(directory.glob(".*.tmp"))
    assert not list(directory.glob("*.flac"))
    assert handle_download_id(database, "track-1") is None
    assert resource.closed is True
    assert resource.read_calls == 0


def test_media_acquisition_failure_preserves_a_preexisting_direct_target(
    tmp_path, monkeypatch
):
    target = tmp_path / "existing.flac"
    target.write_bytes(b"existing complete bytes")
    attempts = [_returned_429() for _attempt in range(3)]
    rejected = [outcome for outcome, _resource in attempts]
    requests, remaining = _install_urlopen_sequence(monkeypatch, rejected)

    with pytest.raises(http.HttpRateLimitError) as exc_info:
        _stream_media("https://media.example.test/track.flac", target)

    assert exc_info.type.__name__ == "HttpRateLimitError"
    assert "media.example.test" not in str(exc_info.value)
    assert target.read_bytes() == b"existing complete bytes"
    assert len(requests) == 3
    assert remaining == []
    assert all(resource.closed for _outcome, resource in attempts)
    assert all(resource.read_calls == 0 for _outcome, resource in attempts)
