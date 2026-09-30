# Architecture Decision Records

## 1. Backend language/framework: Python + FastAPI
Date: 2026-09-30
Status: Decided
Context: HomeStock is a small JSON API run as one process, and I need request validation, easy unit testing and a language I can explain without notes.
Decision: I chose Python with FastAPI (served by uvicorn). It gives typed request validation and automatic API docs with very little code.
Alternatives considered: Flask, which I rejected because validation would need extra libraries; Django, which I rejected because its ORM, admin and auth are unnecessary for one SQLite file and two small domains.
Consequences: Few dependencies and simple tests through TestClient; I write the SQL myself with sqlite3, which keeps the data layer visible but means no migrations tool.
