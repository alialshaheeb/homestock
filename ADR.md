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

## 4. Test the domain logic against a real SQLite file, and the routes only for HTTP behaviour
Date: 2026-11-10
Status: Decided
Context: The 70% coverage bar is on core business logic. Most of HomeStock's rules (stock never below zero, what counts as low stock, one open list entry per item, buying restocks Inventory) are enforced partly in Python and partly by SQLite constraints.
Decision: Service tests call inventory/service.py and restock/service.py directly on a fresh temporary SQLite file per test, with no mocks, so the constraints are exercised too. Restock is tested against the real Inventory functions. Route tests only check status codes (201/204/404/409/422) and one end-to-end flow (low stock → list → bought → restocked). Coverage is measured on the inventory and restock packages.
Alternatives considered: Mocking the database or the inventory client: faster and more isolated, but it would not catch a broken SQL query or constraint, which is where most bugs here would be. Testing only through HTTP: covers everything at once, but failures point to the route instead of the rule.
Consequences: 42 tests run in about a second with 99% coverage of the two domains. Left thinner on purpose: the JavaScript UI (checked by hand in a browser) and the `python app.py` start-up line. When Restock calls Inventory over HTTP (Assignment 2), its tests will need a stub or a running Inventory service.

## 5. No user accounts or login
Date: 2026-11-10
Status: Decided
Context: HomeStock is used by one household on its own network: everyone who can open it is allowed to change the stock. Adding login was one of the free choices (§1b).
Decision: No authentication, user accounts or per-user data. Every request acts on the single household's data.
Alternatives considered: Session login with hashed passwords: needed if several households shared one deployment or the app were exposed to the internet, but it adds a users table, password storage, sessions and their tests, none of which serves the two domains being built. HTTP basic auth with one shared password: cheap, but gives a false sense of security over plain HTTP and is easy to leak.
Consequences: The code stays focused on Inventory and Restock, and there is no password data to protect. The app must not be exposed publicly as-is; before deploying it to the internet (Assignment 2), access control has to be added or the deployment restricted, and every table would need a household id if more than one household used it.
