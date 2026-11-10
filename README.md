# HomeStock

Household inventory and restock list. Track what is in the fridge, pantry and
cupboards, see what is running low or about to expire, and turn that into a
shopping list. Buying something on the list puts it back in stock.

Python 3.10+ / FastAPI / SQLite, one process, one container.

## Run it

```bash
git clone https://github.com/alialshaheeb/homestock.git
cd homestock
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:8000 for the UI. The API docs are at http://localhost:8000/docs.

No setup step is needed: on start-up the app creates the database file, its
tables and the default locations (fridge, pantry, toiletries) if they are missing.

## Configuration

Everything is set through environment variables; none are required.

| Variable   | Default  | Meaning |
|------------|----------|---------|
| `PORT`     | `8000`   | Port the server listens on (always bound to `0.0.0.0`) |
| `DATA_DIR` | `./data` | Directory holding the SQLite file |

The database lives at **`$DATA_DIR/homestock.db`** (by default `./data/homestock.db`).

## Structure

```
app.py               entry point: creates the app, registers both domains, serves ui/
config.py            reads PORT and DATA_DIR
db.py                SQLite connection helper and start-up schema runner
inventory/           domain 1: locations and items, stock levels, expiry
  schema.py          tables: locations, items
  service.py         all inventory logic and SQL
  routes.py          /locations, /items
restock/             domain 2: the shopping list
  schema.py          table: shopping_list
  service.py         all shopping-list logic and SQL
  inventory_client.py   the only code in restock that talks to inventory (the seam)
  routes.py          /shopping-list
ui/                  static HTML/CSS/JS that calls the API
tests/               pytest suite
ADR.md               architecture decision records
AI_USAGE.md          log of AI-assisted changes
```

## API overview

| Method | Path | What it does |
|---|---|---|
| GET | `/health` | Liveness check |
| GET, POST | `/locations` | List or add storage locations |
| GET | `/items?location_id=&low_stock=true&expiring_within_days=3` | List items, with optional filters |
| POST | `/items` | Add an item |
| GET, PATCH, DELETE | `/items/{id}` | Read, change or remove an item |
| POST | `/items/{id}/consume` | Use up an amount (`{"amount": 1}`); 409 if more than in stock |
| POST | `/items/{id}/restock` | Add an amount to stock |
| GET | `/shopping-list?status=open\|bought` | The shopping list |
| POST | `/shopping-list` | Add an entry: free text (`name`) or linked (`inventory_item_id`) |
| POST | `/shopping-list/from-low-stock` | Add every low-stock item not already on the list |
| GET, PATCH, DELETE | `/shopping-list/{id}` | Read, change or remove an entry |
| POST | `/shopping-list/{id}/bought` | Mark bought; a linked entry restocks its inventory item |

Full request and response schemas: `/docs` while the app runs.

## Tests and coverage

```bash
pytest --cov=inventory --cov=restock --cov-report=term-missing
```

Coverage is measured on the two domain packages, where the business logic lives.

Result at the time of writing: **42 tests passed, 99% coverage** (273 statements, 1 missed).
