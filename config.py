"""All configuration comes from environment variables (contract §7.3, §7.5, §7.9)."""
import os

HOST = "0.0.0.0"  # must bind to all interfaces so a container can be reached


def get_port() -> int:
    return int(os.environ.get("PORT", "8000"))


def db_path() -> str:
    """The one documented SQLite path: <DATA_DIR>/homestock.db (DATA_DIR defaults to ./data)."""
    return os.path.join(os.environ.get("DATA_DIR", "data"), "homestock.db")
