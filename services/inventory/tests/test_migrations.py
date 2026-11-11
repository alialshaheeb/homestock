from app.migrations import _batches, migrate, pending


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
