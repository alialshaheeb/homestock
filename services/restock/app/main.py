"""Restock service: the shopping list, over HTTP. Calls the inventory service for stock."""
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import db
from app.inventory_client import InventoryUnavailable
from app.migrations import migrate
from app.routes import router

log = logging.getLogger("restock")
logging.basicConfig(level=logging.INFO, format="%(message)s")

VERSION = os.environ.get("GIT_SHA", "dev")  # set to the commit SHA when the image is deployed


class Health(BaseModel):
    status: str = Field(description='"ok", or "unavailable" with a 503')
    db: str = Field(description='"ok", or the database error')
    version: str = Field(description="Commit SHA of the running image (GIT_SHA), \"dev\" locally")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start-up: wait for the database, then apply pending migrations. Restock has no seed data.
    conn = db.connect_with_retry()
    try:
        migrate(conn)
    finally:
        conn.close()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="HomeStock restock", version=VERSION, lifespan=lifespan)

    # The browser calls this service from the UI's address, so only that origin is allowed.
    origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Content-Type"],
        )

    @app.exception_handler(InventoryUnavailable)
    async def inventory_unavailable(request: Request, error: InventoryUnavailable):
        """Safety net for any route: Inventory being down is a clear 503, never a 500.
        (A 500 would also lose its CORS headers, and the browser would see no answer at all.)"""
        return JSONResponse(
            {"detail": "The inventory service is not reachable right now. Try again in a moment."}, status_code=503
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
        """200 only if this service can read and write its own database. The inventory
        service's state is never part of it: Inventory being down does not make this 503."""
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
