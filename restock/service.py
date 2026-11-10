"""Restock domain logic: the shopping list.

Only this module touches the `shopping_list` table. Anything it needs from
Inventory goes through restock/inventory_client.py.
"""
import sqlite3

from restock import inventory_client


class NotFound(Exception):
    """The shopping-list entry (or the Inventory item it should link to) does not exist."""


class Conflict(Exception):
    """The change breaks a rule: item already on the list, or entry already bought."""


_UPDATABLE = ("name", "quantity", "unit")


def _get(conn: sqlite3.Connection, entry_id: int) -> dict:
    row = conn.execute("SELECT * FROM shopping_list WHERE id = ?", (entry_id,)).fetchone()
    if row is None:
        raise NotFound(f"shopping-list entry {entry_id} not found")
    return dict(row)


def _open_entry_for(conn: sqlite3.Connection, item_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM shopping_list WHERE inventory_item_id = ? AND status = 'open'", (item_id,)
    ).fetchone()
    return dict(row) if row else None


def list_entries(conn: sqlite3.Connection, status: str | None = None) -> list[dict]:
    """Open entries first, then bought ones, newest first within each group."""
    sql, params = "SELECT * FROM shopping_list", []
    if status is not None:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY status = 'bought', id DESC"
    return [dict(r) for r in conn.execute(sql, params)]


def get_entry(conn: sqlite3.Connection, entry_id: int) -> dict:
    return _get(conn, entry_id)


def add_entry(
    conn: sqlite3.Connection,
    quantity: float,
    name: str | None = None,
    unit: str | None = None,
    inventory_item_id: int | None = None,
    source: str = "manual",
) -> dict:
    """Add something to buy: either free text (name) or a link to an Inventory item."""
    if quantity <= 0:
        raise Conflict("quantity must be positive")
    if inventory_item_id is not None:
        item = inventory_client.get_item(conn, inventory_item_id)
        if item is None:
            raise NotFound(f"inventory item {inventory_item_id} not found")
        if _open_entry_for(conn, inventory_item_id):
            raise Conflict(f"{item['name']} is already on the shopping list")
        # Copy what we display, so listing never needs Inventory (ADR-3).
        name = name or item["name"]
        unit = unit or item["unit"]
    if not name or not name.strip():
        raise Conflict("an entry needs a name or an inventory_item_id")
    cur = conn.execute(
        "INSERT INTO shopping_list (name, quantity, unit, inventory_item_id, source) VALUES (?, ?, ?, ?, ?)",
        (name.strip(), quantity, unit or "pcs", inventory_item_id, source),
    )
    conn.commit()
    return _get(conn, cur.lastrowid)


def add_low_stock_items(conn: sqlite3.Connection) -> list[dict]:
    """Put every low-stock Inventory item on the list, skipping ones already there.

    Suggested amount: enough to bring stock back to twice the item's threshold.
    """
    added = []
    for item in inventory_client.low_stock_items(conn):
        if _open_entry_for(conn, item["id"]):
            continue
        amount = 2 * item["min_threshold"] - item["quantity"]
        added.append(add_entry(conn, amount, inventory_item_id=item["id"], source="low_stock"))
    return added


def update_entry(conn: sqlite3.Connection, entry_id: int, changes: dict) -> dict:
    entry = _get(conn, entry_id)
    if entry["status"] == "bought":
        raise Conflict("a bought entry cannot be changed")
    fields = {k: v for k, v in changes.items() if k in _UPDATABLE and v is not None}
    if "quantity" in fields and fields["quantity"] <= 0:
        raise Conflict("quantity must be positive")
    if fields:
        assignments = ", ".join(f"{column} = ?" for column in fields)  # names come from _UPDATABLE only
        conn.execute(f"UPDATE shopping_list SET {assignments} WHERE id = ?", (*fields.values(), entry_id))
        conn.commit()
    return _get(conn, entry_id)


def delete_entry(conn: sqlite3.Connection, entry_id: int) -> None:
    if conn.execute("DELETE FROM shopping_list WHERE id = ?", (entry_id,)).rowcount == 0:
        raise NotFound(f"shopping-list entry {entry_id} not found")
    conn.commit()


def mark_bought(conn: sqlite3.Connection, entry_id: int) -> dict:
    """Mark an entry bought and, if it is linked to Inventory, add the quantity to stock.

    The result has `restocked`: True if Inventory was updated, False if the entry
    was free text or its Inventory item has been deleted in the meantime.
    """
    entry = _get(conn, entry_id)
    if entry["status"] == "bought":
        raise Conflict("entry is already bought")
    restocked = False
    if entry["inventory_item_id"] is not None:
        restocked = inventory_client.add_stock(conn, entry["inventory_item_id"], entry["quantity"])
    conn.execute(
        "UPDATE shopping_list SET status = 'bought', bought_at = datetime('now') WHERE id = ?", (entry_id,)
    )
    conn.commit()
    return {**_get(conn, entry_id), "restocked": restocked}
