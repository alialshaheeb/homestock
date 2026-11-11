"""SQL Server connection for this service. The only setting is DATABASE_URL."""
import os
import time
from urllib.parse import unquote, urlparse

import pymssql

# FreeTDS (the driver under pymssql) starts sessions with some ANSI options off. SQL Server
# refuses writes to a table with a filtered index unless they are on, so set them every time.
SESSION_SETTINGS = (
    "SET ANSI_NULLS ON; SET ANSI_PADDING ON; SET ANSI_WARNINGS ON; SET ARITHABORT ON; "
    "SET CONCAT_NULL_YIELDS_NULL ON; SET QUOTED_IDENTIFIER ON; SET NUMERIC_ROUNDABORT OFF;"
)


def connect(url: str | None = None) -> pymssql.Connection:
    """Open a connection from mssql://user:password@host:port/database."""
    parts = urlparse(url or os.environ["DATABASE_URL"])
    conn = pymssql.connect(
        server=parts.hostname,
        port=parts.port or 1433,
        user=unquote(parts.username or ""),
        password=unquote(parts.password or ""),
        database=parts.path.lstrip("/"),
        login_timeout=5,
        timeout=10,
    )
    conn.cursor().execute(SESSION_SETTINGS)
    return conn


def connect_with_retry(attempts: int = 30, delay: float = 2.0) -> pymssql.Connection:
    """Wait for the database: SQL Server takes ~20 s to start, and a paused Azure SQL
    serverless database can take up to a minute to resume (error 40613 meanwhile)."""
    for attempt in range(1, attempts + 1):
        try:
            return connect()
        except pymssql.Error as error:
            if attempt == attempts:
                raise
            print(f"database not ready ({attempt}/{attempts}): {error}", flush=True)
            time.sleep(delay)
    raise RuntimeError("unreachable")


def get_db():
    """FastAPI dependency: one connection per request, always closed afterwards."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
