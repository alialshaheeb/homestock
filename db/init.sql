-- Local set-up only (docker compose runs it on every `up`): idempotent, safe to repeat.
-- sqlcmd variables INVENTORY_DB_PASSWORD and RESTOCK_DB_PASSWORD are passed with -v.
-- On Azure the same logins are created once by hand (see the README).
IF DB_ID('inventory') IS NULL CREATE DATABASE inventory;
IF DB_ID('restock') IS NULL CREATE DATABASE restock;
GO

IF SUSER_ID('inventory_user') IS NULL CREATE LOGIN inventory_user WITH PASSWORD = '$(INVENTORY_DB_PASSWORD)', CHECK_POLICY = OFF;
IF SUSER_ID('restock_user') IS NULL CREATE LOGIN restock_user WITH PASSWORD = '$(RESTOCK_DB_PASSWORD)', CHECK_POLICY = OFF;
GO

-- Each login is a user in its own database only, so neither service can read the other's data.
USE inventory;
GO
IF USER_ID('inventory_user') IS NULL CREATE USER inventory_user FOR LOGIN inventory_user;
ALTER ROLE db_ddladmin ADD MEMBER inventory_user;
ALTER ROLE db_datareader ADD MEMBER inventory_user;
ALTER ROLE db_datawriter ADD MEMBER inventory_user;
GO

USE restock;
GO
IF USER_ID('restock_user') IS NULL CREATE USER restock_user FOR LOGIN restock_user;
ALTER ROLE db_ddladmin ADD MEMBER restock_user;
ALTER ROLE db_datareader ADD MEMBER restock_user;
ALTER ROLE db_datawriter ADD MEMBER restock_user;
GO
