"""Inventory domain: owns the `locations` and `items` tables."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS locations (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    location_id   INTEGER NOT NULL REFERENCES locations(id),
    quantity      REAL NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    unit          TEXT NOT NULL DEFAULT 'pcs',
    min_threshold REAL NOT NULL DEFAULT 0 CHECK (min_threshold >= 0),
    expiry_date   TEXT,  -- ISO date YYYY-MM-DD, NULL when the item does not expire
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Default locations so the app needs no manual setup (contract §7.4).
INSERT OR IGNORE INTO locations (name) VALUES ('fridge'), ('pantry'), ('toiletries');
"""
