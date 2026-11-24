# Architecture

## Before: the Assignment 1 monolith

```mermaid
flowchart LR
    browser[Browser] -->|HTTP| app
    subgraph app[One FastAPI process, one container]
        ui[UI static files]
        inv[inventory package<br/>routes + service.py]
        rst[restock package<br/>routes + service.py]
        rst -->|Python function calls<br/>list low stock, restock item| inv
    end
    inv --> db[(One SQLite file<br/>locations, items, shopping_list)]
    rst --> db
```

## After: two services, one database each

```mermaid
flowchart LR
    browser[Browser] -->|static files| web[Storage static website<br/>ui/ + config.js]
    browser -->|HTTPS JSON, CORS| inv
    browser -->|HTTPS JSON, CORS| rst
    subgraph inventory service
        inv[inventory API<br/>/locations /items /health]
    end
    subgraph restock service
        rst[restock API<br/>/shopping-list /health]
    end
    rst -->|"the seam, HTTP, 2 s timeout:<br/>GET /items?low_stock=true<br/>GET /items/{id}<br/>POST /items/{id}/restock"| inv
    inv --> invdb[(inventory database<br/>locations, items,<br/>schema_migrations)]
    rst --> rstdb[(restock database<br/>shopping_list,<br/>schema_migrations)]
```

Restock never reads Inventory's database; `shopping_list.inventory_item_id` is a plain number.
If Inventory is down, Restock answers 503 for the three calls above and keeps serving its list.

## Deployment

```mermaid
flowchart LR
    dev[git push / PR] --> gh[GitHub<br/>alialshaheeb/homestock]
    gh --> ci[GitHub Actions CI<br/>lint, tests + 70% coverage,<br/>docs, integration, build]
    ci -->|main only| cd[GitHub Actions CD]
    cd -->|push images tagged with SHA| ghcr[GHCR<br/>homestock-inventory<br/>homestock-restock]
    cd -->|OIDC login as<br/>aalshaheeb-ieu2024-github| az
    subgraph az[Azure: rg-aalshaheeb-ieu2024, France Central]
        subgraph env[Container Apps env: aalshaheeb-ieu2024-env + Log Analytics]
            ca1[aalshaheeb-ieu2024-inventory<br/>0 to 1 replica]
            ca2[aalshaheeb-ieu2024-restock<br/>0 to 1 replica]
        end
        subgraph sql[SQL server: aalshaheeb-ieu2024-sql]
            db1[(aalshaheeb-ieu2024-inventory-db<br/>serverless, free offer)]
            db2[(aalshaheeb-ieu2024-restock-db<br/>serverless, free offer)]
        end
        st[Storage: aalshaheebieu2024ui<br/>static website $web]
    end
    ghcr -->|image pull| ca1
    ghcr -->|image pull| ca2
    cd -->|upload ui/ + config.js| st
    ca1 --> db1
    ca2 --> db2
    ca2 -->|HTTPS| ca1
```

## Databases (after migration 002)

```mermaid
erDiagram
    locations ||--o{ items : "location_id (FK)"
    locations {
        INT id PK
        NVARCHAR name UK
    }
    items {
        INT id PK
        NVARCHAR name
        INT location_id FK
        FLOAT quantity "CHECK >= 0"
        NVARCHAR unit
        FLOAT min_threshold "CHECK >= 0"
        DATE expiry_date "NULL"
        DATETIME2 created_at
        DATETIME2 updated_at "added by 002, backfilled"
    }
```

```mermaid
erDiagram
    shopping_list {
        INT id PK
        NVARCHAR name
        FLOAT quantity
        NVARCHAR unit
        INT inventory_item_id "plain id, no FK across the seam"
        NVARCHAR source "manual or low_stock"
        NVARCHAR status "open or bought"
        DATETIME2 created_at
        DATETIME2 bought_at "NULL"
    }
```

A filtered unique index on `shopping_list (inventory_item_id) WHERE status = 'open'` allows
only one open entry per Inventory item. Each database also has `schema_migrations`.
