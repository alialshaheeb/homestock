"""Inventory domain logic: locations, items and their stock levels.

This module is the only code that reads or writes the inventory tables. The restock
service never touches them: it calls this service's HTTP API (see ADR-2, ADR-6).
"""
from datetime import date, timedelta

import pymssql


class NotFound(Exception):
    """The requested location or item does not exist."""


class Conflict(Exception):
    """The change breaks a rule: duplicate name, or consuming more than is in stock."""


# Idempotent seed, run on every start-up: adds each default place only if it is missing.
SEED = """
INSERT INTO locations (name)
SELECT v.name FROM (VALUES (N'fridge'), (N'pantry'), (N'toiletries')) AS v(name)
WHERE NOT EXISTS (SELECT 1 FROM locations l WHERE l.name = v.name)
"""

_ITEM_SELECT = """
    SELECT i.id, i.name, i.location_id, l.name AS location, i.quantity, i.unit,
           i.min_threshold, i.expiry_date, i.created_at, i.updated_at
    FROM items i JOIN locations l ON l.id = i.location_id
"""

# Fields a client may change with update_item(); anything else is ignored.
_UPDATABLE = ("name", "location_id", "quantity", "unit", "min_threshold", "expiry_date")


def seed(conn) -> None:
    conn.cursor().execute(SEED)
    conn.commit()


def _to_dict(row: dict) -> dict:
    item = dict(row)
    # An item is low on stock when a threshold is set and we are at or below it.
    item["low_stock"] = item["min_threshold"] > 0 and item["quantity"] <= item["min_threshold"]
    return item


def _require_location(conn, location_id: int) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM locations WHERE id = %s", (location_id,))
    if cursor.fetchone() is None:
        raise NotFound(f"location {location_id} not found")


# ---------- locations ----------

def list_locations(conn) -> list[dict]:
    cursor = conn.cursor(as_dict=True)
    cursor.execute("SELECT id, name FROM locations ORDER BY name")
    return cursor.fetchall()


def create_location(conn, name: str) -> dict:
    name = name.strip().lower()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO locations (name) OUTPUT INSERTED.id VALUES (%s)", (name,))
        new_id = cursor.fetchone()[0]
        conn.commit()
    except pymssql.IntegrityError:
        conn.rollback()
        raise Conflict(f"location '{name}' already exists")
    return {"id": new_id, "name": name}


# ---------- items ----------

def list_items(conn, location_id: int | None = None, low_stock: bool = False,
               expiring_within_days: int | None = None, today: date | None = None) -> list[dict]:
    """List items, optionally filtered by location, low stock, or expiry window."""
    sql, params = _ITEM_SELECT + " WHERE 1 = 1", []
    if location_id is not None:
        sql += " AND i.location_id = %s"
        params.append(location_id)
    if low_stock:
        sql += " AND i.min_threshold > 0 AND i.quantity <= i.min_threshold"
    if expiring_within_days is not None:
        limit = (today or date.today()) + timedelta(days=expiring_within_days)
        sql += " AND i.expiry_date IS NOT NULL AND i.expiry_date <= %s"
        params.append(limit)
    sql += " ORDER BY i.name"
    cursor = conn.cursor(as_dict=True)
    cursor.execute(sql, tuple(params))
    return [_to_dict(r) for r in cursor.fetchall()]


def get_item(conn, item_id: int) -> dict:
    cursor = conn.cursor(as_dict=True)
    cursor.execute(_ITEM_SELECT + " WHERE i.id = %s", (item_id,))
    row = cursor.fetchone()
    if row is None:
        raise NotFound(f"item {item_id} not found")
    return _to_dict(row)


def create_item(conn, data: dict) -> dict:
    _require_location(conn, data["location_id"])
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO items (name, location_id, quantity, unit, min_threshold, expiry_date)"
        " OUTPUT INSERTED.id VALUES (%s, %s, %s, %s, %s, %s)",
        (
            data["name"].strip(),
            data["location_id"],
            data.get("quantity", 0),
            data.get("unit", "pcs"),
            data.get("min_threshold", 0),
            data.get("expiry_date"),
        ),
    )
    new_id = cursor.fetchone()[0]
    conn.commit()
    return get_item(conn, new_id)


def update_item(conn, item_id: int, changes: dict) -> dict:
    get_item(conn, item_id)  # raises NotFound first
    fields = {k: v for k, v in changes.items() if k in _UPDATABLE}
    if "location_id" in fields:
        _require_location(conn, fields["location_id"])
    if fields:
        assignments = ", ".join(f"{column} = %s" for column in fields)  # names come from _UPDATABLE only
        conn.cursor().execute(
            f"UPDATE items SET {assignments}, updated_at = SYSUTCDATETIME() WHERE id = %s", (*fields.values(), item_id)
        )
        conn.commit()
    return get_item(conn, item_id)


def delete_item(conn, item_id: int) -> None:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM items WHERE id = %s", (item_id,))
    if cursor.rowcount == 0:
        raise NotFound(f"item {item_id} not found")
    conn.commit()


# ---------- stock changes (consume is used by the UI, restock also by the restock service) ----------

def consume(conn, item_id: int, amount: float) -> dict:
    """Take `amount` out of stock, e.g. when something is eaten or used up."""
    if amount <= 0:
        raise Conflict("amount must be positive")
    item = get_item(conn, item_id)
    if amount > item["quantity"]:
        raise Conflict(f"only {item['quantity']:g} {item['unit']} of {item['name']} in stock")
    conn.cursor().execute(
        "UPDATE items SET quantity = quantity - %s, updated_at = SYSUTCDATETIME() WHERE id = %s", (amount, item_id)
    )
    conn.commit()
    return get_item(conn, item_id)


def restock(conn, item_id: int, amount: float) -> dict:
    """Add `amount` to stock, e.g. after shopping."""
    if amount <= 0:
        raise Conflict("amount must be positive")
    get_item(conn, item_id)
    conn.cursor().execute(
        "UPDATE items SET quantity = quantity + %s, updated_at = SYSUTCDATETIME() WHERE id = %s", (amount, item_id)
    )
    conn.commit()
    return get_item(conn, item_id)
