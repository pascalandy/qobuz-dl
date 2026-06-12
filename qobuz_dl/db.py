import logging
import sqlite3
from contextlib import closing

from qobuz_dl.color import RED, YELLOW

logger = logging.getLogger(__name__)


def create_db(db_path):
    """Create the downloads table if needed and return ``db_path``."""
    with closing(sqlite3.connect(db_path)) as conn, conn:
        try:
            conn.execute("CREATE TABLE downloads (id TEXT UNIQUE NOT NULL);")
            logger.info(f"{YELLOW}Download-IDs database created")
        except sqlite3.OperationalError:
            pass
    return db_path


def handle_download_id(db_path, item_id, add_id=False):
    """Query or record a downloaded item ID.

    With ``add_id=False``, return a truthy row when ``item_id`` is already in
    the database. With ``add_id=True``, record ``item_id``.
    """
    if not db_path:
        return

    with closing(sqlite3.connect(db_path)) as conn, conn:
        if add_id:
            try:
                conn.execute(
                    "INSERT INTO downloads (id) VALUES (?)",
                    (item_id,),
                )
            except sqlite3.Error as e:
                logger.error(f"{RED}Unexpected DB error: {e}")
        else:
            return conn.execute(
                "SELECT id FROM downloads where id=?",
                (item_id,),
            ).fetchone()
