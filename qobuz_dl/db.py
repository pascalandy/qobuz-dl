import hashlib
import logging
import os
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mutagen import MutagenError
from mutagen.flac import FLAC
from mutagen.mp3 import MP3, BitrateMode

from qobuz_dl.color import RED, YELLOW

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class MediaProperties:
    codec: Literal["flac", "mp3"]
    bit_depth: int | None
    sample_rate_hz: int
    bitrate_bps: int | None


@dataclass(frozen=True)
class VerifiedArtifact:
    track_id: str
    path: str
    requested_quality: int
    media: MediaProperties
    size_bytes: int
    sha256: str


class _UnsupportedDatabaseError(Exception):
    pass


def _normalized_path(path: str | os.PathLike[str]) -> str:
    raw_path = os.fspath(path)
    if os.pardir in Path(raw_path).parts:
        raise ValueError("parent traversal is not supported")
    return os.path.normcase(os.path.abspath(raw_path))


def _file_snapshot(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _positive_integer(value) -> int | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return int(value)


def _inspect_artifact(
    *,
    track_id: str,
    path: str | os.PathLike[str],
    requested_quality: int,
) -> VerifiedArtifact | None:
    try:
        normalized = _normalized_path(path)
    except (OSError, TypeError, ValueError):
        return None
    extension = Path(normalized).suffix.lower()
    if extension not in {".flac", ".mp3"}:
        return None

    try:
        path_metadata = os.lstat(normalized)
        if stat.S_ISLNK(path_metadata.st_mode) or not stat.S_ISREG(
            path_metadata.st_mode
        ):
            return None
    except OSError:
        return None

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(normalized, flags)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            path_before = os.lstat(normalized)
            if (
                not stat.S_ISREG(before.st_mode)
                or stat.S_ISLNK(path_before.st_mode)
                or not os.path.samestat(before, path_before)
            ):
                return None

            if extension == ".flac":
                audio = FLAC(stream)
                codec: Literal["flac", "mp3"] = "flac"
                bit_depth = _positive_integer(audio.info.bits_per_sample)
            else:
                audio = MP3(stream)
                codec = "mp3"
                bit_depth = None
                if getattr(audio.info, "bitrate_mode", None) != BitrateMode.CBR:
                    return None

            sample_rate = _positive_integer(audio.info.sample_rate)
            bitrate = _positive_integer(getattr(audio.info, "bitrate", None))
            if sample_rate is None or (codec == "flac" and bit_depth is None):
                return None

            stream.seek(0)
            hasher = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
            digest = hasher.hexdigest()
            after = os.fstat(stream.fileno())
            path_after = os.lstat(normalized)
            if (
                _file_snapshot(before) != _file_snapshot(after)
                or stat.S_ISLNK(path_after.st_mode)
                or not os.path.samestat(after, path_after)
                or _file_snapshot(path_before) != _file_snapshot(path_after)
            ):
                return None
    except (OSError, MutagenError, EOFError, TypeError, ValueError):
        return None

    return VerifiedArtifact(
        track_id=str(track_id),
        path=normalized,
        requested_quality=requested_quality,
        media=MediaProperties(
            codec=codec,
            bit_depth=bit_depth,
            sample_rate_hz=sample_rate,
            bitrate_bps=bitrate,
        ),
        size_bytes=after.st_size,
        sha256=digest,
    )


def _table_names(connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        )
    }


def _table_columns(
    connection, table: str
) -> list[tuple[str, str, int, object, int, int]]:
    return [
        (row[1], row[2].upper(), row[3], row[4], row[5], row[6])
        for row in connection.execute(f"PRAGMA table_xinfo('{table}')")
    ]


def _has_index(
    connection,
    table: str,
    *,
    name: str | None,
    unique: bool,
    origin: str,
    columns: list[tuple[str, str]],
) -> bool:
    for index in connection.execute(f"PRAGMA index_list('{table}')"):
        if (
            (name is not None and index[1] != name)
            or bool(index[2]) is not unique
            or index[3] != origin
            or bool(index[4])
        ):
            continue
        indexed_columns = connection.execute(
            "SELECT name, coll FROM pragma_index_xinfo(?) WHERE key=1 ORDER BY seqno",
            (index[1],),
        ).fetchall()
        if indexed_columns == columns:
            return True
    return False


def _downloads_schema_supported(connection) -> bool:
    if _table_columns(connection, "downloads") != [("id", "TEXT", 1, None, 0, 0)]:
        return False
    return _has_index(
        connection,
        "downloads",
        name=None,
        unique=True,
        origin="u",
        columns=[("id", "BINARY")],
    )


def _artifact_constraints_supported(connection) -> bool:
    insert = (
        "INSERT INTO artifacts ("
        "path, track_id, requested_quality, codec, bit_depth, "
        "sample_rate_hz, bitrate_bps, size_bytes, sha256"
        ") VALUES (?, 'schema-check', 6, ?, ?, ?, ?, ?, ?)"
    )
    valid = ("flac", 16, 1, None, 1, "0" * 64)
    invalid = [
        ("ogg", 16, 1, None, 1, "0" * 64),
        ("flac", 16, 0, None, 1, "0" * 64),
        ("flac", 16, 1, 0, 1, "0" * 64),
        ("flac", 16, 1, None, 0, "0" * 64),
        ("flac", 16, 1, None, 1, "0" * 63),
        ("flac", None, 1, None, 1, "0" * 64),
        ("mp3", 16, 1, 32000, 1, "0" * 64),
        ("mp3", None, 1, None, 1, "0" * 64),
    ]
    connection.execute("SAVEPOINT artifact_schema_check")
    try:
        connection.execute(insert, ("\x00qdl-schema-valid", *valid))
        for index, values in enumerate(invalid):
            try:
                connection.execute(insert, (f"\x00qdl-schema-invalid-{index}", *values))
            except sqlite3.IntegrityError:
                continue
            return False
        return True
    except sqlite3.Error:
        return False
    finally:
        connection.execute("ROLLBACK TO artifact_schema_check")
        connection.execute("RELEASE artifact_schema_check")


def _artifacts_schema_supported(connection) -> bool:
    expected_columns = [
        ("path", "TEXT", 1, None, 1, 0),
        ("track_id", "TEXT", 1, None, 0, 0),
        ("requested_quality", "INTEGER", 1, None, 0, 0),
        ("codec", "TEXT", 1, None, 0, 0),
        ("bit_depth", "INTEGER", 0, None, 0, 0),
        ("sample_rate_hz", "INTEGER", 1, None, 0, 0),
        ("bitrate_bps", "INTEGER", 0, None, 0, 0),
        ("size_bytes", "INTEGER", 1, None, 0, 0),
        ("sha256", "TEXT", 1, None, 0, 0),
    ]
    if _table_columns(connection, "artifacts") != expected_columns:
        return False
    if not _has_index(
        connection,
        "artifacts",
        name=None,
        unique=True,
        origin="pk",
        columns=[("path", "BINARY")],
    ):
        return False
    if not _has_index(
        connection,
        "artifacts",
        name="artifacts_track_id_idx",
        unique=False,
        origin="c",
        columns=[("track_id", "BINARY")],
    ):
        return False
    return _artifact_constraints_supported(connection)


def _validate_current_schema(connection) -> None:
    if _table_names(connection) != {"downloads", "artifacts"}:
        raise _UnsupportedDatabaseError("unsupported version-1 tables")
    if not _downloads_schema_supported(connection):
        raise _UnsupportedDatabaseError("unsupported downloads table")
    if not _artifacts_schema_supported(connection):
        raise _UnsupportedDatabaseError("unsupported artifacts table")


def _migrate(connection) -> bool:
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            _validate_current_schema(connection)
            connection.execute("COMMIT")
            return False
        if version != 0:
            raise _UnsupportedDatabaseError(f"unsupported database version {version}")

        tables = _table_names(connection)
        if tables == set():
            connection.execute("CREATE TABLE downloads (id TEXT UNIQUE NOT NULL)")
        elif tables != {"downloads"} or not _downloads_schema_supported(connection):
            raise _UnsupportedDatabaseError("unsupported version-0 schema")

        connection.execute(
            "CREATE TABLE artifacts ("
            "path TEXT PRIMARY KEY NOT NULL, "
            "track_id TEXT NOT NULL, "
            "requested_quality INTEGER NOT NULL, "
            "codec TEXT NOT NULL CHECK (codec IN ('flac','mp3')), "
            "bit_depth INTEGER, "
            "sample_rate_hz INTEGER NOT NULL CHECK (sample_rate_hz > 0), "
            "bitrate_bps INTEGER CHECK (bitrate_bps IS NULL OR bitrate_bps > 0), "
            "size_bytes INTEGER NOT NULL CHECK (size_bytes > 0), "
            "sha256 TEXT NOT NULL CHECK (length(sha256)=64), "
            "CHECK ((codec='flac' AND bit_depth IS NOT NULL AND bit_depth>0) "
            "OR (codec='mp3' AND bit_depth IS NULL AND bitrate_bps IS NOT NULL "
            "AND bitrate_bps>0)))"
        )
        connection.execute(
            "CREATE INDEX artifacts_track_id_idx ON artifacts (track_id)"
        )
        _validate_current_schema(connection)
        connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        connection.execute("COMMIT")
        return True
    except BaseException:
        connection.execute("ROLLBACK")
        raise


class DownloadHistory:
    def __init__(self, path, connection):
        self._path = path
        self._connection = connection
        self._run_artifacts: dict[tuple[str, str], VerifiedArtifact] = {}

    @classmethod
    def open(cls, path: str | os.PathLike[str] | None) -> "DownloadHistory":
        if path is None:
            return cls(None, None)

        connection = None
        try:
            connection = sqlite3.connect(path, isolation_level=None)
            created = _migrate(connection)
        except (sqlite3.Error, _UnsupportedDatabaseError, OSError) as error:
            if connection is not None:
                connection.close()
            logger.error(f"{RED}Unexpected DB error: {error}")
            return cls(path, None)

        if created:
            logger.info(f"{YELLOW}Download-IDs database created")
        return cls(path, connection)

    @property
    def enabled(self) -> bool:
        return self._connection is not None

    @property
    def path(self):
        return self._path if self.enabled else None

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _disable(self, error: sqlite3.Error) -> None:
        connection = self._connection
        self._connection = None
        if connection is not None:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            try:
                connection.close()
            except sqlite3.Error:
                pass
        logger.error(f"{RED}Unexpected DB error: {error}")

    def contains_legacy_id(self, item_id: str) -> bool:
        if self._connection is None:
            return False
        try:
            row = self._connection.execute(
                "SELECT id FROM downloads WHERE id=?", (str(item_id),)
            ).fetchone()
        except sqlite3.Error as error:
            self._disable(error)
            return False
        return row is not None

    def record_legacy_id(self, item_id: str) -> None:
        if self._connection is None:
            return
        try:
            self._connection.execute(
                "INSERT OR IGNORE INTO downloads (id) VALUES (?)", (str(item_id),)
            )
        except sqlite3.Error as error:
            logger.error(f"{RED}Download ID was not persisted: {item_id}")
            self._disable(error)

    def record_finalized(
        self,
        *,
        track_id: str,
        path: str | os.PathLike[str],
        requested_quality: int,
    ) -> VerifiedArtifact | None:
        artifact = _inspect_artifact(
            track_id=str(track_id),
            path=path,
            requested_quality=requested_quality,
        )
        if artifact is None:
            logger.warning("Finalized media could not be verified at %s", path)
            return None

        return self.record_verified(artifact)

    def record_verified(self, artifact: VerifiedArtifact) -> VerifiedArtifact | None:
        for key in [key for key in self._run_artifacts if key[1] == artifact.path]:
            self._run_artifacts.pop(key, None)
        key = (artifact.track_id, artifact.path)
        self._run_artifacts[key] = artifact
        if self._connection is None:
            return artifact

        try:
            self._connection.execute(
                "INSERT INTO artifacts ("
                "path, track_id, requested_quality, codec, bit_depth, "
                "sample_rate_hz, bitrate_bps, size_bytes, sha256"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET "
                "track_id=excluded.track_id, "
                "requested_quality=excluded.requested_quality, "
                "codec=excluded.codec, "
                "bit_depth=excluded.bit_depth, "
                "sample_rate_hz=excluded.sample_rate_hz, "
                "bitrate_bps=excluded.bitrate_bps, "
                "size_bytes=excluded.size_bytes, "
                "sha256=excluded.sha256",
                (
                    artifact.path,
                    artifact.track_id,
                    artifact.requested_quality,
                    artifact.media.codec,
                    artifact.media.bit_depth,
                    artifact.media.sample_rate_hz,
                    artifact.media.bitrate_bps,
                    artifact.size_bytes,
                    artifact.sha256,
                ),
            )
        except sqlite3.Error as error:
            logger.error(f"{RED}Artifact was not persisted: {artifact!r}")
            self._disable(error)
            return artifact
        return artifact

    def verified_artifact(
        self, track_id: str, path: str | os.PathLike[str]
    ) -> VerifiedArtifact | None:
        try:
            normalized = _normalized_path(path)
        except (OSError, TypeError, ValueError):
            return None
        normalized_track_id = str(track_id)
        key = (normalized_track_id, normalized)
        run_artifact = self._run_artifacts.get(key)
        if run_artifact is not None:
            inspected = _inspect_artifact(
                track_id=normalized_track_id,
                path=normalized,
                requested_quality=run_artifact.requested_quality,
            )
            if inspected == run_artifact:
                return run_artifact
            self._run_artifacts.pop(key, None)

        if self._connection is None:
            return None
        try:
            row = self._connection.execute(
                "SELECT requested_quality, codec, bit_depth, sample_rate_hz, "
                "bitrate_bps, size_bytes, sha256 FROM artifacts "
                "WHERE track_id=? AND path=?",
                (normalized_track_id, normalized),
            ).fetchone()
        except sqlite3.Error as error:
            self._disable(error)
            return None
        if row is None:
            return None

        stored = VerifiedArtifact(
            track_id=normalized_track_id,
            path=normalized,
            requested_quality=row[0],
            media=MediaProperties(
                codec=row[1],
                bit_depth=row[2],
                sample_rate_hz=row[3],
                bitrate_bps=row[4],
            ),
            size_bytes=row[5],
            sha256=row[6],
        )
        inspected = _inspect_artifact(
            track_id=normalized_track_id,
            path=normalized,
            requested_quality=stored.requested_quality,
        )
        if inspected != stored:
            return None
        self._run_artifacts[key] = stored
        return stored

    @staticmethod
    def inspect_artifact(
        track_id: str,
        path: str | os.PathLike[str],
        requested_quality: int,
    ) -> VerifiedArtifact | None:
        return _inspect_artifact(
            track_id=str(track_id),
            path=path,
            requested_quality=requested_quality,
        )

    @staticmethod
    def reverify_artifact(artifact: VerifiedArtifact) -> bool:
        return (
            _inspect_artifact(
                track_id=artifact.track_id,
                path=artifact.path,
                requested_quality=artifact.requested_quality,
            )
            == artifact
        )


def create_db(db_path):
    """Create or migrate the history database and return ``db_path``."""
    history = DownloadHistory.open(db_path)
    if not history.enabled:
        return None
    history.close()
    return db_path


def handle_download_id(db_path, item_id, add_id=False):
    """Query or record a legacy downloaded item ID."""
    history = DownloadHistory.open(db_path)
    if not history.enabled:
        return None
    try:
        if add_id:
            history.record_legacy_id(item_id)
            return None
        return (item_id,) if history.contains_legacy_id(item_id) else None
    finally:
        history.close()
