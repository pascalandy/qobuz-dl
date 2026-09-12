from pathlib import Path

import pytest

from qobuz_dl import http
from qobuz_dl.core import QobuzDL

FIXTURES = Path(__file__).parent / "fixtures"


def test_lastfm_playlist_keeps_complete_rows_and_fragment_order(tmp_path, monkeypatch):
    html = (FIXTURES / "lastfm_row_pairs.html").read_text()
    queries = []
    downloads = []

    monkeypatch.setattr("qobuz_dl.core.http.get_text", lambda url, timeout: html)

    qdl = QobuzDL(directory=tmp_path, no_m3u_for_playlists=True)

    def fake_search(query, item_type, limit=10, lucky=False):
        queries.append((query, item_type, limit, lucky))
        return [f"https://play.qobuz.com/track/row{len(queries)}"]

    qdl.search_by_type = fake_search
    qdl.download_from_id = lambda item_id, album=True, alt_path=None: downloads.append(
        (item_id, album, alt_path)
    )

    qdl.download_lastfm_pl("https://www.last.fm/user/example/playlists/row-pairs")

    playlist_path = str(tmp_path / "Row Pairing Proof")
    assert queries == [
        ("Alpha Artist First Song & Dance", "track", 1, True),
        ("Repeat Artist Repeat Song", "track", 1, True),
        ("Repeat Artist Repeat Song", "track", 1, True),
        ("Gamma Artist Third Song", "track", 1, True),
    ]
    assert downloads == [
        ("row1", False, playlist_path),
        ("row2", False, playlist_path),
        ("row3", False, playlist_path),
        ("row4", False, playlist_path),
    ]


def test_lastfm_playlist_ignores_valueless_class_attributes(tmp_path, monkeypatch):
    html = """
    <h1>Valueless Class</h1>
    <table>
      <td class><a>Ignored Cell</a></td>
      <tr>
        <td class="chartlist-artist"><a>Valid Artist</a></td>
        <td class="chartlist-name"><a>Valid Song</a></td>
      </tr>
    </table>
    """
    queries = []
    downloads = []

    monkeypatch.setattr("qobuz_dl.core.http.get_text", lambda url, timeout: html)

    qdl = QobuzDL(directory=tmp_path, no_m3u_for_playlists=True)

    def fake_search(query, item_type, limit=10, lucky=False):
        queries.append((query, item_type, limit, lucky))
        return ["https://play.qobuz.com/track/validid"]

    qdl.search_by_type = fake_search
    qdl.download_from_id = lambda item_id, album=True, alt_path=None: downloads.append(
        (item_id, album, alt_path)
    )

    qdl.download_lastfm_pl("https://www.last.fm/user/example/playlists/valueless")

    playlist_path = str(tmp_path / "Valueless Class")
    assert queries == [("Valid Artist Valid Song", "track", 1, True)]
    assert downloads == [("validid", False, playlist_path)]


@pytest.mark.parametrize(
    ("no_m3u_for_playlists", "expected_m3u_count"),
    [(False, 1), (True, 0)],
)
def test_lastfm_playlist_parsing_sanitizes_title_downloads_found_tracks_and_obeys_m3u_flag(
    tmp_path, monkeypatch, no_m3u_for_playlists, expected_m3u_count
):
    html = (FIXTURES / "lastfm_playlist.html").read_text()
    requested_urls = []
    queries = []
    downloads = []
    m3u_paths = []

    def fake_get_text(url, timeout):
        requested_urls.append((url, timeout))
        return html

    qdl = QobuzDL(
        directory=tmp_path,
        no_m3u_for_playlists=no_m3u_for_playlists,
    )
    monkeypatch.setattr("qobuz_dl.core.http.get_text", fake_get_text)
    monkeypatch.setattr("qobuz_dl.core.make_m3u", lambda path: m3u_paths.append(path))

    def fake_search(query, item_type, limit=10, lucky=False):
        queries.append((query, item_type, limit, lucky))
        return [f"https://play.qobuz.com/track/id{len(queries)}"]

    qdl.search_by_type = fake_search
    qdl.download_from_id = lambda item_id, album=True, alt_path=None: downloads.append(
        (item_id, album, alt_path)
    )

    qdl.download_lastfm_pl("https://www.last.fm/user/example/library/playlists/1")

    playlist_path = str(tmp_path / "My Lastfm Playlist")
    assert requested_urls == [
        ("https://www.last.fm/user/example/library/playlists/1", 10)
    ]
    assert queries == [
        ("Alpha Artist First Song", "track", 1, True),
        ("Beta: Artist Second/Track", "track", 1, True),
    ]
    assert downloads == [
        ("id1", False, playlist_path),
        ("id2", False, playlist_path),
    ]
    assert m3u_paths == [playlist_path] * expected_m3u_count


def test_lastfm_playlist_with_no_usable_track_list_does_not_search_or_download(
    tmp_path, monkeypatch
):
    html = (FIXTURES / "lastfm_empty_playlist.html").read_text()
    search_calls = []
    downloads = []
    m3u_paths = []

    monkeypatch.setattr("qobuz_dl.core.http.get_text", lambda url, timeout: html)
    monkeypatch.setattr("qobuz_dl.core.make_m3u", lambda path: m3u_paths.append(path))

    qdl = QobuzDL(directory=tmp_path)
    qdl.search_by_type = lambda *args, **kwargs: search_calls.append((args, kwargs))
    qdl.download_from_id = lambda *args, **kwargs: downloads.append((args, kwargs))

    qdl.download_lastfm_pl("https://www.last.fm/user/example/library/playlists/empty")

    assert search_calls == []
    assert downloads == []
    assert m3u_paths == []


@pytest.mark.parametrize(
    "http_error",
    [
        http.HttpRequestError("unknown url type"),
        http.HttpStatusError(503, b"service unavailable"),
    ],
    ids=["request-error", "status-error"],
)
def test_lastfm_playlist_http_errors_do_not_escape(
    tmp_path, monkeypatch, caplog, http_error
):
    search_calls = []
    downloads = []
    m3u_paths = []

    def fake_get_text(url, timeout):
        raise http_error

    monkeypatch.setattr("qobuz_dl.core.http.get_text", fake_get_text)
    monkeypatch.setattr("qobuz_dl.core.make_m3u", lambda path: m3u_paths.append(path))

    qdl = QobuzDL(directory=tmp_path)
    qdl.search_by_type = lambda *args, **kwargs: search_calls.append((args, kwargs))
    qdl.download_from_id = lambda *args, **kwargs: downloads.append((args, kwargs))
    caplog.set_level("ERROR", logger="qobuz_dl.core")

    qdl.download_lastfm_pl("www.last.fm/user/example/library/playlists/1")

    assert search_calls == []
    assert downloads == []
    assert m3u_paths == []
    assert any(
        "Playlist download failed" in record.getMessage() for record in caplog.records
    )
