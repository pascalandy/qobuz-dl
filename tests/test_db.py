from qobuz_dl.db import create_db, handle_download_id


def test_create_db_returns_path_and_tracks_download_ids(tmp_path):
    db_path = tmp_path / "downloads.sqlite"

    returned_path = create_db(db_path)
    handle_download_id(db_path, "album-1", add_id=True)

    assert returned_path == db_path
    assert handle_download_id(db_path, "album-1") == ("album-1",)
    assert handle_download_id(db_path, "missing") is None


def test_handle_download_id_noops_without_db_path():
    assert handle_download_id(None, "album-1") is None
