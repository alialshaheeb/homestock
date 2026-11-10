"""Inventory domain logic: locations, items and their stock levels.

This module is the only code allowed to read or write the inventory tables
(`locations`, `items`). Other domains (restock) call these functions and never
query the tables directly, so inventory can later move behind its own HTTP API
without the rest of the app noticing (see ADR-2).
"""
import sqlite3
from datetime import date, timedelta


class NotFound(Exception):
    """The requested location or item does not exist."""


class Conflict(Exception):
    """The change breaks a rule: duplicate name, or consuming more than is in stock."""


# Columns returned for every item. The join to locations stays inside this domain.
_ITEM_SELECT = """
    SELECT i.id, i.name, i.location_id, l.name AS location, i.quantity, i.unit,
           i.min_threshold, i.expiry_date, i.created_at
    FROM items i JOIN locations l ON l.id = i.location_id
"""

# Fields a client may change with update_item(); anything else is ignored.
_UPDATABLE = ("name", "location_id", "quantity", "unit", "min_threshold", "expiry_date")


def _to_dict(row: sqlite3.Row) -> dict:
    item = dict(row)
    # An item is low on stock when a threshold is set and we are at or below it.
    item["low_stock"] = item["min_threshold"] > 0 and item["quantity"] <= item["min_threshold"]
    return item


def _require_location(conn: sqlite3.Connection, location_id: int) -> None:
    if conn.execute("SELECT 1 FROM locations WHERE id = ?", (location_id,)).fetchone() is None:
        raise NotFound(f"location {location_id} not found")


# ---------- locations ----------

def list_locations(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT id, name FROM locations ORDER BY name")]


def create_location(conn: sqlite3.Connection, name: str) -> dict:
    name = name.strip().lower()
    try:
        cur = conn.execute("INSERT INTO locations (name) VALUES (?)", (name,))
    except sqlite3.IntegrityError:
        raise Conflict(f"location '{name}' already exists")
    conn.commit()
    return {"id": cur.lastrowid, "name": name}


# ---------- items ----------

def list_items(
    conn: sqlite3.Connection,
    location_id: int | None = None,
    low_stock: bool = False,
    expiring_within_days: int | None = None,
    today: date | None = None,
) -> list[dict]:
    """List items, optionally filtered by location, low stock, or expiry window."""
    sql, params = _ITEM_SELECT + " WHERE 1 = 1", []
    if location_id is not None:
        sql += " AND i.location_id = ?"
        params.append(location_id)
    if low_stock:
        sql += " AND i.min_threshold > 0 AND i.quantity <= i.min_threshold"
    if expiring_within_days is not None:
        limit = (today or date.today()) + timedelta(days=expiring_within_days)
        # ISO dates (YYYY-MM-DD) compare correctly as strings.
        sql += " AND i.expiry_date IS NOT NULL AND i.expiry_date <= ?"
        params.append(limit.isoformat())
    sql += " ORDER BY i.name"
    return [_to_dict(r) for r in conn.execute(sql, params)]


def get_item(conn: sqlite3.Connection, item_id: int) -> dict:
    row = conn.execute(_ITEM_SELECT + " WHERE i.id = ?", (item_id,)).fetchone()
    if row is None:
        raise NotFound(f"item {item_id} not found")
    return _to_dict(row)


def create_item(conn: sqlite3.Connection, data: dict) -> dict:
    _require_location(conn, data["location_id"])
    expiry = data.get("expiry_date")
    cur = conn.execute(
        "INSERT INTO items (name, location_id, quantity, unit, min_threshold, expiry_date)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            data["name"].strip(),
            data["location_id"],
            data.get("quantity", 0),
            data.get("unit", "pcs"),
            data.get("min_threshold", 0),
            expiry.isoformat() if isinstance(expiry, date) else expiry,
        ),
    )
    conn.commit()
    return get_item(conn, cur.lastrowid)


def update_item(conn: sqlite3.Connection, item_id: int, changes: dict) -> dict:
    get_item(conn, item_id)  # raises NotFound first
    fields = {k: v for k, v in changes.items() if k in _UPDATABLE}
    if "location_id" in fields:
        _require_location(conn, fields["location_id"])
    if isinstance(fields.get("expiry_date"), date):
        fields["expiry_date"] = fields["expiry_date"].isoformat()
    if fields:
        assignments = ", ".join(f"{column} = ?" for column in fields)  # column names come from _UPDATABLE only
        conn.execute(f"UPDATE items SET {assignments} WHERE id = ?", (*fields.values(), item_id))
        conn.commit()
    return get_item(conn, item_id)


def delete_item(conn: sqlite3.Connection, item_id: int) -> None:
    if conn.execute("DELETE FROM items WHERE id = ?", (item_id,)).rowcount == 0:
        raise NotFound(f"item {item_id} not found")
    conn.commit()


# ---------- stock changes (also the entry points the restock domain uses) ----------

def consume(conn: sqlite3.Connection, item_id: int, amount: float) -> dict:
    """Take `amount` out of stock, e.g. when something is eaten or used up."""
    if amount <= 0:
        raise Conflict("amount must be positive")
    item = get_item(conn, item_id)
    if amount > item["quantity"]:
        raise Conflict(f"only {item['quantity']} {item['unit']} of {item['name']} in stock")
    conn.execute("UPDATE items SET quantity = quantity - ? WHERE id = ?", (amount, item_id))
    conn.commit()
    return get_item(conn, item_id)


def restock(conn: sqlite3.Connection, item_id: int, amount: float) -> dict:
    """Add `amount` to stock, e.g. after shopping."""
    if amount <= 0:
        raise Conflict("amount must be positive")
    get_item(conn, item_id)
    conn.execute("UPDATE items SET quantity = quantity + ? WHERE id = ?", (amount, item_id))
    conn.commit()
    return get_item(conn, item_id)
