-- Restock owns the shopping list. inventory_item_id is a plain number pointing at an item
-- in the inventory service's database: no foreign key is possible across databases (ADR-3).
-- name and unit are copied from Inventory when a row is added, so the list shows without it.
CREATE TABLE shopping_list (
    id                INT IDENTITY PRIMARY KEY,
    name              NVARCHAR(100) NOT NULL,
    quantity          FLOAT         NOT NULL CONSTRAINT ck_list_quantity CHECK (quantity > 0),
    unit              NVARCHAR(20)  NOT NULL CONSTRAINT df_list_unit DEFAULT N'pcs',
    inventory_item_id INT           NULL,
    source            NVARCHAR(20)  NOT NULL CONSTRAINT df_list_source DEFAULT N'manual'
                                    CONSTRAINT ck_list_source CHECK (source IN (N'manual', N'low_stock')),
    status            NVARCHAR(10)  NOT NULL CONSTRAINT df_list_status DEFAULT N'open'
                                    CONSTRAINT ck_list_status CHECK (status IN (N'open', N'bought')),
    created_at        DATETIME2     NOT NULL CONSTRAINT df_list_created DEFAULT SYSUTCDATETIME(),
    bought_at         DATETIME2     NULL
);

-- At most one open entry per Inventory item, so "add low-stock items" can run twice safely.
CREATE UNIQUE INDEX ux_list_one_open_per_item
    ON shopping_list (inventory_item_id)
    WHERE status = N'open' AND inventory_item_id IS NOT NULL;
