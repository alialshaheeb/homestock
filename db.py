"""SQLite access shared by both domains. Each domain owns its own tables/schema."""
import os
import sqlite3

import config


def get_connection() -> sqlite3.Connection:
    """Open a connection to the one SQLite file, creating the data dir if needed."""
    path = config.db_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # FastAPI may run a request's dependency and its endpoint on different worker
    # threads; each connection is still used by one request at a time.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """FastAPI dependency: one connection per request, always closed afterwards."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db(schemas: list[str]) -> None:
    """Run each domain's CREATE TABLE IF NOT EXISTS script. No manual migration (§7.4)."""
    conn = get_connection()
    try:
        for script in schemas:
            conn.executescript(script)
        conn.commit()
    finally:
        conn.close()
