import base64
import logging
import os
import sqlite3
from pathlib import Path

import pytest
from mutagen.flac import FLAC
from mutagen.mp3 import EasyMP3

from qobuz_dl import db, downloader
from qobuz_dl.core import QobuzDL
from qobuz_dl.downloader import DownloadResult
from qobuz_dl.utils import make_m3u

FIXTURES = Path(__file__).parent / "fixtures"

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


def _track_url(track_id, *, bit_depth=16, sample_rate=44.1, format_id=6):
    return {
        "url": f"https://media.example.test/{track_id}.flac",
        "sampling_rate": sample_rate,
        "bit_depth": bit_depth,
        "format_id": format_id,
        "mime_type": "audio/flac",
    }


class _PlaylistClient:
    def __init__(self, name="Playlist", item_ids=("track-a",)):
        self.name = name
        self.item_ids = item_ids
        self.metadata = {
            item_id: _track_metadata(
                item_id, item_id.replace("track-", "Track ").title()
            )
            for item_id in item_ids
        }
        self.urls = {item_id: _track_url(item_id) for item_id in item_ids}

    def get_plist_meta(self, item_id):
        assert item_id == "playlist1"
        return iter(
            [
                {
                    "name": self.name,
                    "tracks": {"items": [{"id": item} for item in self.item_ids]},
                }
            ]
        )

    def get_track_url(self, item_id, fmt_id):
        assert fmt_id == 6
        return self.urls[item_id]

    def get_track_meta(self, item_id):
        return self.metadata[item_id]


def _flac_fixture(*, bit_depth=16, sample_rate_hz=44100):
    fixture = bytearray((FIXTURES / "synthetic-silence.flac").read_bytes())
    if (bit_depth, sample_rate_hz) == (16, 44100):
        return bytes(fixture)
    stream_info = int.from_bytes(fixture[18:26], "big")
    channels = (stream_info >> 41) & 0b111
    total_samples = stream_info & ((1 << 36) - 1)
    stream_info = (
        (sample_rate_hz << 44)
        | (channels << 41)
        | ((bit_depth - 1) << 36)
        | total_samples
    )
    fixture[18:26] = stream_info.to_bytes(8, "big")
    return bytes(fixture)


def _install_real_download(monkeypatch):
    transfers = []

    def transfer(url, filename, _description, **_kwargs):
        transfers.append(Path(url).stem)
        media = (
            _flac_fixture(bit_depth=24, sample_rate_hz=96000)
            if "hires" in url
            else _flac_fixture()
        )
        Path(filename).write_bytes(media)

    def tag(filename, _root, final_name, track, *_args, finalize=True):
        audio = FLAC(filename)
        audio["TITLE"] = track["title"]
        audio["ARTIST"] = track["performer"]["name"]
        audio.save()
        if finalize:
            os.replace(filename, final_name)

    monkeypatch.setattr(downloader, "download_with_progress", transfer)
    monkeypatch.setattr(downloader.metadata, "tag_flac", tag)
    return transfers


def _qobuz(
    root,
    client,
    *,
    database=True,
    no_m3u=False,
    quality_fallback=True,
):
    downloads_db = (
        root / "history.sqlite" if database is True else database if database else None
    )
    qdl = QobuzDL(
        directory=root,
        quality=6,
        no_cover=True,
        downloads_db=downloads_db,
        no_m3u_for_playlists=no_m3u,
        quality_fallback=quality_fallback,
        folder_format="Album",
        track_format="{tracktitle}",
    )
    qdl.client = client
    return qdl


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

    assert [item_id for item_id, _album, _path in transfers] == ["a", "b", "a"]
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
    )
    make_m3u(playlist_dir, qdl._playlist_finalized_paths(occurrences))

    assert [(item.item_id, item.result) for item in occurrences] == [
        ("tagging-failed", results["tagging-failed"]),
        ("missing", results["missing"]),
    ]
    assert (playlist_dir / "Mixed results.m3u").read_text() == "#EXTM3U"


def test_empty_resolved_playlist_rewrites_header_only_without_deleting_audio(tmp_path):
    playlist_dir = tmp_path / "Empty now"
    audio = playlist_dir / "old.flac"
    _write_flac(audio, "Old", "Artist")
    playlist = playlist_dir / "Empty now.m3u"
    playlist.write_text("stale playlist", encoding="utf-8")

    make_m3u(playlist_dir, ())

    assert playlist.read_text(encoding="utf-8") == "#EXTM3U"
    assert audio.is_file()


def test_no_m3u_changes_only_the_writer_and_keeps_ordered_outcomes(
    tmp_path, monkeypatch
):
    transfers = _install_real_download(monkeypatch)

    def run(no_m3u):
        transfer_start = len(transfers)
        root = tmp_path / ("without-m3u" if no_m3u else "with-m3u")
        item_ids = (
            "track-a",
            "unavailable",
            "refused",
            "collision",
            "track-b",
            "track-a",
        )
        client = _PlaylistClient("Parity", item_ids)
        client.urls["unavailable"] = {
            **_track_url("unavailable"),
            "url": None,
        }
        client.urls["refused"] = {
            **_track_url("refused"),
            "restrictions": [{"code": downloader.QL_DOWNGRADE}],
        }
        client.metadata["collision"] = _track_metadata("collision", "Track A")
        qdl = _qobuz(
            root,
            client,
            no_m3u=no_m3u,
            quality_fallback=False,
        )
        plan = qdl._resolve_url_download_plan(
            "https://play.qobuz.com/playlist/playlist1"
        )
        occurrences = qdl._execute_url_download_plan(plan)
        relative_results = [
            (
                occurrence.item_id,
                occurrence.result.state,
                occurrence.result.reason,
                tuple(
                    Path(path).relative_to(root).as_posix()
                    for path in occurrence.result.finalized_paths
                ),
            )
            for occurrence in occurrences
        ]
        media = sorted(
            path.relative_to(root).as_posix() for path in root.rglob("*.flac")
        )
        with sqlite3.connect(qdl.downloads_db) as connection:
            artifacts = [
                (Path(path).relative_to(root).as_posix(), *facts)
                for path, *facts in connection.execute(
                    "SELECT path, track_id, requested_quality, codec, bit_depth, "
                    "sample_rate_hz, bitrate_bps, size_bytes, sha256 "
                    "FROM artifacts ORDER BY track_id"
                )
            ]
        playlist = root / "Parity" / "Parity.m3u"
        return relative_results, media, playlist, transfers[transfer_start:], artifacts

    with_m3u = run(False)
    without_m3u = run(True)
    expected_results = [
        ("track-a", "finalized", "downloaded", ("Parity/Album/Track A.flac",)),
        ("unavailable", "failed", "missing_url", ()),
        ("refused", "ignored", "quality_filter", ()),
        ("collision", "failed", "path_conflict", ()),
        ("track-b", "finalized", "downloaded", ("Parity/Album/Track B.flac",)),
        (
            "track-a",
            "finalized",
            "verified_artifact",
            ("Parity/Album/Track A.flac",),
        ),
    ]

    assert with_m3u[:2] == without_m3u[:2]
    assert with_m3u[0] == expected_results
    assert with_m3u[1] == [
        "Parity/Album/Track A.flac",
        "Parity/Album/Track B.flac",
    ]
    assert with_m3u[3] == without_m3u[3] == ["track-a", "track-b"]
    assert _playlist_items(with_m3u[2]) == [
        "#EXTM3U",
        "#EXTINF:0, Track Artist - Track A\nAlbum/Track A.flac",
        "#EXTINF:0, Track Artist - Track B\nAlbum/Track B.flac",
        "#EXTINF:0, Track Artist - Track A\nAlbum/Track A.flac",
    ]
    assert not without_m3u[2].exists()
    expected_artifact_facts = [
        (
            Path(os.path.normcase(path)).as_posix(),
            track_id,
            6,
            "flac",
            16,
            44100,
        )
        for path, track_id in [
            ("Parity/Album/Track A.flac", "track-a"),
            ("Parity/Album/Track B.flac", "track-b"),
        ]
    ]
    assert [artifact[:6] for artifact in with_m3u[4]] == expected_artifact_facts
    assert [artifact[:6] for artifact in without_m3u[4]] == expected_artifact_facts
    assert [artifact[6:] for artifact in with_m3u[4]] == [
        artifact[6:] for artifact in without_m3u[4]
    ]


def test_direct_artifact_at_playlist_destination_is_reused(tmp_path, monkeypatch):
    transfers = _install_real_download(monkeypatch)
    database = tmp_path / "history.sqlite"
    client = _PlaylistClient("Cross command", ("track-a",))
    direct = _qobuz(tmp_path / "music" / "Cross command", client, database=database)
    first = direct.download_from_id("track-a", album=False)
    playlist = _qobuz(tmp_path / "music", client, database=database)

    playlist.handle_url("https://play.qobuz.com/playlist/playlist1")

    expected = tmp_path / "music" / "Cross command" / "Album" / "Track A.flac"
    assert first == DownloadResult("finalized", "downloaded", (str(expected),))
    assert transfers == ["track-a"]
    assert _playlist_items(
        tmp_path / "music" / "Cross command" / "Cross command.m3u"
    ) == [
        "#EXTM3U",
        "#EXTINF:0, Track Artist - Track A\nAlbum/Track A.flac",
    ]


def test_artifact_in_another_destination_does_not_satisfy_playlist(
    tmp_path, monkeypatch
):
    transfers = _install_real_download(monkeypatch)
    database = tmp_path / "history.sqlite"
    client = _PlaylistClient("New destination", ("track-a",))
    direct = _qobuz(tmp_path / "music" / "Original", client, database=database)
    direct.download_from_id("track-a", album=False)
    playlist = _qobuz(tmp_path / "music", client, database=database)

    playlist.handle_url("https://play.qobuz.com/playlist/playlist1")

    assert transfers == ["track-a", "track-a"]
    assert (tmp_path / "music" / "Original" / "Album" / "Track A.flac").is_file()
    assert (tmp_path / "music" / "New destination" / "Album" / "Track A.flac").is_file()


@pytest.mark.parametrize(
    ("change", "expected_reason", "expected_transfers", "playlist_entries"),
    [
        ("deleted", "downloaded", ["track-a", "track-a"], 1),
        ("replaced", "path_conflict", ["track-a"], 0),
        ("quality", "downloaded", ["track-a", "track-a-hires"], 1),
    ],
)
def test_stale_artifacts_do_not_satisfy_playlist_occurrences(
    tmp_path,
    monkeypatch,
    change,
    expected_reason,
    expected_transfers,
    playlist_entries,
):
    transfers = _install_real_download(monkeypatch)
    client = _PlaylistClient("Stale", ("track-a",))
    qdl = _qobuz(tmp_path / "music", client)
    first_plan = qdl._resolve_url_download_plan(
        "https://play.qobuz.com/playlist/playlist1"
    )
    first = qdl._execute_url_download_plan(first_plan)
    final_path = Path(first[0].result.finalized_paths[0])

    if change == "deleted":
        final_path.unlink()
    elif change == "replaced":
        final_path.write_bytes(b"foreign")
    else:
        client.urls["track-a"] = _track_url(
            "track-a-hires",
            bit_depth=24,
            sample_rate=96,
            format_id=27,
        )

    second_plan = qdl._resolve_url_download_plan(
        "https://play.qobuz.com/playlist/playlist1"
    )
    second = qdl._execute_url_download_plan(second_plan)

    assert second[0].result.reason == expected_reason
    assert transfers == expected_transfers
    playlist = tmp_path / "music" / "Stale" / "Stale.m3u"
    assert len(_playlist_items(playlist)) == playlist_entries + 1
    if change == "replaced":
        assert final_path.read_bytes() == b"foreign"


def test_distinct_track_ids_resolving_to_one_path_conflict_without_overwrite(
    tmp_path, monkeypatch
):
    transfers = _install_real_download(monkeypatch)
    client = _PlaylistClient("Collision", ("track-a", "track-b"))
    client.metadata["track-b"] = _track_metadata("track-b", "Track A")
    qdl = _qobuz(tmp_path / "music", client)
    plan = qdl._resolve_url_download_plan("https://play.qobuz.com/playlist/playlist1")

    occurrences = qdl._execute_url_download_plan(plan)

    expected = tmp_path / "music" / "Collision" / "Album" / "Track A.flac"
    assert [occurrence.result.reason for occurrence in occurrences] == [
        "downloaded",
        "path_conflict",
    ]
    assert transfers == ["track-a"]
    assert expected.is_file()
    assert _playlist_items(tmp_path / "music" / "Collision" / "Collision.m3u") == [
        "#EXTM3U",
        "#EXTINF:0, Track Artist - Track A\nAlbum/Track A.flac",
    ]


def test_no_db_reuses_repeated_playlist_occurrence_without_sqlite(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        db.sqlite3,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("SQLite access in --no-db mode"),
    )
    transfers = _install_real_download(monkeypatch)
    client = _PlaylistClient("No database", ("track-a", "track-a"))
    qdl = _qobuz(tmp_path / "music", client, database=False)
    plan = qdl._resolve_url_download_plan("https://play.qobuz.com/playlist/playlist1")

    occurrences = qdl._execute_url_download_plan(plan)

    assert [occurrence.result.reason for occurrence in occurrences] == [
        "downloaded",
        "verified_artifact",
    ]
    assert transfers == ["track-a"]
    assert qdl.downloads_db is None
    assert _playlist_items(tmp_path / "music" / "No database" / "No database.m3u") == [
        "#EXTM3U",
        "#EXTINF:0, Track Artist - Track A\nAlbum/Track A.flac",
        "#EXTINF:0, Track Artist - Track A\nAlbum/Track A.flac",
    ]


def test_lastfm_html_selection_flows_through_real_m3u_output(tmp_path, monkeypatch):
    html = (FIXTURES / "lastfm_row_pairs.html").read_text()
    qdl = QobuzDL(directory=tmp_path)
    playlist_dir = tmp_path / "Row Pairing Proof"
    paths = {
        "id1": playlist_dir / "Alpha custom.flac",
        "id3": playlist_dir / "Gamma custom.flac",
    }
    _write_flac(paths["id1"], "First Song", "Alpha Artist")
    _write_flac(paths["id3"], "Third Song", "Gamma Artist")
    monkeypatch.setattr("qobuz_dl.core.http.get_text", lambda url, timeout: html)
    search_results = iter(
        [
            ["https://play.qobuz.com/track/id1"],
            [],
            ["https://play.qobuz.com/track/id1"],
            ["https://play.qobuz.com/track/id3"],
        ]
    )
    searches = []
    downloads = []

    def search(query, item_type, limit, lucky):
        searches.append((query, item_type, limit, lucky))
        return next(search_results)

    def download(item_id, album=True, alt_path=None, **_kwargs):
        downloads.append((item_id, album, alt_path))
        return DownloadResult("finalized", "verified_artifact", (str(paths[item_id]),))

    qdl.search_by_type = search
    qdl.download_from_id = download

    qdl.download_lastfm_pl("https://www.last.fm/user/example/playlists/1")

    assert searches == [
        ("Alpha Artist First Song & Dance", "track", 1, True),
        ("Repeat Artist Repeat Song", "track", 1, True),
        ("Repeat Artist Repeat Song", "track", 1, True),
        ("Gamma Artist Third Song", "track", 1, True),
    ]
    assert downloads == [
        ("id1", False, str(playlist_dir)),
        ("id1", False, str(playlist_dir)),
        ("id3", False, str(playlist_dir)),
    ]
    assert _playlist_items(playlist_dir / "Row Pairing Proof.m3u") == [
        "#EXTM3U",
        "#EXTINF:0, Alpha Artist - First Song\nAlpha custom.flac",
        "#EXTINF:0, Alpha Artist - First Song\nAlpha custom.flac",
        "#EXTINF:0, Gamma Artist - Third Song\nGamma custom.flac",
    ]


def test_lastfm_source_with_no_qobuz_matches_writes_header_only(tmp_path, monkeypatch):
    html = (Path(__file__).parent / "fixtures" / "lastfm_playlist.html").read_text()
    qdl = QobuzDL(directory=tmp_path)
    monkeypatch.setattr("qobuz_dl.core.http.get_text", lambda url, timeout: html)
    qdl.search_by_type = lambda query, item_type, limit, lucky: []

    qdl.download_lastfm_pl("https://www.last.fm/user/example/playlists/1")

    playlist = tmp_path / "My Lastfm Playlist" / "My Lastfm Playlist.m3u"
    assert playlist.read_text(encoding="utf-8") == "#EXTM3U"


def test_lastfm_no_m3u_still_processes_every_matched_occurrence(tmp_path, monkeypatch):
    html = (FIXTURES / "lastfm_playlist.html").read_text()
    qdl = QobuzDL(
        directory=tmp_path,
        no_m3u_for_playlists=True,
    )
    playlist_dir = tmp_path / "My Lastfm Playlist"
    playlist_dir.mkdir()
    playlist = playlist_dir / "My Lastfm Playlist.m3u"
    playlist.write_text("existing playlist", encoding="utf-8")
    downloads = []
    monkeypatch.setattr("qobuz_dl.core.http.get_text", lambda url, timeout: html)
    qdl.search_by_type = lambda query, item_type, limit, lucky: [
        f"https://play.qobuz.com/track/id{1 if query.startswith('Alpha') else 2}"
    ]
    qdl.download_from_id = lambda item_id, album=True, alt_path=None, **_kwargs: (
        downloads.append((item_id, album, alt_path))
        or DownloadResult("finalized", "verified_artifact")
    )

    qdl.download_lastfm_pl("https://www.last.fm/user/example/playlists/1")

    assert downloads == [
        ("id1", False, str(playlist_dir)),
        ("id2", False, str(playlist_dir)),
    ]
    assert playlist.read_text(encoding="utf-8") == "existing playlist"
