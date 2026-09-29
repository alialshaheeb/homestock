"""All configuration comes from environment variables (contract §7.3, §7.5, §7.9)."""
import os

HOST = "0.0.0.0"  # must bind to all interfaces so a container can be reached
PORT = int(os.environ.get("PORT", "8000"))
DATA_DIR = os.environ.get("DATA_DIR", "data")


def db_path() -> str:
    """The one documented SQLite path: <DATA_DIR>/homestock.db"""
    return os.path.join(DATA_DIR, "homestock.db")
