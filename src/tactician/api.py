"""FastAPI app entry point.

Run via:
    uvicorn tactician.api:app --host 0.0.0.0 --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
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


class Puzzle(BaseModel):
    # snake_case Python fields auto-serialized as camelCase JSON
    # (e.g. game_id -> gameId) via the to_camel alias generator.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: int
    game_id: str
    fen: str
    moves: list[str]
    difficulty: int
    themes: list[str]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/themes", response_model=list[Theme])
def get_themes(conn: Connection = Depends(get_db)) -> list[Theme]:
    return [Theme(**row) for row in mysql_reader.list_themes(conn)]


@app.get("/puzzles/random", response_model=Puzzle)
def get_random_puzzle(
    theme: str | None = None, conn: Connection = Depends(get_db)
) -> Puzzle:
    row = mysql_reader.random_puzzle(conn, theme or None)
    if row is None:
        raise HTTPException(status_code=404, detail="no puzzle matches")
    return Puzzle(**row)


@app.get("/puzzles/{puzzle_id}", response_model=Puzzle)
def get_puzzle(puzzle_id: int, conn: Connection = Depends(get_db)) -> Puzzle:
    row = mysql_reader.get_puzzle(conn, puzzle_id)
    if row is None:
        raise HTTPException(status_code=404, detail="puzzle not found")
    return Puzzle(**row)
