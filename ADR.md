# Architecture Decision Records

## 1. Backend language/framework: Python + FastAPI
Date: 2026-09-30
Status: Decided
Context: HomeStock is a small JSON API run as one process, and I need request validation, easy unit testing and a language I can explain without notes.
Decision: I chose Python with FastAPI (served by uvicorn). It gives typed request validation and automatic API docs with very little code.
Alternatives considered: Flask, which I rejected because validation would need extra libraries; Django, which I rejected because its ORM, admin and auth are unnecessary for one SQLite file and two small domains.
Consequences: Few dependencies and simple tests through TestClient; I write the SQL myself with sqlite3, which keeps the data layer visible but means no migrations tool.

## 2. Two domains, Inventory and Restock, joined only through Inventory's service functions
Date: 2026-11-10
Status: Decided
Context: HomeStock does two separate jobs: tracking what is in the house (Inventory) and deciding what to buy (Restock list). Assignment 2 will run them as separate services with separate data, so the boundary has to be clean now even though both live in one process.
Decision: Each domain is its own package (inventory/, restock/) owning its own tables and routes. Restock never reads or writes Inventory's tables; it only calls the public functions in inventory/service.py (list low-stock items, restock an item), which become HTTP calls after the split. A shopping-list row stores the Inventory item id as a plain number, not a foreign key.
Alternatives considered: A shopping list that JOINs directly on the items table: simpler queries today, but it breaks as soon as each service owns its own database. Splitting by entity (locations vs items): rejected because an item cannot exist without its location, so the two halves would call each other on almost every request.
Consequences: Inventory can move into its own service without code changes on its side. The cost: Restock must copy what it shows (item name, unit) when it adds a row, and the database no longer stops a shopping-list row from pointing at a deleted item, so that case is handled in code.

## 3. Shopping-list rows reference Inventory items by a plain id and keep their own copy of name and unit
Date: 2026-11-10
Status: Decided
Context: The two domains share one SQLite file for now, but ADR-2 requires that each owns its tables. The shopping list still needs to point at the Inventory item it restocks.
Decision: Inventory keeps a real foreign key inside its own domain (items.location_id → locations.id, with CHECK constraints on quantities). shopping_list.inventory_item_id is a nullable plain INTEGER with no FOREIGN KEY, and name/unit are copied into the row when it is added. A partial UNIQUE index allows only one open entry per Inventory item.
Alternatives considered: A FOREIGN KEY from shopping_list to items: the database would guarantee the link, but it ties the two domains to one database and makes deleting an item fail while it is on the list. Storing only the id and looking up the name each time: no duplicated data, but every list view would need Inventory.
Consequences: The list renders on its own, and the split in Assignment 2 needs no schema change. Copied names can go stale if an item is renamed, and a row can point at a deleted item; mark_bought() handles that case and reports restocked=false.
