import hashlib
import os
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from qobuz_dl import db, downloader
from qobuz_dl.core import QobuzDL
from qobuz_dl.db import DownloadHistory, MediaProperties, VerifiedArtifact
from qobuz_dl.downloader import Download, DownloadResult

FIXTURES = Path(__file__).parent / "fixtures"


def _rows(path, query):
    with sqlite3.connect(path) as connection:
        return connection.execute(query).fetchall()


def _create_artifacts_table(connection, *, constraints=True):
    checks = "CHECK (codec IN ('flac','mp3'))" if constraints else ""
    sample_rate_check = "CHECK (sample_rate_hz > 0)" if constraints else ""
    bitrate_check = (
        "CHECK (bitrate_bps IS NULL OR bitrate_bps > 0)" if constraints else ""
    )
    size_check = "CHECK (size_bytes > 0)" if constraints else ""
    digest_check = "CHECK (length(sha256)=64)" if constraints else ""
    media_check = (
        "CHECK ((codec='flac' AND bit_depth IS NOT NULL AND bit_depth>0) "
        "OR (codec='mp3' AND bit_depth IS NULL AND bitrate_bps IS NOT NULL "
        "AND bitrate_bps>0))"
        if constraints
        else ""
    )
    table_check = f", {media_check}" if media_check else ""
    connection.execute(
        "CREATE TABLE artifacts ("
        "path TEXT PRIMARY KEY NOT NULL, "
        "track_id TEXT NOT NULL, "
        "requested_quality INTEGER NOT NULL, "
        f"codec TEXT NOT NULL {checks}, "
        "bit_depth INTEGER, "
        f"sample_rate_hz INTEGER NOT NULL {sample_rate_check}, "
        f"bitrate_bps INTEGER {bitrate_check}, "
        f"size_bytes INTEGER NOT NULL {size_check}, "
        f"sha256 TEXT NOT NULL {digest_check}"
        f"{table_check})"
    )
    connection.execute("CREATE INDEX artifacts_track_id_idx ON artifacts (track_id)")


def _copy_fixture(tmp_path, extension):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"track.{extension}"
    shutil.copyfile(FIXTURES / f"synthetic-silence.{extension}", path)
    return path


def _track(track_id="track-1", title="Track", track_number=1):
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


def _album(tracks):
    return {
        "id": "album-1",
        "streamable": True,
        "release_type": "album",
        "title": "Album",
        "artist": {"name": "Album Artist"},
        "release_date_original": "2024-01-02",
        "image": {"large": "https://images.example.test/cover.jpg"},
        "tracks": {"items": tracks},
        "tracks_count": len(tracks),
        "genres_list": ["Rock"],
        "label": {"name": "Label"},
        "copyright": "",
    }


def _track_metadata(track):
    return {
        **track,
        "album": {
            "id": "album-1",
            "title": "Album",
            "artist": {"name": "Album Artist"},
            "release_date_original": "2024-01-02",
            "image": {"large": "https://images.example.test/cover.jpg"},
            "tracks_count": 1,
            "genres_list": ["Rock"],
            "label": {"name": "Label"},
        },
        "copyright": "",
    }


class _Client:
    def __init__(self, tracks):
        self.tracks = tracks

    def get_album_meta(self, item_id):
        assert item_id == "album-1"
        return _album(self.tracks)

    def get_track_meta(self, item_id):
        track = next(track for track in self.tracks if track["id"] == item_id)
        return _track_metadata(track)

    def get_track_url(self, item_id, fmt_id):
        return {
            "url": f"https://media.example.test/{item_id}.flac",
            "sampling_rate": 44.1,
            "bit_depth": 16,
            "format_id": 6,
            "mime_type": "audio/flac",
        }


def _download(history, tmp_path, *, tracks=None):
    return Download(
        _Client(tracks or [_track()]),
        "album-1" if tracks else "track-1",
        str(tmp_path / "music"),
        6,
        no_cover=True,
        folder_format="album",
        track_format="{tracknumber}. {tracktitle}",
        download_history=history,
    )


def _install_fixture_download(monkeypatch, *, failing_track=None):
    def copy_fixture(
        _url,
        filename,
        _description,
        *,
        retry_rate_limited=False,
    ):
        shutil.copyfile(FIXTURES / "synthetic-silence.flac", filename)

    def rename(filename, _root, final_path, track, *_args, finalize=True):
        if track["id"] == failing_track:
            raise RuntimeError("tagging failed")
        if finalize:
            os.replace(filename, final_path)

    monkeypatch.setattr(downloader, "download_with_progress", copy_fixture)
    monkeypatch.setattr(downloader.metadata, "tag_flac", rename)


def test_fresh_database_has_versioned_artifact_schema(tmp_path):
    database = tmp_path / "history.sqlite"

    history = DownloadHistory.open(database)

    assert history.enabled is True
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall() == [("artifacts",), ("downloads",)]
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='artifacts' AND sql IS NOT NULL"
        ).fetchall() == [("artifacts_track_id_idx",)]


def test_legacy_schema_migrates_once_without_fabricating_artifacts(tmp_path):
    database = tmp_path / "history.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE downloads (id TEXT UNIQUE NOT NULL)")
        connection.execute("INSERT INTO downloads VALUES ('album-1')")

    first = DownloadHistory.open(database)
    second = DownloadHistory.open(database)

    assert first.contains_legacy_id("album-1") is True
    assert second.contains_legacy_id("album-1") is True
    assert _rows(database, "SELECT * FROM artifacts") == []
    assert _rows(database, "PRAGMA user_version") == [(1,)]


def test_failed_migration_rolls_back_every_statement(tmp_path, monkeypatch):
    database = tmp_path / "history.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE downloads (id TEXT UNIQUE NOT NULL)")
        connection.execute("INSERT INTO downloads VALUES ('album-1')")

    real_connect = sqlite3.connect

    class FailingConnection:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, statement, parameters=()):
            if statement == "PRAGMA user_version=1":
                raise sqlite3.OperationalError("injected migration failure")
            return self.connection.execute(statement, parameters)

        def close(self):
            self.connection.close()

    monkeypatch.setattr(
        db.sqlite3,
        "connect",
        lambda *args, **kwargs: FailingConnection(real_connect(*args, **kwargs)),
    )

    history = DownloadHistory.open(database)

    assert history.enabled is False
    with real_connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (0,)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall() == [("downloads",)]
        assert connection.execute("SELECT id FROM downloads").fetchall() == [
            ("album-1",)
        ]


@pytest.mark.parametrize("unsupported", ["version", "schema"])
def test_unsupported_database_is_disabled_without_modification(tmp_path, unsupported):
    database = tmp_path / "history.sqlite"
    with sqlite3.connect(database) as connection:
        if unsupported == "version":
            connection.execute("PRAGMA user_version=99")
        else:
            connection.execute("CREATE TABLE downloads (item_id TEXT NOT NULL)")

    before = database.read_bytes()
    history = DownloadHistory.open(database)

    assert history.enabled is False
    assert database.read_bytes() == before


@pytest.mark.parametrize("version", [0, 1])
@pytest.mark.parametrize("lookalike", ["partial", "nocase", "generated"])
def test_downloads_schema_lookalikes_are_rejected(tmp_path, version, lookalike):
    database = tmp_path / "history.sqlite"
    with sqlite3.connect(database) as connection:
        if lookalike == "partial":
            connection.execute("CREATE TABLE downloads (id TEXT NOT NULL)")
            connection.execute(
                "CREATE UNIQUE INDEX downloads_id_unique ON downloads (id) "
                "WHERE id <> ''"
            )
        elif lookalike == "nocase":
            connection.execute(
                "CREATE TABLE downloads (id TEXT COLLATE NOCASE UNIQUE NOT NULL)"
            )
        else:
            connection.execute(
                "CREATE TABLE downloads ("
                "id TEXT UNIQUE NOT NULL, "
                "shadow TEXT GENERATED ALWAYS AS (id) VIRTUAL)"
            )
        if version == 1:
            _create_artifacts_table(connection)
            connection.execute("PRAGMA user_version=1")

    history = DownloadHistory.open(database)

    assert history.enabled is False


@pytest.mark.parametrize(
    "lookalike", ["missing_checks", "partial_index", "nocase_index", "hidden_column"]
)
def test_artifacts_schema_lookalikes_are_rejected(tmp_path, lookalike):
    database = tmp_path / "history.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE downloads (id TEXT UNIQUE NOT NULL)")
        _create_artifacts_table(
            connection,
            constraints=lookalike != "missing_checks",
        )
        if lookalike in {"partial_index", "nocase_index"}:
            connection.execute("DROP INDEX artifacts_track_id_idx")
            suffix = " COLLATE NOCASE" if lookalike == "nocase_index" else ""
            predicate = " WHERE track_id <> ''" if lookalike == "partial_index" else ""
            connection.execute(
                "CREATE INDEX artifacts_track_id_idx ON artifacts "
                f"(track_id{suffix}){predicate}"
            )
        elif lookalike == "hidden_column":
            connection.execute(
                "ALTER TABLE artifacts ADD shadow TEXT "
                "GENERATED ALWAYS AS (track_id) VIRTUAL"
            )
        connection.execute("PRAGMA user_version=1")

    history = DownloadHistory.open(database)

    assert history.enabled is False


@pytest.mark.parametrize(
    ("extension", "expected_media"),
    [
        ("flac", MediaProperties("flac", 16, 44100, 5440)),
    ],
)
def test_real_media_facts_and_full_digest_are_persisted(
    tmp_path, extension, expected_media
):
    database = tmp_path / "history.sqlite"
    media_path = _copy_fixture(tmp_path, extension)
    history = DownloadHistory.open(database)

    artifact = history.record_finalized(
        track_id="track-1",
        path=media_path,
        requested_quality=5 if extension == "mp3" else 6,
    )

    assert artifact == VerifiedArtifact(
        track_id="track-1",
        path=os.path.normcase(os.path.abspath(media_path)),
        requested_quality=5 if extension == "mp3" else 6,
        media=expected_media,
        size_bytes=media_path.stat().st_size,
        sha256=hashlib.sha256(media_path.read_bytes()).hexdigest(),
    )
    assert history.verified_artifact("track-1", media_path) == artifact


def test_unknown_bitrate_mode_mp3_fixture_is_not_verified(tmp_path):
    media_path = _copy_fixture(tmp_path, "mp3")

    assert DownloadHistory.inspect_artifact("track-1", media_path, 5) is None


@pytest.mark.parametrize(
    ("bitrate_mode", "accepted"),
    [
        (db.BitrateMode.CBR, True),
        (db.BitrateMode.UNKNOWN, False),
        (db.BitrateMode.ABR, False),
        (db.BitrateMode.VBR, False),
        (None, False),
    ],
)
def test_mp3_inspection_requires_cbr(tmp_path, monkeypatch, bitrate_mode, accepted):
    media_path = _copy_fixture(tmp_path, "mp3")

    class ParsedInfo:
        sample_rate = 44100
        bitrate = 320000

    if bitrate_mode is not None:
        ParsedInfo.bitrate_mode = bitrate_mode

    class ParsedMp3:
        info = ParsedInfo()

    monkeypatch.setattr(db, "MP3", lambda _stream: ParsedMp3())

    artifact = DownloadHistory.inspect_artifact("track-1", media_path, 5)

    if accepted:
        assert artifact is not None
        assert artifact.media == MediaProperties("mp3", None, 44100, 320000)
    else:
        assert artifact is None


def test_path_key_supports_multiple_destinations_qualities_and_upsert(tmp_path):
    database = tmp_path / "history.sqlite"
    first = _copy_fixture(tmp_path / "first", "flac")
    second = _copy_fixture(tmp_path / "second", "flac")
    history = DownloadHistory.open(database)

    history.record_finalized(track_id="track-1", path=first, requested_quality=6)
    history.record_finalized(track_id="track-1", path=second, requested_quality=27)
    history.record_finalized(track_id="track-2", path=first, requested_quality=7)

    assert _rows(
        database,
        "SELECT path, track_id, requested_quality FROM artifacts ORDER BY path",
    ) == [
        (os.path.normcase(os.path.abspath(first)), "track-2", 7),
        (os.path.normcase(os.path.abspath(second)), "track-1", 27),
    ]


def test_deleted_and_equal_size_replaced_files_are_not_verified(tmp_path):
    database = tmp_path / "history.sqlite"
    deleted = _copy_fixture(tmp_path / "deleted", "flac")
    replaced = _copy_fixture(tmp_path / "replaced", "flac")
    history = DownloadHistory.open(database)
    history.record_finalized(track_id="deleted", path=deleted, requested_quality=6)
    history.record_finalized(track_id="replaced", path=replaced, requested_quality=6)

    deleted.unlink()
    replacement = bytearray(replaced.read_bytes())
    replacement[-1] ^= 1
    replaced.write_bytes(replacement)

    assert history.verified_artifact("deleted", deleted) is None
    assert history.verified_artifact("replaced", replaced) is None


def test_dotdot_after_parent_symlink_is_rejected_before_lexical_normalization(
    tmp_path,
):
    lexical_target = _copy_fixture(tmp_path / "base", "flac")
    traversal_target = _copy_fixture(tmp_path / "target", "flac")
    nested = tmp_path / "target" / "nested"
    nested.mkdir()
    link = tmp_path / "base" / "link"
    try:
        link.symlink_to(nested, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")
    adversarial_path = link / ".." / traversal_target.name
    assert adversarial_path.read_bytes() == traversal_target.read_bytes()
    assert os.path.abspath(adversarial_path) == str(lexical_target)
    history = DownloadHistory.open(tmp_path / "history.sqlite")

    artifact = history.record_finalized(
        track_id="track-1", path=adversarial_path, requested_quality=6
    )

    assert artifact is None
    assert _rows(tmp_path / "history.sqlite", "SELECT * FROM artifacts") == []


def test_final_symlink_is_rejected_but_parent_symlink_spelling_is_preserved(tmp_path):
    target = _copy_fixture(tmp_path / "target", "flac")
    parent_link = tmp_path / "music"
    final_link = tmp_path / "final.flac"
    try:
        parent_link.symlink_to(target.parent, target_is_directory=True)
        final_link.symlink_to(target)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")
    spelled_path = parent_link / target.name
    history = DownloadHistory.open(tmp_path / "history.sqlite")

    preserved = history.record_finalized(
        track_id="track-1", path=spelled_path, requested_quality=6
    )
    rejected = history.record_finalized(
        track_id="track-2", path=final_link, requested_quality=6
    )

    assert preserved is not None
    assert preserved.path == os.path.normcase(os.path.abspath(spelled_path))
    assert rejected is None
    assert _rows(
        tmp_path / "history.sqlite", "SELECT path, track_id FROM artifacts"
    ) == [(preserved.path, "track-1")]


def test_unstable_file_is_rejected(tmp_path, monkeypatch):
    media_path = _copy_fixture(tmp_path, "flac")
    history = DownloadHistory.open(tmp_path / "history.sqlite")
    real_fstat = db.os.fstat
    calls = 0

    def changing_fstat(descriptor):
        nonlocal calls
        calls += 1
        current = real_fstat(descriptor)
        if calls == 2:
            values = list(current)
            values[6] += 1
            return os.stat_result(values)
        return current

    monkeypatch.setattr(db.os, "fstat", changing_fstat)

    assert (
        history.record_finalized(
            track_id="track-1", path=media_path, requested_quality=6
        )
        is None
    )
    assert _rows(tmp_path / "history.sqlite", "SELECT * FROM artifacts") == []


def test_stable_file_accepts_source_specific_ctime_semantics(tmp_path, monkeypatch):
    media_path = _copy_fixture(tmp_path, "flac")
    history = DownloadHistory.open(tmp_path / "history.sqlite")
    real_fstat = db.os.fstat
    real_lstat = db.os.lstat

    def with_ctime(metadata, ctime_ns):
        return SimpleNamespace(
            st_dev=metadata.st_dev,
            st_ino=metadata.st_ino,
            st_mode=metadata.st_mode,
            st_size=metadata.st_size,
            st_mtime_ns=metadata.st_mtime_ns,
            st_ctime_ns=ctime_ns,
        )

    monkeypatch.setattr(
        db.os,
        "fstat",
        lambda descriptor: with_ctime(real_fstat(descriptor), 2_000_000_000),
    )
    monkeypatch.setattr(
        db.os,
        "lstat",
        lambda path: with_ctime(real_lstat(path), 1_000_000_000),
    )

    artifact = history.record_finalized(
        track_id="track-1", path=media_path, requested_quality=6
    )

    assert artifact is not None
    assert artifact.path == os.path.normcase(os.path.abspath(media_path))


@pytest.mark.parametrize("kind", ["nonregular", "malformed", "unsupported"])
def test_invalid_finalized_files_are_rejected(tmp_path, kind):
    if kind == "nonregular":
        media_path = tmp_path / "directory.flac"
        media_path.mkdir()
    elif kind == "malformed":
        media_path = tmp_path / "broken.flac"
        media_path.write_bytes(b"not flac")
    else:
        media_path = tmp_path / "track.ogg"
        shutil.copyfile(FIXTURES / "synthetic-silence.flac", media_path)
    database = tmp_path / "history.sqlite"
    history = DownloadHistory.open(database)

    artifact = history.record_finalized(
        track_id="track-1", path=media_path, requested_quality=6
    )

    assert artifact is None
    assert _rows(database, "SELECT * FROM artifacts") == []


def test_only_new_post_tag_success_records_artifact(tmp_path, monkeypatch):
    history = DownloadHistory.open(tmp_path / "history.sqlite")
    _install_fixture_download(monkeypatch)
    successful = _download(history, tmp_path)

    result = successful.download_track()
    final_path = Path(result.finalized_paths[0])

    assert result == DownloadResult("finalized", "downloaded", (str(final_path),))
    assert history.verified_artifact("track-1", final_path) is not None

    other_history = DownloadHistory.open(tmp_path / "other.sqlite")
    existing = _download(other_history, tmp_path)
    assert existing.download_track() == DownloadResult(
        "finalized", "existing_file", (str(final_path),)
    )
    assert _rows(tmp_path / "other.sqlite", "SELECT * FROM artifacts") == []


def test_tag_failure_does_not_record_artifact(tmp_path, monkeypatch):
    history = DownloadHistory.open(tmp_path / "history.sqlite")
    _install_fixture_download(monkeypatch, failing_track="track-1")

    result = _download(history, tmp_path).download_track()

    assert result == DownloadResult("failed", "tagging_error")
    assert _rows(tmp_path / "history.sqlite", "SELECT * FROM artifacts") == []


def test_partial_album_records_only_successful_children(tmp_path, monkeypatch):
    tracks = [_track("track-1", "First", 1), _track("track-2", "Second", 2)]
    history = DownloadHistory.open(tmp_path / "history.sqlite")
    _install_fixture_download(monkeypatch, failing_track="track-2")

    result = _download(history, tmp_path, tracks=tracks).download_release()

    assert result.state == "failed"
    assert result.reason == "tagging_error"
    assert _rows(
        tmp_path / "history.sqlite", "SELECT track_id FROM artifacts ORDER BY track_id"
    ) == [("track-1",)]


def test_sqlite_write_error_sticky_disables_history_and_keeps_media_facts(
    tmp_path, caplog
):
    database = tmp_path / "history.sqlite"
    media_path = _copy_fixture(tmp_path, "flac")
    history = DownloadHistory.open(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TRIGGER reject_artifact BEFORE INSERT ON artifacts "
            "BEGIN SELECT RAISE(FAIL, 'write rejected'); END"
        )
    caplog.set_level("ERROR", logger="qobuz_dl.db")

    artifact = history.record_finalized(
        track_id="track-1", path=media_path, requested_quality=6
    )
    history.record_legacy_id("album-1")

    assert artifact is not None
    assert history.enabled is False
    assert history.verified_artifact("track-1", media_path) == artifact
    assert history.contains_legacy_id("album-1") is False
    assert _rows(database, "SELECT * FROM artifacts") == []
    assert _rows(database, "SELECT * FROM downloads") == []
    assert any(
        "track-1" in record.getMessage()
        and hashlib.sha256(media_path.read_bytes()).hexdigest() in record.getMessage()
        for record in caplog.records
    )


def test_integer_track_id_round_trips_as_a_string(tmp_path):
    database = tmp_path / "history.sqlite"
    media_path = _copy_fixture(tmp_path, "flac")
    history = DownloadHistory.open(database)

    recorded = history.record_finalized(
        track_id=12345, path=media_path, requested_quality=6
    )

    assert recorded is not None
    assert recorded.track_id == "12345"
    assert history.verified_artifact(12345, media_path) == recorded
    assert _rows(database, "SELECT track_id, typeof(track_id) FROM artifacts") == [
        ("12345", "text")
    ]


def test_cross_thread_sqlite_error_sticky_disables_without_cleanup_error(tmp_path):
    history = DownloadHistory.open(tmp_path / "history.sqlite")

    with ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(history.contains_legacy_id, "album-1").result()

    assert result is False
    assert history.enabled is False
    assert history.contains_legacy_id("album-1") is False
    history.record_legacy_id("album-1")
    assert history.enabled is False


def test_download_result_stays_successful_when_artifact_write_fails(
    tmp_path, monkeypatch
):
    database = tmp_path / "history.sqlite"
    qobuz = QobuzDL(
        directory=tmp_path / "music",
        quality=6,
        no_cover=True,
        downloads_db=database,
        folder_format="album",
        track_format="{tracknumber}. {tracktitle}",
    )
    qobuz.client = _Client([_track()])
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TRIGGER reject_artifact BEFORE INSERT ON artifacts "
            "BEGIN SELECT RAISE(FAIL, 'write rejected'); END"
        )
    _install_fixture_download(monkeypatch)

    result = qobuz.download_from_id("track-1", album=False)
    reused = qobuz.download_from_id("track-1", album=False)

    assert result.state == "finalized"
    assert result.reason == "downloaded"
    assert reused == DownloadResult(
        "finalized", "verified_artifact", result.finalized_paths
    )
    assert Path(result.finalized_paths[0]).is_file()
    assert qobuz.download_history.enabled is False
    assert _rows(database, "SELECT * FROM artifacts") == []
    assert _rows(database, "SELECT * FROM downloads") == []


def test_no_db_open_does_not_touch_paths_or_sqlite(monkeypatch):
    monkeypatch.setattr(
        db.sqlite3, "connect", lambda *_args, **_kwargs: pytest.fail("sqlite access")
    )
    monkeypatch.setattr(
        db.os.path, "abspath", lambda *_args, **_kwargs: pytest.fail("path access")
    )

    history = DownloadHistory.open(None)

    assert history.enabled is False
    assert history.contains_legacy_id("album-1") is False
