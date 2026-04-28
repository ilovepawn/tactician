"""Prometheus metrics for the API.

HTTP-level metrics (latency, QPS, status, in-progress) are produced by
prometheus_fastapi_instrumentator in api.py. This module owns the
domain-specific counters and DB-pool gauges, which the route handlers and
db.py update directly.
"""
from prometheus_client import Counter, Gauge

PUZZLES_SERVED = Counter(
    "tactician_puzzles_served_total",
    "Puzzles successfully returned by the API.",
    ["endpoint", "theme"],
)

PUZZLE_NOT_FOUND = Counter(
    "tactician_puzzle_not_found_total",
    "Puzzle requests that returned 404.",
    ["endpoint"],
)

THEMES_QUERIED = Counter(
    "tactician_themes_queried_total",
    "Calls to the /themes listing endpoint.",
)

DB_POOL_IN_USE = Gauge(
    "tactician_db_pool_connections_in_use",
    "DB connections currently checked out from the pool.",
)

DB_POOL_MAX = Gauge(
    "tactician_db_pool_connections_max",
    "Configured max connections in the DB pool.",
)
