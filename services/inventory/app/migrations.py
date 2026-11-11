"""Versioned migrations: numbered .sql files applied once each, in order, at start-up.

Applied files are recorded in schema_migrations, so a second start applies nothing.
An applied file is never edited; a correction goes in a new, higher-numbered file.
"""
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

_TRACKING_TABLE = """
IF OBJECT_ID('schema_migrations', 'U') IS NULL
    CREATE TABLE schema_migrations (
        version    NVARCHAR(100) NOT NULL PRIMARY KEY,
        applied_at DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
    )
"""


def _batches(sql: str) -> list[str]:
    """Split a file into batches on lines that contain only GO (like sqlcmd does)."""
    batches, current = [], []
    for line in sql.splitlines():
        if line.strip().upper() == "GO":
            batches.append("\n".join(current))
            current = []
        else:
            current.append(line)
    batches.append("\n".join(current))
    return [b for b in batches if b.strip()]


def pending(conn, directory: Path = MIGRATIONS_DIR) -> list[Path]:
    cursor = conn.cursor()
    cursor.execute(_TRACKING_TABLE)
    conn.commit()
    cursor.execute("SELECT version FROM schema_migrations")
    applied = {row[0] for row in cursor.fetchall()}
    return [f for f in sorted(directory.glob("*.sql")) if f.stem not in applied]


def migrate(conn, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every pending migration; each one and its record commit together or not at all."""
    done = []
    for path in pending(conn, directory):
        cursor = conn.cursor()
        try:
            for batch in _batches(path.read_text(encoding="utf-8")):
                cursor.execute(batch)
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        print(f"applied migration {path.stem}", flush=True)
        done.append(path.stem)
    return done
