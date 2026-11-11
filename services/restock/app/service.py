"""Restock domain logic: the shopping list.

Only this module touches the shopping_list table. Anything it needs from Inventory goes
through app/inventory_client.py, which may raise InventoryUnavailable.
"""
import pymssql

from app import inventory_client


class NotFound(Exception):
    """The shopping-list entry (or the Inventory item it should link to) does not exist."""


class Conflict(Exception):
    """The change breaks a rule: item already on the list, or entry already bought."""


_UPDATABLE = ("name", "quantity", "unit")
_COLUMNS = "id, name, quantity, unit, inventory_item_id, source, status, created_at, bought_at"


def _get(conn, entry_id: int) -> dict:
    cursor = conn.cursor(as_dict=True)
    cursor.execute(f"SELECT {_COLUMNS} FROM shopping_list WHERE id = %s", (entry_id,))
    row = cursor.fetchone()
    if row is None:
        raise NotFound(f"shopping-list entry {entry_id} not found")
    return row


def _open_entry_for(conn, item_id: int) -> dict | None:
    cursor = conn.cursor(as_dict=True)
    cursor.execute(
        f"SELECT {_COLUMNS} FROM shopping_list WHERE inventory_item_id = %s AND status = N'open'", (item_id,)
    )
    return cursor.fetchone()


def list_entries(conn, status: str | None = None) -> list[dict]:
    """Open entries first, then bought ones, newest first within each group. Needs no Inventory."""
    sql, params = f"SELECT {_COLUMNS} FROM shopping_list", ()
    if status is not None:
        sql += " WHERE status = %s"
        params = (status,)
    sql += " ORDER BY CASE WHEN status = N'bought' THEN 1 ELSE 0 END, id DESC"
    cursor = conn.cursor(as_dict=True)
    cursor.execute(sql, params)
    return cursor.fetchall()


def get_entry(conn, entry_id: int) -> dict:
    return _get(conn, entry_id)


def add_entry(conn, quantity: float, name: str | None = None, unit: str | None = None,
              inventory_item_id: int | None = None, source: str = "manual") -> dict:
    """Add something to buy: either free text (name) or a link to an Inventory item."""
    if quantity <= 0:
        raise Conflict("quantity must be positive")
    if inventory_item_id is not None:
        item = inventory_client.get_item(inventory_item_id)
        if item is None:
            raise NotFound(f"inventory item {inventory_item_id} not found")
        if _open_entry_for(conn, inventory_item_id):
            raise Conflict(f"{item['name']} is already on the shopping list")
        # Copy what we display, so listing never needs Inventory (ADR-3).
        name = name or item["name"]
        unit = unit or item["unit"]
    if not name or not name.strip():
        raise Conflict("an entry needs a name or an inventory_item_id")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO shopping_list (name, quantity, unit, inventory_item_id, source)"
            " OUTPUT INSERTED.id VALUES (%s, %s, %s, %s, %s)",
            (name.strip(), quantity, unit or "pcs", inventory_item_id, source),
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
    except pymssql.IntegrityError:  # two requests raced past the check above
        conn.rollback()
        raise Conflict(f"{name} is already on the shopping list")
    return _get(conn, new_id)


def add_low_stock_items(conn) -> list[dict]:
    """Put every low-stock Inventory item on the list, skipping ones already there.

    Suggested amount: enough to bring stock back to twice the item's threshold.
    """
    added = []
    for item in inventory_client.low_stock_items():
        if _open_entry_for(conn, item["id"]):
            continue
        amount = 2 * item["min_threshold"] - item["quantity"]
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO shopping_list (name, quantity, unit, inventory_item_id, source)"
            " OUTPUT INSERTED.id VALUES (%s, %s, %s, %s, N'low_stock')",
            (item["name"], amount, item["unit"], item["id"]),
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        added.append(_get(conn, new_id))
    return added


def update_entry(conn, entry_id: int, changes: dict) -> dict:
    entry = _get(conn, entry_id)
    if entry["status"] == "bought":
        raise Conflict("a bought entry cannot be changed")
    fields = {k: v for k, v in changes.items() if k in _UPDATABLE and v is not None}
    if "quantity" in fields and fields["quantity"] <= 0:
        raise Conflict("quantity must be positive")
    if fields:
        assignments = ", ".join(f"{column} = %s" for column in fields)  # names come from _UPDATABLE only
        conn.cursor().execute(f"UPDATE shopping_list SET {assignments} WHERE id = %s", (*fields.values(), entry_id))
        conn.commit()
    return _get(conn, entry_id)


def delete_entry(conn, entry_id: int) -> None:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM shopping_list WHERE id = %s", (entry_id,))
    if cursor.rowcount == 0:
        raise NotFound(f"shopping-list entry {entry_id} not found")
    conn.commit()


def mark_bought(conn, entry_id: int) -> dict:
    """Mark an entry bought and, if it is linked to Inventory, add the quantity to stock.

    Inventory is asked first: if it is unreachable, InventoryUnavailable propagates and
    nothing is changed here, so the user can simply try again. `restocked` in the result
    is False if the entry was free text or its Inventory item was deleted meanwhile.
    """
    entry = _get(conn, entry_id)
    if entry["status"] == "bought":
        raise Conflict("entry is already bought")
    restocked = False
    if entry["inventory_item_id"] is not None:
        restocked = inventory_client.add_stock(entry["inventory_item_id"], entry["quantity"])
    conn.cursor().execute(
        "UPDATE shopping_list SET status = N'bought', bought_at = SYSUTCDATETIME() WHERE id = %s", (entry_id,)
    )
    conn.commit()
    return {**_get(conn, entry_id), "restocked": restocked}
