"""The ONLY place the Restock domain talks to Inventory (the seam from ADR-2).

Today these are plain function calls into inventory/service.py on the same
SQLite connection. When the app is split into services (Assignment 2), only this
file changes: each function becomes an HTTP request to the Inventory service.
"""
import sqlite3

from inventory import service as inventory


def low_stock_items(conn: sqlite3.Connection) -> list[dict]:
    return inventory.list_items(conn, low_stock=True)


def get_item(conn: sqlite3.Connection, item_id: int) -> dict | None:
    """The Inventory item, or None if it does not exist (any more)."""
    try:
        return inventory.get_item(conn, item_id)
    except inventory.NotFound:
        return None


def add_stock(conn: sqlite3.Connection, item_id: int, amount: float) -> bool:
    """Increase an item's stock. False if the item no longer exists in Inventory."""
    try:
        inventory.restock(conn, item_id, amount)
        return True
    except inventory.NotFound:
        return False
