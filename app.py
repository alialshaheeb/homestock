"""Entry point: `python app.py` starts the single process (contract §7.1)."""
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

import config
import db
from inventory import schema as inventory_schema
from inventory.routes import router as inventory_router
from restock import schema as restock_schema
from restock.routes import router as restock_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db([inventory_schema.SCHEMA, restock_schema.SCHEMA])  # each domain registers its schema here
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="HomeStock", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.include_router(inventory_router)
    app.include_router(restock_router)
    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.get_port())
