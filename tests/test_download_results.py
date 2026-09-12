import os
from pathlib import Path

import pytest

from qobuz_dl import downloader
from qobuz_dl.core import QobuzDL
from qobuz_dl.db import handle_download_id
from qobuz_dl.downloader import (
    Download,
    DownloadResult,
    _aggregate_download_results,
)


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


def _album_meta(*, tracks=None, release_type="album"):
    items = tracks if tracks is not None else [_track()]
    return {
        "id": "album-1",
        "streamable": True,
        "release_type": release_type,
        "title": "Album Title",
        "artist": {"name": "Album Artist"},
        "release_date_original": "2024-02-03",
        "image": {"large": "https://img.example.test/cover.jpg"},
        "tracks": {"items": items},
        "tracks_count": len(items),
        "genres_list": ["Rock"],
        "label": {"name": "Label"},
        "copyright": "",
    }


def _track_meta(track_id="track-1", title="Single Track", track_number=1):
    return {
        **_track(track_id, title, track_number),
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


def _available_url(track_id):
    return {
        "url": f"https://media.example.test/{track_id}.flac",
        "sampling_rate": 96,
        "bit_depth": 24,
    }


class MutableDownloadClient:
    def __init__(self, *, album_meta=None, track_meta=None):
        self.album_meta = album_meta if album_meta is not None else _album_meta()
        self.track_meta = track_meta if track_meta is not None else _track_meta()
        self.track_urls = {}

    def get_album_meta(self, item_id):
        assert item_id == self.album_meta["id"]
        return self.album_meta

    def get_track_meta(self, item_id):
        assert item_id == self.track_meta["id"]
        return self.track_meta

    def get_track_url(self, item_id, fmt_id):
        assert fmt_id == 27
        return self.track_urls.get(item_id, _available_url(item_id))


def _install_file_boundaries(monkeypatch, *, tagging_fails=None):
    transferred = []
    tagging_fails = tagging_fails if tagging_fails is not None else set()

    def fake_stream_download(url, target_path, *, progress=None):
        track_id = Path(url).stem
        transferred.append(track_id)
        Path(target_path).write_bytes(f"audio:{track_id}".encode())

    def fake_tag(filename, root_dir, final_file, track_metadata, *args):
        if track_metadata["id"] in tagging_fails:
            raise RuntimeError(f"cannot tag {track_metadata['id']}")
        os.replace(filename, final_file)

    monkeypatch.setattr(downloader.http, "stream_download", fake_stream_download)
    monkeypatch.setattr(downloader.metadata, "tag_flac", fake_tag)
    return transferred


def _assert_result(result, state, reason, finalized_paths=()):
    assert result is not None, f"expected {state}/{reason}, got no download result"
    assert result.state == state
    assert result.reason == reason
    assert result.finalized_paths == tuple(str(path) for path in finalized_paths)


def _completed_messages(caplog):
    return [
        record.getMessage()
        for record in caplog.records
        if "Completed" in record.getMessage()
    ]


@pytest.mark.parametrize(
    ("cause", "album", "expected_reason"),
    [
        ("type_filter", True, "type_filter"),
        ("quality_filter", True, "quality_filter"),
        ("demo", False, "demo"),
        ("missing_url", False, "missing_url"),
        ("tagging_failure", False, "tagging_error"),
    ],
)
def test_incomplete_download_is_not_recorded_and_retries_after_correction(
    tmp_path, monkeypatch, caplog, cause, album, expected_reason
):
    item_id = "album-1" if album else "track-1"
    client = MutableDownloadClient()
    tagging_fails = set()
    transferred = _install_file_boundaries(
        monkeypatch,
        tagging_fails=tagging_fails,
    )
    kwargs = {
        "directory": tmp_path / "music",
        "quality": 27,
        "no_cover": True,
        "downloads_db": tmp_path / "downloads.sqlite",
    }

    if cause == "type_filter":
        client.album_meta["release_type"] = "single"
        kwargs["ignore_singles_eps"] = True
    elif cause == "quality_filter":
        client.track_urls["track-1"] = {
            **_available_url("track-1"),
            "restrictions": [{"code": downloader.QL_DOWNGRADE}],
        }
        kwargs["quality_fallback"] = False
    elif cause == "demo":
        client.track_urls["track-1"] = {
            **_available_url("track-1"),
            "sample": True,
        }
    elif cause == "missing_url":
        client.track_urls["track-1"] = {"sampling_rate": 96, "bit_depth": 24}
    else:
        tagging_fails.add("track-1")

    qdl = QobuzDL(**kwargs)
    qdl.client = client
    caplog.set_level("INFO", logger="qobuz_dl.downloader")

    incomplete = qdl.download_from_id(item_id, album=album)

    _assert_result(
        incomplete,
        "ignored" if cause.endswith("filter") or cause == "demo" else "failed",
        expected_reason,
    )
    assert handle_download_id(qdl.downloads_db, item_id) is None
    assert _completed_messages(caplog) == []

    client.album_meta["release_type"] = "album"
    client.track_urls["track-1"] = _available_url("track-1")
    tagging_fails.clear()
    caplog.clear()

    completed = qdl.download_from_id(item_id, album=album)

    folder = (
        "Album Artist - Album Title (2024) [24B-96kHz]"
        if album
        else "Album Artist - Track Album (2024) [24B-96kHz]"
    )
    final_path = tmp_path / "music" / folder / "01. Single Track.flac"
    _assert_result(completed, "finalized", "downloaded", (final_path,))
    assert final_path.read_bytes() == b"audio:track-1"
    assert handle_download_id(qdl.downloads_db, item_id) == (item_id,)
    assert transferred[-1] == "track-1"
    assert len(_completed_messages(caplog)) == 1


def test_partial_album_reuses_finalized_track_and_records_only_completed_retry(
    tmp_path, monkeypatch, caplog
):
    tracks = [
        _track("track-1", "Opening", 1),
        _track("track-2", "Finale", 2),
    ]
    client = MutableDownloadClient(album_meta=_album_meta(tracks=tracks))
    tagging_fails = {"track-2"}
    transferred = _install_file_boundaries(
        monkeypatch,
        tagging_fails=tagging_fails,
    )
    qdl = QobuzDL(
        directory=tmp_path / "music",
        quality=27,
        no_cover=True,
        downloads_db=tmp_path / "downloads.sqlite",
    )
    qdl.client = client
    caplog.set_level("INFO", logger="qobuz_dl.downloader")
    album_dir = tmp_path / "music" / "Album Artist - Album Title (2024) [24B-96kHz]"
    first_path = album_dir / "01. Opening.flac"
    second_path = album_dir / "02. Finale.flac"

    incomplete = qdl.download_from_id("album-1", album=True)

    assert first_path.read_bytes() == b"audio:track-1"
    assert not second_path.exists()
    assert transferred == ["track-1", "track-2"]
    assert handle_download_id(qdl.downloads_db, "album-1") is None
    _assert_result(incomplete, "failed", "tagging_error", (first_path,))
    assert _completed_messages(caplog) == []

    tagging_fails.clear()
    caplog.clear()

    completed = qdl.download_from_id("album-1", album=True)

    _assert_result(
        completed,
        "finalized",
        "downloaded",
        (first_path, second_path),
    )
    assert first_path.read_bytes() == b"audio:track-1"
    assert second_path.read_bytes() == b"audio:track-2"
    assert transferred == ["track-1", "track-2", "track-2"]
    assert handle_download_id(qdl.downloads_db, "album-1") == ("album-1",)
    assert len(_completed_messages(caplog)) == 1


@pytest.mark.parametrize("failure_point", ["url_request", "media_stream"])
def test_partial_album_request_failure_retains_paths_and_stops(
    tmp_path, monkeypatch, caplog, failure_point
):
    tracks = [
        _track("track-1", "Opening", 1),
        _track("track-2", "Interlude", 2),
        _track("track-3", "Finale", 3),
    ]
    client = MutableDownloadClient(album_meta=_album_meta(tracks=tracks))
    transferred = _install_file_boundaries(monkeypatch)
    requested = []
    get_track_url = client.get_track_url

    def failing_track_url(track_id, fmt_id):
        requested.append(track_id)
        if failure_point == "url_request" and track_id == "track-2":
            raise downloader.http.HttpRequestError("request failed")
        return get_track_url(track_id, fmt_id)

    client.get_track_url = failing_track_url
    if failure_point == "media_stream":

        def failing_stream(url, target_path, *, progress=None):
            track_id = Path(url).stem
            transferred.append(track_id)
            Path(target_path).write_bytes(f"audio:{track_id}".encode())
            if track_id == "track-2":
                raise ConnectionError("stream failed")

        monkeypatch.setattr(downloader.http, "stream_download", failing_stream)

    qdl = QobuzDL(
        directory=tmp_path / "music",
        quality=27,
        no_cover=True,
        downloads_db=tmp_path / "downloads.sqlite",
    )
    qdl.client = client
    caplog.set_level("INFO", logger="qobuz_dl.downloader")
    album_dir = tmp_path / "music" / "Album Artist - Album Title (2024) [24B-96kHz]"
    first_path = album_dir / "01. Opening.flac"

    result = qdl.download_from_id("album-1", album=True)

    _assert_result(result, "failed", "request_error", (first_path,))
    assert first_path.read_bytes() == b"audio:track-1"
    assert "track-3" not in requested
    assert transferred == (
        ["track-1"] if failure_point == "url_request" else ["track-1", "track-2"]
    )
    assert handle_download_id(qdl.downloads_db, "album-1") is None
    assert not list(album_dir.glob(".*.tmp"))
    assert _completed_messages(caplog) == []


def test_empty_album_is_ignored_without_history_or_completed_message(tmp_path, caplog):
    client = MutableDownloadClient(album_meta=_album_meta(tracks=[]))
    qdl = QobuzDL(
        directory=tmp_path / "music",
        quality=27,
        no_cover=True,
        downloads_db=tmp_path / "downloads.sqlite",
    )
    qdl.client = client
    caplog.set_level("INFO", logger="qobuz_dl.downloader")

    result = qdl.download_from_id("album-1", album=True)

    _assert_result(result, "ignored", "empty_release")
    assert handle_download_id(qdl.downloads_db, "album-1") is None
    assert _completed_messages(caplog) == []


def test_database_duplicate_is_ignored_without_fabricated_paths(tmp_path, caplog):
    db_path = tmp_path / "downloads.sqlite"
    qdl = QobuzDL(
        directory=tmp_path / "music",
        downloads_db=db_path,
    )
    handle_download_id(db_path, "album-1", add_id=True)
    qdl.client = object()
    caplog.set_level("INFO")

    result = qdl.download_from_id("album-1", album=True)

    _assert_result(result, "ignored", "database_duplicate")
    assert _completed_messages(caplog) == []


@pytest.mark.parametrize("track", [True, False])
def test_public_downloader_dispatch_returns_exact_child_result(
    tmp_path, monkeypatch, track
):
    expected = object()
    download = Download(object(), "item-1", str(tmp_path), 27)
    monkeypatch.setattr(download, "download_track", lambda: expected)
    monkeypatch.setattr(download, "download_release", lambda: expected)

    assert download.download_id_by_type(track=track) is expected


def test_noop_tagger_is_failed_without_final_file(tmp_path, monkeypatch, caplog):
    transferred = _install_file_boundaries(monkeypatch)
    monkeypatch.setattr(downloader.metadata, "tag_flac", lambda *args: None)
    caplog.set_level("INFO", logger="qobuz_dl.downloader")

    result = Download(
        MutableDownloadClient(),
        "track-1",
        str(tmp_path),
        27,
        no_cover=True,
    ).download_track()

    _assert_result(result, "failed", "tagging_error")
    assert transferred == ["track-1"]
    assert not list(tmp_path.rglob("*.flac"))
    assert not list(tmp_path.rglob(".*.tmp"))
    assert _completed_messages(caplog) == []


@pytest.mark.parametrize(
    ("children", "state", "reason", "paths"),
    [
        (
            [
                DownloadResult("finalized", "existing_file", ("first.flac",)),
                DownloadResult("finalized", "downloaded", ("second.flac",)),
            ],
            "finalized",
            "downloaded",
            ("first.flac", "second.flac"),
        ),
        (
            [
                DownloadResult("finalized", "downloaded", ("first.flac",)),
                DownloadResult("ignored", "demo"),
                DownloadResult("finalized", "existing_file", ("third.flac",)),
            ],
            "ignored",
            "demo",
            ("first.flac", "third.flac"),
        ),
        (
            [
                DownloadResult("ignored", "demo"),
                DownloadResult("failed", "missing_url"),
                DownloadResult("failed", "tagging_error"),
            ],
            "failed",
            "missing_url",
            (),
        ),
        (
            [
                DownloadResult("finalized", "existing_file", ("first.flac",)),
                DownloadResult("finalized", "existing_file", ("second.flac",)),
            ],
            "finalized",
            "existing_file",
            ("first.flac", "second.flac"),
        ),
    ],
)
def test_album_result_aggregation_preserves_order_and_blocking_precedence(
    children, state, reason, paths
):
    _assert_result(_aggregate_download_results(children), state, reason, paths)
