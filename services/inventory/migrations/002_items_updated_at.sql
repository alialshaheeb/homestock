-- 002: record when each item last changed (its details or its stock).
-- items already holds data, so the table is changed in place, never recreated:
-- the column is added as NULL, every existing row is backfilled from created_at,
-- and only then is it made NOT NULL, with a default for new rows.
ALTER TABLE items ADD updated_at DATETIME2 NULL;
GO
UPDATE items SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE items ALTER COLUMN updated_at DATETIME2 NOT NULL;
ALTER TABLE items ADD CONSTRAINT df_items_updated_at DEFAULT SYSUTCDATETIME() FOR updated_at;
