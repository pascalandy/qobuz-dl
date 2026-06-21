"""Regression tests for bugs fixed while hardening the fork for production."""

import builtins
import os

import pytest

from qobuz_dl.core import QobuzDL
from qobuz_dl.utils import get_url_info, smart_discography_filter


def _album(title, artist, bit_depth=16, sampling_rate=44.1, album_id="a-1"):
    return {
        "title": title,
        "artist": {"name": artist},
        "maximum_bit_depth": bit_depth,
        "maximum_sampling_rate": sampling_rate,
        "id": album_id,
    }


class TestGetUrlInfo:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://play.qobuz.com/album/abc123", ("album", "abc123")),
            ("https://open.qobuz.com/track/12345", ("track", "12345")),
            (
                "https://www.qobuz.com/us-en/album/some-name/xyz789",
                ("album", "xyz789"),
            ),
            ("/us-en/artist/-/55555", ("artist", "55555")),
            ("https://play.qobuz.com/label/98765", ("label", "98765")),
            ("https://play.qobuz.com/playlist/424242", ("playlist", "424242")),
        ],
    )
    def test_parses_supported_url_forms(self, url, expected):
        assert get_url_info(url) == expected

    def test_accepts_bare_paths_with_a_known_type_segment(self):
        # Documented lenient behavior: the domain part is optional, so any
        # input containing /{type}/{id} parses.
        assert get_url_info("/album/abc123") == ("album", "abc123")

    @pytest.mark.parametrize(
        "url",
        [
            "not a url at all",
            "",
            "https://play.qobuz.com/",
            "https://example.com/not-qobuz",
        ],
    )
    def test_raises_value_error_for_unrecognized_urls(self, url):
        with pytest.raises(ValueError, match="Invalid Qobuz URL"):
            get_url_info(url)


def test_handle_url_logs_invalid_url_without_crashing(tmp_path, caplog):
    qdl = QobuzDL(directory=tmp_path)
    caplog.set_level("INFO", logger="qobuz_dl.core")

    qdl.handle_url("https://example.com/not-qobuz")

    assert any("Invalid url" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://play.qobuz.com/album/album1", ("album1", True, None)),
        ("https://play.qobuz.com/track/track1", ("track1", False, None)),
    ],
)
def test_handle_url_routes_direct_album_and_track_downloads(tmp_path, url, expected):
    qdl = QobuzDL(directory=tmp_path)
    downloaded = []
    qdl.download_from_id = lambda item_id, album=True, alt_path=None: downloaded.append(
        (item_id, album, alt_path)
    )

    qdl.handle_url(url)

    assert downloaded == [expected]


def test_download_list_of_urls_ingests_text_file_sources_in_order(tmp_path):
    url_file = tmp_path / "urls.txt"
    repeated_track = "https://play.qobuz.com/track/repeated"
    url_file.write_text(
        "\n".join(
            [
                "",
                "   ",
                "# skipped whole-line comment",
                "   # skipped indented comment",
                "https://play.qobuz.com/album/album1",
                repeated_track,
                "https://www.last.fm/user/example/playlists/playlist1",
                repeated_track,
                "",
            ]
        ),
        encoding="utf-8",
    )
    qdl = QobuzDL(directory=tmp_path / "downloads")
    dispatched = []
    qdl.handle_url = lambda url: dispatched.append(("qobuz", url))
    qdl.download_lastfm_pl = lambda url: dispatched.append(("lastfm", url))
    qdl.download_from_id = lambda *args, **kwargs: pytest.fail(
        "text-file ingestion should dispatch through URL handlers"
    )

    qdl.download_list_of_urls([str(url_file)])

    assert dispatched == [
        ("qobuz", "https://play.qobuz.com/album/album1"),
        ("qobuz", repeated_track),
        ("lastfm", "https://www.last.fm/user/example/playlists/playlist1"),
        ("qobuz", repeated_track),
    ]


@pytest.mark.parametrize(
    "path_name",
    ["missing.txt", "invalid-utf8.txt"],
)
def test_download_from_txt_file_logs_bad_files_without_dispatching(
    tmp_path, caplog, path_name
):
    txt_file = tmp_path / path_name
    if path_name == "invalid-utf8.txt":
        txt_file.write_bytes(b"\xff")
    qdl = QobuzDL(directory=tmp_path / "downloads")
    qdl.download_list_of_urls = lambda urls: pytest.fail(
        f"bad text file unexpectedly dispatched {urls}"
    )
    caplog.set_level("ERROR", logger="qobuz_dl.core")

    qdl.download_from_txt_file(txt_file)

    assert any("Invalid text file" in record.getMessage() for record in caplog.records)
    assert not hasattr(qdl, "client")


def test_download_from_txt_file_logs_unreadable_file_without_dispatching(
    tmp_path, monkeypatch, caplog
):
    txt_file = tmp_path / "unreadable.txt"
    txt_file.write_text("https://play.qobuz.com/album/album1", encoding="utf-8")
    qdl = QobuzDL(directory=tmp_path / "downloads")
    qdl.download_list_of_urls = lambda urls: pytest.fail(
        f"unreadable text file unexpectedly dispatched {urls}"
    )
    real_open = builtins.open

    def fake_open(file, *args, **kwargs):
        if os.fspath(file) == os.fspath(txt_file):
            raise PermissionError("permission denied")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    caplog.set_level("ERROR", logger="qobuz_dl.core")

    qdl.download_from_txt_file(txt_file)

    assert any("Invalid text file" in record.getMessage() for record in caplog.records)
    assert not hasattr(qdl, "client")


@pytest.mark.parametrize("query", ["", "ab", "   ", None])
def test_lucky_mode_rejects_short_or_invalid_queries_without_search_or_download(
    tmp_path, caplog, query
):
    qdl = QobuzDL(directory=tmp_path)
    qdl.search_by_type = lambda *args, **kwargs: pytest.fail(
        "invalid lucky query should not search"
    )
    qdl.download_list_of_urls = lambda urls: pytest.fail(
        f"invalid lucky query unexpectedly dispatched {urls}"
    )
    caplog.set_level("INFO", logger="qobuz_dl.core")

    assert qdl.lucky_mode(query) is None

    assert any(
        "search query is too short or invalid" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.parametrize("query", ["", "ab", "   ", None])
def test_search_by_type_rejects_short_or_invalid_queries_without_client(
    tmp_path, caplog, query
):
    qdl = QobuzDL(directory=tmp_path)
    caplog.set_level("INFO", logger="qobuz_dl.core")

    assert qdl.search_by_type(query, "album", lucky=True) is None

    assert not hasattr(qdl, "client")
    assert any(
        "search query is too short or invalid" in record.getMessage()
        for record in caplog.records
    )


def test_lucky_mode_uses_configured_search_boundary_and_download_flag(tmp_path):
    qdl = QobuzDL(directory=tmp_path, lucky_limit=2, lucky_type="track")
    results = [
        "https://play.qobuz.com/track/track1",
        "https://play.qobuz.com/track/track2",
    ]
    searches = []
    downloads = []

    def fake_search(query, item_type, limit, lucky=False):
        searches.append((query, item_type, limit, lucky))
        return results

    qdl.search_by_type = fake_search
    qdl.download_list_of_urls = lambda urls: downloads.append(list(urls))

    assert qdl.lucky_mode(" artist song ", download=True) == results
    assert qdl.lucky_mode("artist song", download=False) == results

    assert searches == [
        ("artist song", "track", 2, True),
        ("artist song", "track", 2, True),
    ]
    assert downloads == [results]


@pytest.mark.parametrize(
    ("item_type", "search_method", "result_key", "item", "expected_url"),
    [
        (
            "album",
            "search_albums",
            "albums",
            {
                "artist": {"name": "Artist"},
                "duration": 180,
                "hires_streamable": True,
                "id": "album1",
                "title": "Album",
            },
            "https://play.qobuz.com/album/album1",
        ),
        (
            "track",
            "search_tracks",
            "tracks",
            {
                "duration": 180,
                "hires_streamable": False,
                "id": "track1",
                "performer": {"name": "Artist"},
                "title": "Track",
            },
            "https://play.qobuz.com/track/track1",
        ),
        (
            "artist",
            "search_artists",
            "artists",
            {"albums_count": 7, "id": "artist1", "name": "Artist"},
            "https://play.qobuz.com/artist/artist1",
        ),
        (
            "playlist",
            "search_playlists",
            "playlists",
            {"id": "playlist1", "name": "Playlist", "tracks_count": 12},
            "https://play.qobuz.com/playlist/playlist1",
        ),
    ],
)
def test_search_by_type_lucky_builds_urls_for_supported_types(
    tmp_path, item_type, search_method, result_key, item, expected_url
):
    qdl = QobuzDL(directory=tmp_path)
    calls = []

    def fake_search(self, query, limit):
        calls.append((query, limit))
        return {result_key: {"items": [item]}}

    def unexpected_search(self, query, limit):
        pytest.fail(f"unexpected search call for {query=} {limit=}")

    search_methods = {
        "search_albums": unexpected_search,
        "search_artists": unexpected_search,
        "search_playlists": unexpected_search,
        "search_tracks": unexpected_search,
    }
    search_methods[search_method] = fake_search
    qdl.client = type("Client", (), search_methods)()

    urls = qdl.search_by_type(" valid query ", item_type, limit=3, lucky=True)

    assert urls == [expected_url]
    assert calls == [("valid query", 3)]


@pytest.mark.parametrize(
    ("url", "meta_method", "item_key", "expected_item_id", "expected_album"),
    [
        (
            "https://play.qobuz.com/artist/artist1",
            "get_artist_meta",
            "albums",
            "artist1",
            True,
        ),
        (
            "https://play.qobuz.com/label/label1",
            "get_label_meta",
            "albums",
            "label1",
            True,
        ),
        (
            "https://play.qobuz.com/playlist/pl1",
            "get_plist_meta",
            "tracks",
            "pl1",
            False,
        ),
    ],
)
@pytest.mark.parametrize(
    ("no_m3u_for_playlists", "expected_m3u_count"),
    [(False, 1), (True, 0)],
)
def test_handle_url_downloads_collection_items_from_every_page(
    tmp_path,
    monkeypatch,
    url,
    meta_method,
    item_key,
    expected_item_id,
    expected_album,
    no_m3u_for_playlists,
    expected_m3u_count,
):
    """Artist/label/playlist downloads must not be truncated to the first page."""
    qdl = QobuzDL(
        directory=tmp_path,
        no_m3u_for_playlists=no_m3u_for_playlists,
    )
    downloaded = []
    m3u_paths = []
    metadata_item_ids = []
    qdl.download_from_id = lambda item_id, album=True, alt_path=None: downloaded.append(
        (item_id, album, alt_path)
    )

    def paged_meta(self, item_id):
        metadata_item_ids.append(item_id)
        return iter(
            [
                {
                    "name": "Paged Collection",
                    item_key: {"items": [{"id": "item1"}, {"id": "item2"}]},
                },
                {
                    "name": "Paged Collection",
                    item_key: {"items": [{"id": "item3"}]},
                },
            ]
        )

    qdl.client = type("Client", (), {meta_method: paged_meta})()
    monkeypatch.setattr(
        "qobuz_dl.core.make_m3u",
        lambda playlist_path: m3u_paths.append(playlist_path),
    )

    qdl.handle_url(url)

    collection_path = str(tmp_path / "Paged Collection")
    assert metadata_item_ids == [expected_item_id]
    assert downloaded == [
        ("item1", expected_album, collection_path),
        ("item2", expected_album, collection_path),
        ("item3", expected_album, collection_path),
    ]
    if item_key == "tracks":
        assert m3u_paths == [collection_path] * expected_m3u_count
    else:
        assert m3u_paths == []


def test_smart_discography_filter_sees_albums_from_every_page():
    contents = [
        {
            "name": "Artist",
            "albums": {"items": [_album("First Album", "Artist", album_id="a-1")]},
        },
        {
            "name": "Artist",
            "albums": {"items": [_album("Second Album", "Artist", album_id="a-2")]},
        },
    ]

    filtered = smart_discography_filter(contents)

    assert sorted(album["id"] for album in filtered) == ["a-1", "a-2"]


def test_smart_discography_filter_drops_other_artists_and_duplicates():
    contents = [
        {
            "name": "Artist",
            "albums": {
                "items": [
                    _album("Great Album", "Artist", 24, 96, "hi-res"),
                    _album("Great Album", "Artist", 16, 44.1, "cd-quality"),
                    _album("Feature Album", "Someone Else", album_id="other"),
                ]
            },
        },
    ]

    filtered = smart_discography_filter(contents)

    assert [album["id"] for album in filtered] == ["hi-res"]


def test_smart_discography_filter_ignores_other_artists_before_quality_choice():
    contents = [
        {
            "name": "Artist",
            "albums": {
                "items": [
                    _album("Shared Title", "Artist", 16, 44.1, "requested-artist")
                ]
            },
        },
        {
            "name": "Artist",
            "albums": {
                "items": [
                    _album("Shared Title", "Someone Else", 24, 96, "other-artist")
                ]
            },
        },
    ]

    filtered = smart_discography_filter(contents)

    assert [album["id"] for album in filtered] == ["requested-artist"]


def test_lastfm_playlist_skips_tracks_without_qobuz_matches(tmp_path, monkeypatch):
    from pathlib import Path

    html = (Path(__file__).parent / "fixtures" / "lastfm_playlist.html").read_text()
    downloads = []

    monkeypatch.setattr("qobuz_dl.core.http.get_text", lambda url, timeout: html)
    monkeypatch.setattr("qobuz_dl.core.make_m3u", lambda path: None)

    qdl = QobuzDL(directory=tmp_path)

    searches = iter(
        [
            [],  # first track: no Qobuz match -> must be skipped, not crash
            ["https://play.qobuz.com/track/id2"],
        ]
    )
    qdl.search_by_type = lambda *args, **kwargs: next(searches)
    qdl.download_from_id = lambda item_id, album=True, alt_path=None: downloads.append(
        item_id
    )

    qdl.download_lastfm_pl("https://www.last.fm/user/example/library/playlists/1")

    assert downloads == ["id2"]
