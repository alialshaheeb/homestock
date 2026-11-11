# HomeStock

Household inventory and restock list. Track what is in the fridge, pantry and
cupboards, see what is running low or about to expire, and turn that into a
shopping list. Buying something on the list puts it back in stock.

Since Assignment 2 it runs as **two services**, each with its own SQL Server database,
and a static UI that calls both:

| Part | Folder | Owns | Local address |
|---|---|---|---|
| inventory service | `services/inventory` | places (`locations`) and `items` | http://localhost:8001 (docs at `/docs`) |
| restock service | `services/restock` | `shopping_list`; asks inventory over HTTP for stock | http://localhost:8002 (docs at `/docs`) |
| UI | `ui` | static HTML/CSS/JS | http://localhost:8080 |

The restock service finds the inventory service through `INVENTORY_URL`. If inventory is
down, the shopping list still loads; "add everything running low" and "mark bought" on a
linked item answer 503 with a clear message instead of failing silently.

## Run everything locally

Needs Docker Desktop (on Apple Silicon, enable Rosetta in its settings).

```bash
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
docker compose up --build
```

The first start downloads SQL Server and takes a few minutes; afterwards about 30 s,
because SQL Server must be healthy before `db-init` creates the databases and logins and
the services start. Then open http://localhost:8080.

- Stop: `Ctrl+C`, or `docker compose down`. Data is kept in the `sqldata` volume.
- Wipe all data: `docker compose down -v`.
- Try a partial failure: `docker compose stop inventory`, then use the shopping list.
  `docker compose start inventory` brings it back.

## Configuration

Each service reads only environment variables.

| Variable | Service | Default | Meaning |
|---|---|---|---|
| `DATABASE_URL` | both | none (required, secret) | `mssql://user:password@host:1433/database` |
| `PORT` | both | `8000` | Port inside the container |
| `CORS_ORIGINS` | both | none | Comma-separated origins allowed to call the API (the UI's address) |
| `GIT_SHA` | both | `dev` | Version reported by `/health` |
| `INVENTORY_URL` | restock | `http://inventory:8000` | Base URL of the inventory service |
| `INVENTORY_TIMEOUT_S` | restock | `2` | Timeout for every call to inventory, in seconds |

The UI reads the two service URLs from `ui/config.js`.

## Database and migrations

Each service creates and changes its own tables with numbered SQL files in
`services/<name>/migrations/`, applied automatically and in order at start-up. Applied
files are recorded in a `schema_migrations` table, so a restart applies nothing. An applied
file is never edited; a change goes in a new file.

## Tests

Tests run per service against a real SQL Server test database. With the compose stack
running (it publishes SQL Server on port 1433), from a service folder:

```bash
cd services/inventory                     # or services/restock
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt     # Windows: .venv\Scripts\pip
export TEST_DATABASE_URL="mssql://sa:<SA_PASSWORD from .env>@localhost:1433/inventory_test"
# PowerShell: $env:TEST_DATABASE_URL="mssql://sa:<SA_PASSWORD>@localhost:1433/inventory_test"
pytest --cov=app --cov-report=term-missing
ruff check .
```

The test database (`inventory_test`, `restock_test`) is created if missing and emptied
before each test. Without `TEST_DATABASE_URL`, only the tests that need no database run.
Restock's tests replace the inventory service with an in-memory fake.

## Run one service on its own

```bash
cd services/inventory
DATABASE_URL="mssql://sa:<SA_PASSWORD>@localhost:1433/inventory" uvicorn app.main:app --port 8001
```

## Repository layout

```
docker-compose.yml        SQL Server, db-init, both services, nginx for the UI
db/init.sql               local only: creates both databases and one login per service
services/inventory/       Dockerfile, requirements*.txt, app/, migrations/, tests/
services/restock/         same; app/inventory_client.py is the only code that calls inventory
ui/                       static UI; config.js says where the services are
ADR.md, AI_USAGE.md       decision records and AI usage log
```
