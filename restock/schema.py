"""Restock domain: owns the `shopping_list` table.

`inventory_item_id` is a plain number pointing at an Inventory item, deliberately
not a FOREIGN KEY: the two domains must be able to live in separate databases
(ADR-2, ADR-3). `name` and `unit` are copied from Inventory when the row is added,
so the list can be shown without asking Inventory again.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS shopping_list (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    quantity          REAL NOT NULL CHECK (quantity > 0),
    unit              TEXT NOT NULL DEFAULT 'pcs',
    inventory_item_id INTEGER,  -- NULL when the thing is not tracked in Inventory yet
    source            TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'low_stock')),
    status            TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'bought')),
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    bought_at         TEXT
);

-- At most one open entry per Inventory item, so "add low-stock items" can run twice safely.
CREATE UNIQUE INDEX IF NOT EXISTS shopping_list_one_open_per_item
    ON shopping_list (inventory_item_id)
    WHERE status = 'open' AND inventory_item_id IS NOT NULL;
"""
