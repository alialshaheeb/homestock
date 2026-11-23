from urllib.parse import urlparse, urlunparse

from app import db, service
from app.migrations import MIGRATIONS_DIR, _batches, migrate, pending


def test_batches_split_on_go_lines_only():
    sql = "CREATE TABLE a (x INT)\nGO\n  go  \nSELECT 'GO here is text'\nGO\n"
    assert _batches(sql) == ["CREATE TABLE a (x INT)", "SELECT 'GO here is text'"]


def test_second_run_applies_nothing(conn):
    assert pending(conn) == []  # the session fixture already migrated the test database
    assert migrate(conn) == []
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM schema_migrations WHERE version = '001_init'")
    assert cursor.fetchone() is not None


def test_failed_migration_is_rolled_back_and_not_recorded(conn, tmp_path):
    (tmp_path / "900_broken.sql").write_text("CREATE TABLE tmp_should_vanish (x INT)\nGO\nSELECT * FROM no_such_table")
    try:
        migrate(conn, tmp_path)
    except Exception:
        pass
    cursor = conn.cursor()
    cursor.execute("SELECT OBJECT_ID('tmp_should_vanish', 'U')")
    assert cursor.fetchone()[0] is None
    cursor.execute("SELECT COUNT(*) FROM schema_migrations WHERE version = '900_broken'")
    assert cursor.fetchone()[0] == 0


def _fresh_database(url: str, suffix: str) -> str:
    """Drop and recreate a scratch database next to the test database; return its URL."""
    parts = urlparse(url)
    name = parts.path.lstrip("/") + suffix
    master = db.connect(urlunparse(parts._replace(path="/master")))
    master.autocommit(True)  # CREATE/DROP DATABASE cannot run inside a transaction
    cursor = master.cursor()
    cursor.execute(
        f"IF DB_ID('{name}') IS NOT NULL BEGIN "
        f"ALTER DATABASE {name} SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE {name}; END"
    )
    cursor.execute(f"CREATE DATABASE {name}")
    master.close()
    return urlunparse(parts._replace(path=f"/{name}"))


def test_002_keeps_existing_items_and_backfills_updated_at(database_url, tmp_path):
    """002 changes a table that already holds data: the rows stay, and updated_at is filled in."""
    conn = db.connect(_fresh_database(database_url, "_migration"))
    try:
        # A database as it was before 002: only 001 applied, with an item in it.
        (tmp_path / "001_init.sql").write_text((MIGRATIONS_DIR / "001_init.sql").read_text(encoding="utf-8"))
        migrate(conn, tmp_path)
        service.seed(conn)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO items (name, location_id, quantity, unit) SELECT N'milk', id, 2, N'l' FROM locations WHERE name = N'fridge'"
        )
        conn.commit()

        assert "002_items_updated_at" in migrate(conn)  # 001 is recorded, so only the new files run

        cursor.execute("SELECT name, quantity, unit, created_at, updated_at FROM items")
        rows = cursor.fetchall()
        assert len(rows) == 1
        name, quantity, unit, created_at, updated_at = rows[0]
        assert (name, quantity, unit) == ("milk", 2, "l")
        assert updated_at == created_at  # backfilled, not NULL and not "now"
    finally:
        conn.close()


def test_changing_stock_moves_updated_at(conn):
    location_id = service.list_locations(conn)[0]["id"]
    item = service.create_item(conn, {"name": "rice", "location_id": location_id, "quantity": 2})
    after = service.consume(conn, item["id"], 1)
    assert after["updated_at"] >= item["updated_at"]
