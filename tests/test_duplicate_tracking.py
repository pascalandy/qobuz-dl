import sqlite3

from qobuz_dl.core import QobuzDL
from qobuz_dl.db import handle_download_id


def _record_downloads(monkeypatch, calls, failures=None):
    failures = failures if failures is not None else set()

    class FakeDownload:
        def __init__(
            self,
            client,
            item_id,
            path,
            quality,
            embed_art,
            albums_only,
            downgrade_quality,
            cover_og_quality,
            no_cover,
            folder_format,
            track_format,
        ):
            self.item_id = item_id
            self.path = path

        def download_id_by_type(self, track=True):
            if self.item_id in failures:
                raise ConnectionError("fake download failed")
            calls.append((self.item_id, track, self.path))

    monkeypatch.setattr("qobuz_dl.core.downloader.Download", FakeDownload)


def test_duplicate_db_records_successful_album_and_track_downloads(
    tmp_path, monkeypatch, caplog
):
    calls = []
    _record_downloads(monkeypatch, calls)
    db_path = tmp_path / "downloads.sqlite"
    qdl = QobuzDL(directory=tmp_path / "music", downloads_db=db_path)
    qdl.client = object()
    caplog.set_level("INFO", logger="qobuz_dl.core")

    qdl.download_from_id("album-1", album=True)
    qdl.download_from_id("track-1", album=False)
    qdl.download_from_id("album-1", album=True)
    qdl.download_from_id("track-1", album=False)

    assert [(item_id, is_track) for item_id, is_track, _path in calls] == [
        ("album-1", False),
        ("track-1", True),
    ]
    assert handle_download_id(db_path, "album-1") == ("album-1",)
    assert handle_download_id(db_path, "track-1") == ("track-1",)
    assert (
        sum("already downloaded" in record.getMessage() for record in caplog.records)
        == 2
    )


def test_duplicate_db_records_only_successful_downloads(tmp_path, monkeypatch):
    failures = {"album-1"}
    calls = []
    _record_downloads(monkeypatch, calls, failures)
    db_path = tmp_path / "downloads.sqlite"
    qdl = QobuzDL(directory=tmp_path / "music", downloads_db=db_path)
    qdl.client = object()

    qdl.download_from_id("album-1", album=True)
    failures.clear()
    qdl.download_from_id("album-1", album=True)

    assert [(item_id, is_track) for item_id, is_track, _path in calls] == [
        ("album-1", False),
    ]
    assert handle_download_id(db_path, "album-1") == ("album-1",)


def test_duplicate_db_skips_repeated_direct_text_and_queue_inputs(
    tmp_path, monkeypatch
):
    calls = []
    _record_downloads(monkeypatch, calls)
    db_path = tmp_path / "downloads.sqlite"
    text_file = tmp_path / "urls.txt"
    text_file.write_text(
        "\n".join(
            [
                "https://play.qobuz.com/album/album1",
                "https://play.qobuz.com/track/track2",
                "https://play.qobuz.com/track/track2",
            ]
        ),
        encoding="utf-8",
    )
    qdl = QobuzDL(directory=tmp_path / "music", downloads_db=db_path)
    qdl.client = object()

    qdl.download_list_of_urls(
        [
            "https://play.qobuz.com/album/album1",
            "https://play.qobuz.com/track/track1",
            "https://play.qobuz.com/album/album1",
            str(text_file),
            "https://play.qobuz.com/track/track1",
        ]
    )

    assert [(item_id, is_track) for item_id, is_track, _path in calls] == [
        ("album1", False),
        ("track1", True),
        ("track2", True),
    ]


def test_no_db_bypasses_duplicate_tracking_for_repeated_downloads(
    tmp_path, monkeypatch
):
    calls = []
    _record_downloads(monkeypatch, calls)
    qdl = QobuzDL(directory=tmp_path / "music", downloads_db=None)
    qdl.client = object()

    qdl.download_from_id("album-1", album=True)
    qdl.download_from_id("album-1", album=True)

    assert [(item_id, is_track) for item_id, is_track, _path in calls] == [
        ("album-1", False),
        ("album-1", False),
    ]
    assert qdl.downloads_db is None


def test_corrupt_duplicate_db_fails_open_without_blocking_downloads(
    tmp_path, monkeypatch, caplog
):
    calls = []
    _record_downloads(monkeypatch, calls)
    db_path = tmp_path / "downloads.sqlite"
    db_path.write_text("not a sqlite database", encoding="utf-8")
    caplog.set_level("ERROR", logger="qobuz_dl.db")

    qdl = QobuzDL(directory=tmp_path / "music", downloads_db=db_path)
    qdl.client = object()
    qdl.download_from_id("album-1", album=True)

    assert qdl.downloads_db is None
    assert [(item_id, is_track) for item_id, is_track, _path in calls] == [
        ("album-1", False),
    ]
    assert any(
        "Unexpected DB error" in record.getMessage() for record in caplog.records
    )


def test_legacy_duplicate_db_schema_fails_open_without_blocking_downloads(
    tmp_path, monkeypatch, caplog
):
    calls = []
    _record_downloads(monkeypatch, calls)
    db_path = tmp_path / "downloads.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE downloads (item_id TEXT UNIQUE NOT NULL);")
        conn.execute("INSERT INTO downloads (item_id) VALUES (?)", ("album-1",))
    caplog.set_level("ERROR", logger="qobuz_dl.db")

    qdl = QobuzDL(directory=tmp_path / "music", downloads_db=db_path)
    qdl.client = object()
    qdl.download_from_id("album-1", album=True)

    assert [(item_id, is_track) for item_id, is_track, _path in calls] == [
        ("album-1", False),
    ]
    assert any(
        "Unexpected DB error" in record.getMessage() for record in caplog.records
    )
