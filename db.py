"""SQLite access shared by both domains. Each domain owns its own tables/schema."""
import os
import sqlite3

import config


def get_connection() -> sqlite3.Connection:
    """Open a connection to the one SQLite file, creating the data dir if needed."""
    path = config.db_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(schemas: list[str]) -> None:
    """Run each domain's CREATE TABLE IF NOT EXISTS script. No manual migration (§7.4)."""
    conn = get_connection()
    try:
        for script in schemas:
            conn.executescript(script)
        conn.commit()
    finally:
        conn.close()
