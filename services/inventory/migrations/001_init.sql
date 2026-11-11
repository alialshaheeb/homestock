-- Inventory owns locations and items. items.location_id is a real foreign key: both
-- tables live in this service's database.
CREATE TABLE locations (
    id   INT IDENTITY PRIMARY KEY,
    name NVARCHAR(50) NOT NULL CONSTRAINT uq_locations_name UNIQUE
);

CREATE TABLE items (
    id            INT IDENTITY PRIMARY KEY,
    name          NVARCHAR(100) NOT NULL,
    location_id   INT           NOT NULL CONSTRAINT fk_items_location REFERENCES locations (id),
    quantity      FLOAT         NOT NULL CONSTRAINT df_items_quantity DEFAULT 0 CONSTRAINT ck_items_quantity CHECK (quantity >= 0),
    unit          NVARCHAR(20)  NOT NULL CONSTRAINT df_items_unit DEFAULT N'pcs',
    min_threshold FLOAT         NOT NULL CONSTRAINT df_items_min DEFAULT 0 CONSTRAINT ck_items_min CHECK (min_threshold >= 0),
    expiry_date   DATE          NULL,
    created_at    DATETIME2     NOT NULL CONSTRAINT df_items_created DEFAULT SYSUTCDATETIME()
);
