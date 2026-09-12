import os
import sqlite3
from pathlib import Path

import pytest

from qobuz_dl import downloader
from qobuz_dl.color import OFF, RESET
from qobuz_dl.core import QobuzDL
from qobuz_dl.downloader import DownloadResult


def _track(track_id, title, track_number):
    return {
        "id": track_id,
        "title": title,
        "performer": {"name": "Track Artist"},
        "album": {"artist": {"name": "Album Artist"}},
        "maximum_bit_depth": 24,
        "maximum_sampling_rate": 192,
        "track_number": track_number,
        "media_number": 1,
        "version": None,
    }


TRACKS = [
    _track("track-1", "Opening", 1),
    _track("track-2", "Interlude", 2),
    _track("track-3", "Finale", 3),
]


def _album_meta(tracks=TRACKS):
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
    }


def _track_meta():
    return {
        **TRACKS[1],
        "album": {
            "id": "album-1",
            "title": "Album Title",
            "artist": {"name": "Album Artist"},
            "release_date_original": "2024-02-03",
            "image": {"large": "https://img.example.test/cover.jpg"},
            "tracks_count": 3,
            "genres_list": ["Rock"],
        },
        "copyright": "",
    }


def _track_url(
    track_id,
    *,
    bit_depth=24,
    sampling_rate=192,
    restricted=False,
    extension="flac",
):
    response = {
        "url": f"https://media.example.test/{track_id}.{extension}",
        "bit_depth": bit_depth,
        "sampling_rate": sampling_rate,
    }
    if restricted:
        response["restrictions"] = [{"code": downloader.QL_DOWNGRADE}]
    return response


class RecordingClient:
    def __init__(self, responses, *, tracks=TRACKS):
        self.album_meta = _album_meta(tracks)
        self.track_meta = _track_meta()
        self.responses = responses
        self.track_url_calls = []

    def get_album_meta(self, item_id):
        assert item_id == "album-1"
        return self.album_meta

    def get_track_meta(self, item_id):
        assert item_id == "track-2"
        return self.track_meta

    def get_track_url(self, item_id, fmt_id):
        self.track_url_calls.append((item_id, fmt_id))
        return self.responses[item_id]


def _install_media_boundaries(monkeypatch):
    transferred = []

    def stream_download(url, target_path, *, progress=None):
        track_id = Path(url).stem
        transferred.append(track_id)
        Path(target_path).write_bytes(f"audio:{track_id}".encode())

    def tag(filename, root_dir, final_file, *args):
        os.replace(filename, final_file)

    monkeypatch.setattr(downloader.http, "stream_download", stream_download)
    monkeypatch.setattr(downloader.metadata, "tag_flac", tag)
    monkeypatch.setattr(downloader.metadata, "tag_mp3", tag)
    return transferred


def _qobuz(tmp_path, client, *, quality=27, quality_fallback=False):
    qdl = QobuzDL(
        directory=tmp_path / "music",
        quality=quality,
        quality_fallback=quality_fallback,
        no_cover=True,
        downloads_db=tmp_path / "downloads.sqlite",
    )
    qdl.client = client
    return qdl


def _history_ids(database):
    with sqlite3.connect(database) as connection:
        return [row[0] for row in connection.execute("SELECT id FROM downloads")]


def _plain_messages(caplog):
    return [
        record.getMessage().removeprefix(OFF).removesuffix(RESET)
        for record in caplog.records
    ]


def _track_quality_messages(caplog):
    return [
        message
        for message in _plain_messages(caplog)
        if message.startswith("Track quality:")
    ]


def test_first_refusal_continues_to_later_admissible_track(
    tmp_path, monkeypatch, caplog
):
    client = RecordingClient(
        {
            "track-1": _track_url("track-1", restricted=True),
            "track-2": _track_url("track-2", sampling_rate=96),
        },
        tracks=TRACKS[:2],
    )
    transferred = _install_media_boundaries(monkeypatch)
    qdl = _qobuz(tmp_path, client)
    caplog.set_level("INFO", logger="qobuz_dl.downloader")
    album_dir = tmp_path / "music/Album Artist - Album Title (2024) [24B-192kHz]"
    first_path = album_dir / "01. Opening.flac"
    second_path = album_dir / "02. Interlude.flac"

    result = qdl.download_from_id("album-1", album=True)

    assert result == DownloadResult("ignored", "quality_filter", (str(second_path),))
    assert client.track_url_calls == [("track-1", 27), ("track-2", 27)]
    assert transferred == ["track-2"]
    assert not first_path.exists()
    assert second_path.read_bytes() == b"audio:track-2"
    assert _history_ids(qdl.downloads_db) == []
    assert _track_quality_messages(caplog) == ["Track quality: 24-bit/96 kHz"]
    assert "Skipping Opening as it doesn't meet quality requirement" in _plain_messages(
        caplog
    )
    assert not any(message.endswith("Completed") for message in _plain_messages(caplog))


def test_later_refusal_continues_and_retry_downloads_only_missing_track(
    tmp_path, monkeypatch, caplog
):
    responses = {
        "track-1": _track_url("track-1"),
        "track-2": _track_url(
            "track-2", bit_depth=16, sampling_rate=44.1, restricted=True
        ),
        "track-3": _track_url("track-3", sampling_rate=96),
    }
    client = RecordingClient(responses)
    transferred = _install_media_boundaries(monkeypatch)
    qdl = _qobuz(tmp_path, client)
    caplog.set_level("INFO", logger="qobuz_dl.downloader")
    album_dir = tmp_path / "music/Album Artist - Album Title (2024) [24B-192kHz]"
    paths = (
        album_dir / "01. Opening.flac",
        album_dir / "02. Interlude.flac",
        album_dir / "03. Finale.flac",
    )

    incomplete = qdl.download_from_id("album-1", album=True)

    assert incomplete == DownloadResult(
        "ignored", "quality_filter", (str(paths[0]), str(paths[2]))
    )
    assert client.track_url_calls == [
        ("track-1", 27),
        ("track-2", 27),
        ("track-3", 27),
    ]
    assert transferred == ["track-1", "track-3"]
    assert paths[0].read_bytes() == b"audio:track-1"
    assert not paths[1].exists()
    assert paths[2].read_bytes() == b"audio:track-3"
    assert _history_ids(qdl.downloads_db) == []
    assert _track_quality_messages(caplog) == [
        "Track quality: 24-bit/192 kHz",
        "Track quality: 24-bit/96 kHz",
    ]
    assert (
        "Skipping Interlude as it doesn't meet quality requirement"
        in _plain_messages(caplog)
    )
    assert not any(message.endswith("Completed") for message in _plain_messages(caplog))

    responses["track-2"] = _track_url("track-2", bit_depth=16, sampling_rate=44.1)
    caplog.clear()

    completed = qdl.download_from_id("album-1", album=True)

    assert completed == DownloadResult(
        "finalized", "downloaded", tuple(str(path) for path in paths)
    )
    assert client.track_url_calls == [
        ("track-1", 27),
        ("track-2", 27),
        ("track-3", 27),
        ("track-1", 27),
        ("track-2", 27),
        ("track-3", 27),
    ]
    assert transferred == ["track-1", "track-3", "track-2"]
    assert [path.read_bytes() for path in paths] == [
        b"audio:track-1",
        b"audio:track-2",
        b"audio:track-3",
    ]
    assert _history_ids(qdl.downloads_db) == ["album-1"]
    assert _track_quality_messages(caplog) == [
        "Track quality: 24-bit/192 kHz",
        "Track quality: 16-bit/44.1 kHz",
        "Track quality: 24-bit/96 kHz",
    ]
    assert (
        sum(message.endswith("Completed") for message in _plain_messages(caplog)) == 1
    )


def test_allowed_downgrade_logs_each_returned_quality(tmp_path, monkeypatch, caplog):
    client = RecordingClient(
        {
            "track-1": _track_url("track-1"),
            "track-2": _track_url(
                "track-2", bit_depth=16, sampling_rate=44.1, restricted=True
            ),
            "track-3": _track_url("track-3", sampling_rate=96),
        }
    )
    transferred = _install_media_boundaries(monkeypatch)
    qdl = _qobuz(tmp_path, client, quality_fallback=True)
    caplog.set_level("INFO", logger="qobuz_dl.downloader")
    album_dir = tmp_path / "music/Album Artist - Album Title (2024) [24B-192kHz]"
    paths = tuple(
        album_dir / f"0{index}. {title}.flac"
        for index, title in enumerate(("Opening", "Interlude", "Finale"), start=1)
    )

    result = qdl.download_from_id("album-1", album=True)

    assert result == DownloadResult(
        "finalized", "downloaded", tuple(str(path) for path in paths)
    )
    assert transferred == ["track-1", "track-2", "track-3"]
    assert [path.read_bytes() for path in paths] == [
        b"audio:track-1",
        b"audio:track-2",
        b"audio:track-3",
    ]
    assert _history_ids(qdl.downloads_db) == ["album-1"]
    assert _track_quality_messages(caplog) == [
        "Track quality: 24-bit/192 kHz",
        "Track quality: 16-bit/44.1 kHz",
        "Track quality: 24-bit/96 kHz",
    ]
    assert client.track_url_calls == [
        ("track-1", 27),
        ("track-2", 27),
        ("track-3", 27),
    ]


@pytest.mark.parametrize("missing_field", ["bit_depth", "sampling_rate"])
def test_album_logs_unknown_when_returned_quality_is_incomplete(
    tmp_path, monkeypatch, caplog, missing_field
):
    unknown_response = _track_url("track-2", bit_depth=16, sampling_rate=44.1)
    unknown_response.pop(missing_field)
    client = RecordingClient(
        {
            "track-1": _track_url("track-1"),
            "track-2": unknown_response,
        },
        tracks=TRACKS[:2],
    )
    transferred = _install_media_boundaries(monkeypatch)
    qdl = _qobuz(tmp_path, client)
    caplog.set_level("INFO", logger="qobuz_dl.downloader")

    result = qdl.download_from_id("album-1", album=True)

    album_dir = tmp_path / "music/Album Artist - Album Title (2024) [24B-192kHz]"
    paths = (
        album_dir / "01. Opening.flac",
        album_dir / "02. Interlude.flac",
    )
    assert result == DownloadResult(
        "finalized", "downloaded", tuple(str(path) for path in paths)
    )
    assert transferred == ["track-1", "track-2"]
    assert _track_quality_messages(caplog) == [
        "Track quality: 24-bit/192 kHz",
        "Track quality: unknown",
    ]
    assert client.track_url_calls == [("track-1", 27), ("track-2", 27)]


def test_demo_response_has_no_track_quality_log_or_history(
    tmp_path, monkeypatch, caplog
):
    demo_response = _track_url("track-2", bit_depth=16, sampling_rate=44.1)
    demo_response["sample"] = True
    client = RecordingClient(
        {
            "track-1": _track_url("track-1"),
            "track-2": demo_response,
        },
        tracks=TRACKS[:2],
    )
    transferred = _install_media_boundaries(monkeypatch)
    qdl = _qobuz(tmp_path, client)
    caplog.set_level("INFO", logger="qobuz_dl.downloader")
    first_path = (
        tmp_path
        / "music/Album Artist - Album Title (2024) [24B-192kHz]"
        / "01. Opening.flac"
    )

    result = qdl.download_from_id("album-1", album=True)

    assert result == DownloadResult("ignored", "demo", (str(first_path),))
    assert transferred == ["track-1"]
    assert first_path.read_bytes() == b"audio:track-1"
    assert _history_ids(qdl.downloads_db) == []
    assert _track_quality_messages(caplog) == ["Track quality: 24-bit/192 kHz"]
    assert "Demo. Skipping" in _plain_messages(caplog)
    assert client.track_url_calls == [("track-1", 27), ("track-2", 27)]


def test_empty_first_response_is_reused_without_quality_or_history(
    tmp_path, monkeypatch, caplog
):
    client = RecordingClient({"track-1": {}}, tracks=TRACKS[:1])
    transferred = _install_media_boundaries(monkeypatch)
    qdl = _qobuz(tmp_path, client)
    caplog.set_level("INFO", logger="qobuz_dl.downloader")

    result = qdl.download_from_id("album-1", album=True)

    assert result == DownloadResult("failed", "missing_url")
    assert client.track_url_calls == [("track-1", 27)]
    assert transferred == []
    assert list((tmp_path / "music").rglob("*")) == [
        tmp_path / "music/Album Artist - Album Title"
    ]
    assert _history_ids(qdl.downloads_db) == []
    assert _track_quality_messages(caplog) == []
    assert "Track not available for download" in _plain_messages(caplog)


def test_all_restricted_flac_tracks_are_refused_without_transfers(
    tmp_path, monkeypatch, caplog
):
    client = RecordingClient(
        {
            "track-1": _track_url("track-1", restricted=True),
            "track-2": _track_url("track-2", restricted=True),
            "track-3": _track_url("track-3", restricted=True),
        }
    )
    transferred = _install_media_boundaries(monkeypatch)
    qdl = _qobuz(tmp_path, client)
    caplog.set_level("INFO", logger="qobuz_dl.downloader")

    result = qdl.download_from_id("album-1", album=True)

    assert result == DownloadResult("ignored", "quality_filter")
    assert client.track_url_calls == [
        ("track-1", 27),
        ("track-2", 27),
        ("track-3", 27),
    ]
    assert transferred == []
    assert not list((tmp_path / "music").rglob("*.flac"))
    assert _history_ids(qdl.downloads_db) == []
    assert _track_quality_messages(caplog) == []
    messages = _plain_messages(caplog)
    for title in ("Opening", "Interlude", "Finale"):
        assert f"Skipping {title} as it doesn't meet quality requirement" in messages


def test_mp3_album_keeps_lazy_per_track_requests_and_ignores_restrictions(
    tmp_path, monkeypatch, caplog
):
    client = RecordingClient(
        {
            track["id"]: _track_url(track["id"], restricted=True, extension="mp3")
            for track in TRACKS
        }
    )
    transferred = _install_media_boundaries(monkeypatch)
    qdl = _qobuz(tmp_path, client, quality=5)
    caplog.set_level("INFO", logger="qobuz_dl.downloader")
    album_dir = tmp_path / "music/Album Artist - Album Title (2024) [MP3]"
    paths = (
        album_dir / "01. Opening.mp3",
        album_dir / "02. Interlude.mp3",
        album_dir / "03. Finale.mp3",
    )

    result = qdl.download_from_id("album-1", album=True)

    assert result == DownloadResult(
        "finalized", "downloaded", tuple(str(path) for path in paths)
    )
    assert client.track_url_calls == [
        ("track-1", 5),
        ("track-2", 5),
        ("track-3", 5),
    ]
    assert transferred == ["track-1", "track-2", "track-3"]
    assert [path.read_bytes() for path in paths] == [
        b"audio:track-1",
        b"audio:track-2",
        b"audio:track-3",
    ]
    assert _history_ids(qdl.downloads_db) == ["album-1"]
    assert not any(
        "doesn't meet quality requirement" in message
        for message in _plain_messages(caplog)
    )


@pytest.mark.parametrize(
    ("quality_fallback", "state", "reason", "transferred", "history"),
    [
        (False, "ignored", "quality_filter", [], []),
        (True, "finalized", "downloaded", ["track-2"], ["track-2"]),
    ],
)
def test_direct_track_fallback_behavior_is_unchanged(
    tmp_path,
    monkeypatch,
    caplog,
    quality_fallback,
    state,
    reason,
    transferred,
    history,
):
    client = RecordingClient(
        {
            "track-2": _track_url(
                "track-2", bit_depth=16, sampling_rate=44.1, restricted=True
            )
        }
    )
    actual_transfers = _install_media_boundaries(monkeypatch)
    qdl = _qobuz(tmp_path, client, quality_fallback=quality_fallback)
    caplog.set_level("INFO", logger="qobuz_dl.downloader")
    final_path = (
        tmp_path
        / "music/Album Artist - Album Title (2024) [16B-44.1kHz]"
        / "02. Interlude.flac"
    )

    result = qdl.download_from_id("track-2", album=False)

    paths = (str(final_path),) if state == "finalized" else ()
    assert result == DownloadResult(state, reason, paths)
    assert client.track_url_calls == [("track-2", 27)]
    assert actual_transfers == transferred
    assert final_path.exists() is quality_fallback
    assert _history_ids(qdl.downloads_db) == history
    assert _track_quality_messages(caplog) == []
