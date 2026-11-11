"""Entry point: `python app.py` starts the single process (contract §7.1)."""
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import config
import db
from inventory import schema as inventory_schema
from inventory.routes import router as inventory_router
from restock import schema as restock_schema
from restock.routes import router as restock_router

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db([inventory_schema.SCHEMA, restock_schema.SCHEMA])  # each domain registers its schema here
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="HomeStock", lifespan=lifespan)

    @app.middleware("http")
    async def always_revalidate(request, call_next):
        # "no-cache" = the browser may keep a copy but must ask the server whether it
        # is still current, so a changed ui/ file shows up on the next normal refresh.
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-cache")
        return response

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.include_router(inventory_router)
    app.include_router(restock_router)
    # Mounted last so the API routes above win; everything else is the static UI.
    app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")
    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.get_port())
