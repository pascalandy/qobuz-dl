import base64
import logging
from pathlib import Path

import pytest
from mutagen.flac import FLAC
from mutagen.mp3 import EasyMP3

from qobuz_dl.core import QobuzDL
from qobuz_dl.db import handle_download_id
from qobuz_dl.downloader import DownloadResult
from qobuz_dl.utils import make_m3u

SILENT_MP3 = base64.b64decode(
    "SUQzBAAAAAAAIlRTU0UAAAAOAAADTGF2ZjYzLjEuMTAxAAAAAAAAAAAAAAD/4zjAAAAAAAAA"
    "AAAASW5mbwAAAA8AAAADAAABsACqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqrV"
    "1dXV1dXV1dXV1dXV1dXV1dXV1dXV1dXV1dXV1dXV1dX/////////////////////////////"
    "//////////////8AAAAATGF2YzYzLjEuAAAAAAAAAAAAAAAAJALwAAAAAAAAAbCaZ7gQAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/4xjEAAAAA0gA"
    "AAAATEFNRTQuMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
    "VVVVVVVVVVX/4xjEOwAAA0gAAAAAVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
    "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVX/4xjEdgAAA0gAAAAAVVVVVVVVVVVVVVVVVVVV"
    "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVU="
)


def _write_flac(path, title, artist):
    path.parent.mkdir(parents=True, exist_ok=True)
    streaminfo = bytearray(34)
    streaminfo[0:2] = (4096).to_bytes(2, "big")
    streaminfo[2:4] = (4096).to_bytes(2, "big")
    value = (44100 << 44) | (1 << 41) | (15 << 36)
    streaminfo[10:18] = value.to_bytes(8, "big")
    path.write_bytes(b"fLaC" + bytes([0x80]) + (34).to_bytes(3, "big") + streaminfo)
    audio = FLAC(path)
    audio["TITLE"] = title
    audio["ARTIST"] = artist
    audio.save()


def _write_mp3(path, title, artist):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(SILENT_MP3)
    audio = EasyMP3(path)
    audio["TITLE"] = title
    audio["ARTIST"] = artist
    audio.save()


def _playlist_items(path):
    return path.read_text(encoding="utf-8").split("\n\n")


def _track_metadata(track_id="track-a", title="Track A"):
    return {
        "id": track_id,
        "title": title,
        "performer": {"name": "Track Artist"},
        "album": {
            "id": "album-1",
            "title": "Album",
            "artist": {"name": "Album Artist"},
            "release_date_original": "2024-02-03",
            "image": {"large": "https://img.example.test/cover.jpg"},
            "tracks_count": 1,
            "genres_list": ["Rock"],
        },
        "maximum_bit_depth": 24,
        "maximum_sampling_rate": 96,
        "track_number": 1,
        "media_number": 1,
        "version": None,
        "copyright": "",
    }


def test_make_m3u_uses_explicit_paths_in_order_with_repetitions(tmp_path, caplog):
    playlist_dir = tmp_path / "Source order"
    first = playlist_dir / "custom A.mp3"
    second = playlist_dir / "nested" / "custom B.flac"
    missing = playlist_dir / "missing.flac"
    unsupported = playlist_dir / "foreign.ogg"
    _write_mp3(first, "First", "Artist A")
    unsupported.write_bytes(b"foreign bytes")
    _write_flac(second, "Second", "Artist B")
    caplog.set_level(logging.WARNING, logger="qobuz_dl.utils")

    make_m3u(playlist_dir, (first, second, first, missing, unsupported))

    assert _playlist_items(playlist_dir / "Source order.m3u") == [
        "#EXTM3U",
        "#EXTINF:0, Artist A - First\ncustom A.mp3",
        "#EXTINF:0, Artist B - Second\nnested/custom B.flac",
        "#EXTINF:0, Artist A - First\ncustom A.mp3",
    ]
    assert [record.getMessage() for record in caplog.records] == [
        f"Skipping {missing} in m3u: file is not readable",
        f"Skipping {unsupported} in m3u: unsupported media suffix .ogg",
    ]


def test_qobuz_playlist_rewrites_from_current_source_without_scanning_directory(
    tmp_path,
):
    qdl = QobuzDL(directory=tmp_path)
    playlist_dir = tmp_path / "Current source"
    paths = {
        "a": playlist_dir / "custom A.flac",
        "b": playlist_dir / "custom B.flac",
    }
    _write_flac(paths["a"], "A", "Artist A")
    _write_flac(paths["b"], "B", "Artist B")
    foreign = playlist_dir / "foreign.flac"
    _write_flac(foreign, "Foreign", "Other Artist")

    source_ids = ["a", "b", "a"]

    class Client:
        def get_plist_meta(self, item_id):
            assert item_id == "playlist1"
            return iter(
                [
                    {
                        "name": "Current source",
                        "tracks": {"items": [{"id": item} for item in source_ids]},
                    }
                ]
            )

    qdl.client = Client()
    transfers = []

    def download(item_id, album=True, alt_path=None, **_kwargs):
        transfers.append((item_id, album, alt_path))
        return DownloadResult("finalized", "downloaded", (str(paths[item_id]),))

    qdl.download_from_id = download

    qdl.handle_url("https://play.qobuz.com/playlist/playlist1")

    assert [item_id for item_id, _album, _path in transfers] == ["a", "b"]
    assert _playlist_items(playlist_dir / "Current source.m3u") == [
        "#EXTM3U",
        "#EXTINF:0, Artist A - A\ncustom A.flac",
        "#EXTINF:0, Artist B - B\ncustom B.flac",
        "#EXTINF:0, Artist A - A\ncustom A.flac",
    ]

    source_ids[:] = ["b", "a"]
    transfers.clear()
    qdl.handle_url("https://play.qobuz.com/playlist/playlist1")

    assert [item_id for item_id, _album, _path in transfers] == ["b", "a"]
    assert _playlist_items(playlist_dir / "Current source.m3u") == [
        "#EXTM3U",
        "#EXTINF:0, Artist B - B\ncustom B.flac",
        "#EXTINF:0, Artist A - A\ncustom A.flac",
    ]
    assert paths["a"].is_file()
    assert foreign.is_file()


def test_playlist_occurrences_preserve_explicit_failures_and_usable_failed_paths(
    tmp_path,
):
    qdl = QobuzDL(directory=tmp_path)
    playlist_dir = tmp_path / "Mixed results"
    usable = playlist_dir / "tagged despite failure.flac"
    _write_flac(usable, "Usable", "Artist")
    results = {
        "tagging-failed": DownloadResult("failed", "tagging_error", (str(usable),)),
        "missing": DownloadResult("failed", "missing_url"),
    }
    qdl.download_from_id = lambda item_id, album=True, alt_path=None, **_kwargs: (
        results[item_id]
    )

    occurrences = qdl._download_playlist_occurrences(
        ("tagging-failed", "missing"),
        str(playlist_dir),
        recover_existing=True,
    )
    make_m3u(
        playlist_dir,
        tuple(
            path
            for occurrence in occurrences
            for path in occurrence.result.finalized_paths
        ),
    )

    assert [(item.item_id, item.result) for item in occurrences] == [
        ("tagging-failed", results["tagging-failed"]),
        ("missing", results["missing"]),
    ]
    assert _playlist_items(playlist_dir / "Mixed results.m3u") == [
        "#EXTM3U",
        "#EXTINF:0, Artist - Usable\ntagged despite failure.flac",
    ]


def test_empty_resolved_playlist_rewrites_header_only_without_deleting_audio(tmp_path):
    playlist_dir = tmp_path / "Empty now"
    audio = playlist_dir / "old.flac"
    _write_flac(audio, "Old", "Artist")
    playlist = playlist_dir / "Empty now.m3u"
    playlist.write_text("stale playlist", encoding="utf-8")

    make_m3u(playlist_dir, ())

    assert playlist.read_text(encoding="utf-8") == "#EXTM3U"
    assert audio.is_file()


def test_qobuz_no_m3u_skips_duplicate_path_recovery_and_leaves_playlist_untouched(
    tmp_path,
):
    database = tmp_path / "downloads.sqlite"
    qdl = QobuzDL(
        directory=tmp_path,
        no_m3u_for_playlists=True,
        downloads_db=database,
    )
    playlist_dir = tmp_path / "No rewrite"
    playlist_dir.mkdir()
    playlist = playlist_dir / "No rewrite.m3u"
    playlist.write_text("existing playlist", encoding="utf-8")
    handle_download_id(qdl.downloads_db, "track-a", add_id=True)

    class Client:
        def get_plist_meta(self, item_id):
            return iter(
                [
                    {
                        "name": "No rewrite",
                        "tracks": {"items": [{"id": "track-a"}]},
                    }
                ]
            )

        def get_track_url(self, item_id, fmt_id):
            pytest.fail("--no-m3u must not resolve a database duplicate URL")

        def get_track_meta(self, item_id):
            pytest.fail("--no-m3u must not resolve database duplicate metadata")

    qdl.client = Client()

    qdl.handle_url("https://play.qobuz.com/playlist/playlist1")

    assert playlist.read_text(encoding="utf-8") == "existing playlist"


def test_database_duplicate_reuses_only_the_exact_destination_file(
    tmp_path, monkeypatch
):
    database = tmp_path / "downloads.sqlite"
    qdl = QobuzDL(
        directory=tmp_path / "music",
        downloads_db=database,
        no_cover=True,
        folder_format="{album}",
        track_format="{tracktitle}",
    )
    playlist_dir = tmp_path / "music" / "Database rerun"
    expected = playlist_dir / "Album" / "Track A.flac"
    _write_flac(expected, "Track A", "Track Artist")
    handle_download_id(qdl.downloads_db, "track-a", add_id=True)
    requests = []

    class Client:
        def get_plist_meta(self, item_id):
            return iter(
                [
                    {
                        "name": "Database rerun",
                        "tracks": {"items": [{"id": "track-a"}]},
                    }
                ]
            )

        def get_track_url(self, item_id, fmt_id):
            requests.append(("url", item_id, fmt_id))
            return {
                "url": "https://media.example.test/track-a.flac",
                "sampling_rate": 96,
                "bit_depth": 24,
            }

        def get_track_meta(self, item_id):
            requests.append(("meta", item_id))
            return _track_metadata()

    qdl.client = Client()
    monkeypatch.setattr(
        "qobuz_dl.downloader.http.stream_download",
        lambda *args, **kwargs: pytest.fail(
            "database recovery must not transfer media"
        ),
    )

    qdl.handle_url("https://play.qobuz.com/playlist/playlist1")

    assert requests == [("url", "track-a", 6), ("meta", "track-a")]
    assert _playlist_items(playlist_dir / "Database rerun.m3u") == [
        "#EXTM3U",
        "#EXTINF:0, Track Artist - Track A\nAlbum/Track A.flac",
    ]


def test_database_duplicate_without_exact_file_stays_explicit_and_never_transfers(
    tmp_path, monkeypatch
):
    database = tmp_path / "downloads.sqlite"
    qdl = QobuzDL(
        directory=tmp_path / "music",
        downloads_db=database,
        no_cover=True,
        folder_format="{album}",
        track_format="{tracktitle}",
    )
    destination = tmp_path / "music" / "Other destination"
    destination.mkdir(parents=True)
    other_destination = tmp_path / "music" / "Original" / "Album" / "Track A.flac"
    _write_flac(other_destination, "Track A", "Track Artist")
    handle_download_id(qdl.downloads_db, "track-a", add_id=True)

    class Client:
        def get_track_url(self, item_id, fmt_id):
            return {
                "url": "https://media.example.test/track-a.flac",
                "sampling_rate": 96,
                "bit_depth": 24,
            }

        def get_track_meta(self, item_id):
            return _track_metadata()

    qdl.client = Client()
    monkeypatch.setattr(
        "qobuz_dl.downloader.http.stream_download",
        lambda *args, **kwargs: pytest.fail("history recovery must not transfer media"),
    )

    occurrences = qdl._download_playlist_occurrences(
        ("track-a",), str(destination), recover_existing=True
    )
    make_m3u(destination, qdl._playlist_finalized_paths(occurrences))

    assert occurrences[0].result == DownloadResult("ignored", "database_duplicate")
    assert (destination / "Other destination.m3u").read_text() == "#EXTM3U"


def test_distinct_track_ids_claiming_one_path_are_reported(tmp_path, caplog):
    shared = tmp_path / "shared.flac"
    result = DownloadResult("finalized", "existing_file", (str(shared),))
    qdl = QobuzDL(directory=tmp_path)
    qdl.download_from_id = lambda item_id, album=True, alt_path=None, **_kwargs: result
    caplog.set_level(logging.WARNING, logger="qobuz_dl.core")

    occurrences = qdl._download_playlist_occurrences(
        ("track-a", "track-b"), tmp_path, recover_existing=True
    )
    paths = qdl._playlist_finalized_paths(occurrences)

    assert paths == (str(shared), str(shared))
    assert [record.getMessage() for record in caplog.records] == [
        f"track-a and track-b resolved to the same playlist file: {shared}"
    ]


def test_lastfm_html_selection_flows_through_real_m3u_output(tmp_path, monkeypatch):
    html = (Path(__file__).parent / "fixtures" / "lastfm_playlist.html").read_text()
    qdl = QobuzDL(directory=tmp_path)
    playlist_dir = tmp_path / "My Lastfm Playlist"
    paths = {
        "id1": playlist_dir / "Alpha custom.flac",
        "id2": playlist_dir / "Beta custom.flac",
    }
    _write_flac(paths["id1"], "First Song", "Alpha Artist")
    _write_flac(paths["id2"], "Second Track", "Beta Artist")
    monkeypatch.setattr("qobuz_dl.core.http.get_text", lambda url, timeout: html)
    qdl.search_by_type = lambda query, item_type, limit, lucky: [
        f"https://play.qobuz.com/track/id{1 if query.startswith('Alpha') else 2}"
    ]
    qdl.download_from_id = lambda item_id, album=True, alt_path=None, **_kwargs: (
        DownloadResult("finalized", "existing_file", (str(paths[item_id]),))
    )

    qdl.download_lastfm_pl("https://www.last.fm/user/example/playlists/1")

    assert _playlist_items(playlist_dir / "My Lastfm Playlist.m3u") == [
        "#EXTM3U",
        "#EXTINF:0, Alpha Artist - First Song\nAlpha custom.flac",
        "#EXTINF:0, Beta Artist - Second Track\nBeta custom.flac",
    ]


def test_lastfm_source_with_no_qobuz_matches_writes_header_only(tmp_path, monkeypatch):
    html = (Path(__file__).parent / "fixtures" / "lastfm_playlist.html").read_text()
    qdl = QobuzDL(directory=tmp_path)
    monkeypatch.setattr("qobuz_dl.core.http.get_text", lambda url, timeout: html)
    qdl.search_by_type = lambda query, item_type, limit, lucky: []

    qdl.download_lastfm_pl("https://www.last.fm/user/example/playlists/1")

    playlist = tmp_path / "My Lastfm Playlist" / "My Lastfm Playlist.m3u"
    assert playlist.read_text(encoding="utf-8") == "#EXTM3U"


def test_lastfm_no_m3u_skips_duplicate_path_recovery_and_leaves_playlist_untouched(
    tmp_path, monkeypatch
):
    html = (Path(__file__).parent / "fixtures" / "lastfm_playlist.html").read_text()
    database = tmp_path / "downloads.sqlite"
    qdl = QobuzDL(
        directory=tmp_path,
        no_m3u_for_playlists=True,
        downloads_db=database,
    )
    playlist_dir = tmp_path / "My Lastfm Playlist"
    playlist_dir.mkdir()
    playlist = playlist_dir / "My Lastfm Playlist.m3u"
    playlist.write_text("existing playlist", encoding="utf-8")
    for item_id in ("id1", "id2"):
        handle_download_id(qdl.downloads_db, item_id, add_id=True)

    class Client:
        def get_track_url(self, item_id, fmt_id):
            pytest.fail("--no-m3u must not resolve a database duplicate URL")

        def get_track_meta(self, item_id):
            pytest.fail("--no-m3u must not resolve database duplicate metadata")

    qdl.client = Client()
    monkeypatch.setattr("qobuz_dl.core.http.get_text", lambda url, timeout: html)
    qdl.search_by_type = lambda query, item_type, limit, lucky: [
        f"https://play.qobuz.com/track/id{1 if query.startswith('Alpha') else 2}"
    ]

    qdl.download_lastfm_pl("https://www.last.fm/user/example/playlists/1")

    assert playlist.read_text(encoding="utf-8") == "existing playlist"
