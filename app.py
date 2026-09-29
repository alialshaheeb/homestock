"""Entry point: `python app.py` starts the single process (contract §7.1)."""
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

import config
import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db([])  # domain schemas get registered here as they are added
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="HomeStock", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.get_port())
