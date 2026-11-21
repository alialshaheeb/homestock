"""Inventory service: locations, items and stock levels, over HTTP."""
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import db, service
from app.migrations import migrate
from app.routes import router

log = logging.getLogger("inventory")
logging.basicConfig(level=logging.INFO, format="%(message)s")

VERSION = os.environ.get("GIT_SHA", "dev")  # set to the commit SHA when the image is deployed


class Health(BaseModel):
    status: str = Field(description='"ok", or "unavailable" with a 503')
    db: str = Field(description='"ok", or the database error')
    version: str = Field(description="Commit SHA of the running image (GIT_SHA), \"dev\" locally")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start-up: wait for the database, apply pending migrations, then the idempotent seed.
    conn = db.connect_with_retry()
    try:
        migrate(conn)
        service.seed(conn)
    finally:
        conn.close()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="HomeStock inventory", version=VERSION, lifespan=lifespan)

    # The browser calls this service from the UI's address, so only that origin is allowed.
    origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Content-Type"],
        )

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        """One line per request on stdout: method, path, status, duration."""
        start = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - start) * 1000
        log.info("%s %s %s %.0fms", request.method, request.url.path, response.status_code, ms)
        return response

    @app.get("/health", response_model=Health,
             responses={503: {"model": Health, "description": "The database cannot be read or written"}})
    def health():
        """200 only if this service can read and write its own database (the restock
        service's state is never part of it). The write is rolled back."""
        try:
            conn = db.connect()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM schema_migrations")
                cursor.fetchone()
                cursor.execute("INSERT INTO schema_migrations (version) VALUES (N'__health_probe__')")
                conn.rollback()
            finally:
                conn.close()
        except Exception as error:  # any failure means "not healthy", never a stack trace
            return JSONResponse({"status": "unavailable", "db": str(error)[:200], "version": VERSION}, status_code=503)
        return {"status": "ok", "db": "ok", "version": VERSION}

    app.include_router(router)
    return app


app = create_app()
