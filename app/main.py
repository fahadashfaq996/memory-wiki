from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api import memory, transcripts
from app.api.deps import get_object_store
from app.config import get_settings
from app.db.session import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("memory.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    get_object_store().ensure_bucket()
    logger.info("API ready (bucket=%s)", settings.s3_bucket)
    yield


app = FastAPI(title="Memory Wiki", version="0.1.0", lifespan=lifespan)
app.include_router(transcripts.router)
app.include_router(memory.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
