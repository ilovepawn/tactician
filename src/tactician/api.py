"""FastAPI app entry point.

Run via:
    uvicorn tactician.api:app --host 0.0.0.0 --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymysql.connections import Connection

from tactician.adapters import mysql_reader
from tactician.config import load_config
from tactician.db import get_db, init_pool


@asynccontextmanager
async def lifespan(_: FastAPI):
    cfg = load_config()
    init_pool(cfg.mysql)
    yield


app = FastAPI(title="Tactician API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


class Theme(BaseModel):
    name: str
    count: int


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/themes", response_model=list[Theme])
def get_themes(conn: Connection = Depends(get_db)) -> list[Theme]:
    return [Theme(**row) for row in mysql_reader.list_themes(conn)]
