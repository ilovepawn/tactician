"""Connection pool for the API. Batch worker keeps using its own per-job
connections; pooling is only beneficial for the concurrent request workload.
"""
from typing import Generator

import pymysql
from dbutils.pooled_db import PooledDB
from pymysql.connections import Connection

from tactician.config import MySQLConfig

_pool: PooledDB | None = None


def init_pool(cfg: MySQLConfig) -> None:
    global _pool
    _pool = PooledDB(
        creator=pymysql,
        mincached=2,
        maxcached=5,
        maxconnections=20,
        blocking=True,
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
        autocommit=True,
        charset="utf8mb4",
    )


def get_db() -> Generator[Connection, None, None]:
    """FastAPI dependency. Yields a pooled connection; close() returns it to the pool."""
    if _pool is None:
        raise RuntimeError("init_pool() must be called before get_db()")
    conn = _pool.connection()
    try:
        yield conn
    finally:
        conn.close()
