from pathlib import Path

from qobuz_dl import http
from qobuz_dl.core import QobuzDL

FIXTURES = Path(__file__).parent / "fixtures"


def test_lastfm_playlist_parsing_sanitizes_title_and_downloads_found_tracks(
    tmp_path, monkeypatch
):
    html = (FIXTURES / "lastfm_playlist.html").read_text()
    requested_urls = []
    queries = []
    downloads = []
    m3u_paths = []

    def fake_get_text(url, timeout):
        requested_urls.append((url, timeout))
        return html

    qdl = QobuzDL(directory=tmp_path)
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
    assert m3u_paths == [playlist_path]


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


def test_lastfm_playlist_request_errors_do_not_escape(tmp_path, monkeypatch):
    search_calls = []

    def fake_get_text(url, timeout):
        raise http.HttpRequestError("unknown url type")

    monkeypatch.setattr("qobuz_dl.core.http.get_text", fake_get_text)

    qdl = QobuzDL(directory=tmp_path)
    qdl.search_by_type = lambda *args, **kwargs: search_calls.append((args, kwargs))

    qdl.download_lastfm_pl("www.last.fm/user/example/library/playlists/1")

    assert search_calls == []
