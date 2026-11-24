# HomeStock

**Live:** https://aalshaheebieu2024ui.z28.web.core.windows.net
(the services scale to zero when idle: the first visit after a quiet period shows
"starting up" for up to a minute while the containers and databases wake up)

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

**Integration test across the seam** (`tests/integration`): runs against the real compose
stack, with restock calling inventory over HTTP. From the repository root:

```bash
docker compose up -d --build
pip install -r tests/integration/requirements.txt
pytest tests/integration        # the last test stops inventory for a moment and restarts it
```

**API documents:** each service's `openapi.yaml` is generated from its code
(`python export_openapi.py` in the service folder); a test fails if it is out of date.
`system.yaml` at the root describes both services, their configuration, the calls across
the seam and their Azure resources, following `system.schema.json`.

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
tests/integration/        integration test across the seam (needs the compose stack)
system.yaml               machine-readable description of the system (system.schema.json)
docs/architecture.md      architecture, deployment and database diagrams
.github/workflows/        ci.yml and cd.yml
```

## CI/CD

- **CI** (`.github/workflows/ci.yml`) runs on every push to a branch and every pull request:
  ruff and the tests of each service against a SQL Server container (failing below 70%
  coverage), validation of `system.yaml` and both OpenAPI documents, the integration test
  on the compose stack, and a build of both images. Changes reach `main` only through pull
  requests.
- **CD** (`.github/workflows/cd.yml`) runs on every push to `main`: it runs the same CI,
  pushes both images to GHCR tagged with the commit SHA
  (`ghcr.io/alialshaheeb/homestock-<service>:<sha>`), signs in to Azure as a managed identity
  through OpenID Connect (no Azure password is stored), sets each Container App's database
  secret, image and environment variables, writes `ui/config.js` with the services' URLs,
  uploads `ui/` to the storage account's `$web` container, and fails unless `/health` on both
  services answers 200 with the new SHA within about 5 minutes.

GitHub Actions secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
`INVENTORY_DB_PASSWORD`, `RESTOCK_DB_PASSWORD`, `TEST_SA_PASSWORD` (CI's throwaway SQL
Server). Variables: `PREFIX`, `RESOURCE_GROUP`, `UI_STORAGE`.

## Azure: initial setup (done once, by hand)

Everything after this is done by the pipeline. Run in PowerShell with the Azure CLI, signed
in (`az login`) to the Azure for Students subscription. Passwords are placeholders: they are
generated locally, kept in a password manager and stored only as GitHub secrets.

```powershell
$PREFIX = "aalshaheeb-ieu2024"
$RG     = "rg-$PREFIX"
$LOC    = "francecentral"          # one of the 5 regions the subscription allows

# 1. Providers, CLI extension, resource group
foreach ($ns in "Microsoft.App","Microsoft.OperationalInsights","Microsoft.Sql","Microsoft.Storage","Microsoft.ManagedIdentity") { az provider register --namespace $ns --wait }
az extension add --name containerapp --upgrade
az group create --name $RG --location $LOC

# 2. Storage account for the UI, with a static website
$UI_STORAGE = ($PREFIX -replace "-","") + "ui"
az storage account create --name $UI_STORAGE --resource-group $RG --location $LOC --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2
az storage blob service-properties update --account-name $UI_STORAGE --static-website --index-document index.html
az storage account show --name $UI_STORAGE --resource-group $RG --query "primaryEndpoints.web" -o tsv

# 3. SQL server and one serverless database per service, on the free offer
$SQL_SERVER = "$PREFIX-sql"
az sql server create --name $SQL_SERVER --resource-group $RG --location $LOC --admin-user homestockadmin --admin-password "<SQL_ADMIN_PASSWORD>" --minimal-tls-version 1.2
az sql server firewall-rule create --resource-group $RG --server $SQL_SERVER --name AllowAzureServices --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0
foreach ($svc in "inventory","restock") { az sql db create --resource-group $RG --server $SQL_SERVER --name "$PREFIX-$svc-db" --edition GeneralPurpose --compute-model Serverless --family Gen5 --min-capacity 0.5 --capacity 1 --backup-storage-redundancy Local --use-free-limit true --free-limit-exhaustion-behavior AutoPause }

# 4. One contained user per service, with access to its own database only
#    (my IP is allowed only while this runs; sqlcmd comes from the SQL Server image)
$MY_IP = Invoke-RestMethod https://api.ipify.org
az sql server firewall-rule create --resource-group $RG --server $SQL_SERVER --name TempMyIP --start-ip-address $MY_IP --end-ip-address $MY_IP
$HOST_ = "tcp:$SQL_SERVER.database.windows.net,1433"
docker run --rm --entrypoint /opt/mssql-tools18/bin/sqlcmd mcr.microsoft.com/mssql/server:2022-latest -S $HOST_ -d "$PREFIX-inventory-db" -U homestockadmin -P "<SQL_ADMIN_PASSWORD>" -Q "CREATE USER inventory_user WITH PASSWORD = '<INVENTORY_DB_PASSWORD>'; ALTER ROLE db_ddladmin ADD MEMBER inventory_user; ALTER ROLE db_datareader ADD MEMBER inventory_user; ALTER ROLE db_datawriter ADD MEMBER inventory_user;"
docker run --rm --entrypoint /opt/mssql-tools18/bin/sqlcmd mcr.microsoft.com/mssql/server:2022-latest -S $HOST_ -d "$PREFIX-restock-db" -U homestockadmin -P "<SQL_ADMIN_PASSWORD>" -Q "CREATE USER restock_user WITH PASSWORD = '<RESTOCK_DB_PASSWORD>'; ALTER ROLE db_ddladmin ADD MEMBER restock_user; ALTER ROLE db_datareader ADD MEMBER restock_user; ALTER ROLE db_datawriter ADD MEMBER restock_user;"
az sql server firewall-rule delete --resource-group $RG --server $SQL_SERVER --name TempMyIP

# 5. Container Apps environment and the two apps (placeholder image; CD deploys the real ones)
$UI_ORIGIN = "https://aalshaheebieu2024ui.z28.web.core.windows.net"
az containerapp env create --name "$PREFIX-env" --resource-group $RG --location $LOC
az containerapp create --name "$PREFIX-inventory" --resource-group $RG --environment "$PREFIX-env" --image mcr.microsoft.com/k8se/quickstart:latest --ingress external --target-port 8000 --min-replicas 0 --max-replicas 1 --cpu 0.25 --memory 0.5Gi --secrets "database-url=mssql://inventory_user:<INVENTORY_DB_PASSWORD>@$SQL_SERVER.database.windows.net:1433/$PREFIX-inventory-db" --env-vars "DATABASE_URL=secretref:database-url" "CORS_ORIGINS=$UI_ORIGIN" "PORT=8000"
$INVENTORY_URL = "https://" + (az containerapp show --name "$PREFIX-inventory" --resource-group $RG --query properties.configuration.ingress.fqdn -o tsv)
az containerapp create --name "$PREFIX-restock" --resource-group $RG --environment "$PREFIX-env" --image mcr.microsoft.com/k8se/quickstart:latest --ingress external --target-port 8000 --min-replicas 0 --max-replicas 1 --cpu 0.25 --memory 0.5Gi --secrets "database-url=mssql://restock_user:<RESTOCK_DB_PASSWORD>@$SQL_SERVER.database.windows.net:1433/$PREFIX-restock-db" --env-vars "DATABASE_URL=secretref:database-url" "CORS_ORIGINS=$UI_ORIGIN" "PORT=8000" "INVENTORY_URL=$INVENTORY_URL"

# 6. Managed identity for the pipeline: Contributor on this resource group only, trusted
#    only for runs on main of this repository (GitHub sends the subject in both forms)
$IDENTITY = "$PREFIX-github"
az identity create --name $IDENTITY --resource-group $RG --location $LOC
$PRINCIPAL_ID = az identity show --name $IDENTITY --resource-group $RG --query principalId -o tsv
$RG_ID = az group show --name $RG --query id -o tsv
az role assignment create --assignee-object-id $PRINCIPAL_ID --assignee-principal-type ServicePrincipal --role Contributor --scope $RG_ID
az identity federated-credential create --name github-main --identity-name $IDENTITY --resource-group $RG --issuer https://token.actions.githubusercontent.com --subject "repo:alialshaheeb/homestock:ref:refs/heads/main" --audiences api://AzureADTokenExchange
az identity federated-credential create --name github-main-ids --identity-name $IDENTITY --resource-group $RG --issuer https://token.actions.githubusercontent.com --subject "repo:alialshaheeb@215004918/homestock@1410863097:ref:refs/heads/main" --audiences api://AzureADTokenExchange

# 7. Read access for grading
foreach ($prof in "amartini@faculty.ie.edu","bserra@faculty.ie.edu") { az role assignment create --assignee $prof --role Reader --scope $RG_ID }
```

Then: store the secrets and variables listed under CI/CD in the GitHub repository, and make
the two GHCR packages (`homestock-inventory`, `homestock-restock`) public so Azure can pull
them. The first push to `main` deploys everything.
