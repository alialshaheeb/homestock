# AI Usage Log

| Date/commit | Tool | Prompt | Disposition (Accepted/Modified/Rejected) | What changed & why (if modified) | In my own words, how this works |
|---|---|---|---|---|---|
| 2026-09-30 / 6ef9afe | Claude | Scaffold repo with env-based config, requirements, gitignore | Accepted | | TODO (Ali): explain what get_port() and db_path() in config.py do and why HOST is fixed to 0.0.0.0 |
| 2026-09-30 / d5e5a37 | Claude | Add FastAPI app with /health, SQLite helper, first test | Accepted | | TODO (Ali): explain get_connection(), init_db(schemas), the lifespan function and what test_health checks |
| 2026-09-30 / ADR-1 commit | Claude | Draft ADR-1 (framework choice) | Accepted | (update to Modified if I rewrite it) | TODO (Ali): explain in my own words why FastAPI over Flask and Django |
| 2026-09-30 / Inventory schema commit | Claude | Create inventory tables (locations, items), register schema at startup, add schema tests | Accepted | | TODO (Ali): explain the CHECK constraints, REFERENCES, INSERT OR IGNORE seeding, and what each of the 4 tests proves |
