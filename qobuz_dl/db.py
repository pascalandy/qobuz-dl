import logging
import sqlite3
from contextlib import closing

from qobuz_dl.color import RED, YELLOW

logger = logging.getLogger(__name__)


def create_db(db_path):
    """Create the downloads table if needed and return ``db_path``."""
    try:
        with closing(sqlite3.connect(db_path)) as conn, conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='downloads'"
            ).fetchone()
            conn.execute(
                "CREATE TABLE IF NOT EXISTS downloads (id TEXT UNIQUE NOT NULL);"
            )
            if not exists:
                logger.info(f"{YELLOW}Download-IDs database created")
    except sqlite3.Error as e:
        logger.error(f"{RED}Unexpected DB error: {e}")
        return None
    return db_path


def handle_download_id(db_path, item_id, add_id=False):
    """Query or record a downloaded item ID.

    With ``add_id=False``, return a truthy row when ``item_id`` is already in
    the database. With ``add_id=True``, record ``item_id``.
    """
    if not db_path:
        return

    try:
        with closing(sqlite3.connect(db_path)) as conn, conn:
            if add_id:
                conn.execute(
                    "INSERT INTO downloads (id) VALUES (?)",
                    (item_id,),
                )
                return None
            return conn.execute(
                "SELECT id FROM downloads where id=?",
                (item_id,),
            ).fetchone()
    except sqlite3.Error as e:
        logger.error(f"{RED}Unexpected DB error: {e}")
        return None
