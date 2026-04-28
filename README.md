# Tactician

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![MySQL](https://img.shields.io/badge/MySQL-8.4-4479A1?logo=mysql&logoColor=white)](https://www.mysql.com/)
[![MinIO](https://img.shields.io/badge/MinIO-S3--Compatible-C72E49?logo=minio&logoColor=white)](https://min.io/)
[![Stockfish](https://img.shields.io/badge/Stockfish-18-000000?logo=lichess&logoColor=white)](https://stockfishchess.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-AGPL--3.0--or--later-blue)](LICENSE)

[한국어](README.ko.md)

> *Tactician (n.)* — A specialist in finding the move that turns a position decisive.

**Puzzle Service** for the [ilovepawn](https://github.com/ilovepawn) chess platform. Mines tactical puzzles from platform games and serves them to users.

Every puzzle is auto-discovered by Stockfish from real games played on the platform — no hand-crafting, no curation overhead. Spot the blunder, deliver the punishment.

---

## How It Works

1. Users finish their games on the platform
2. Annotated PGNs (with Stockfish `%eval` markers) flow into the platform's shared S3 bucket (produced by a separate analysis service; tactician is a consumer)
3. A nightly batch scans games for blunders and forced wins, extracting puzzle candidates
4. Each candidate is auto-tagged (`fork`, `pin`, `mateIn3`, `zugzwang`, ...) using ~60 themed pattern detectors
5. Tagged puzzles land in MySQL
6. The HTTP API serves them to clients (single, random, by theme)

The pattern recognition logic is vendored from [Lichess's puzzle generator](https://github.com/ornicar/lichess-puzzler) under AGPL-3.0 — battle-tested on millions of Lichess games.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Chess Engine | Stockfish 18 (UCI) |
| Pattern Logic | python-chess + vendored lichess-puzzler |
| HTTP API | FastAPI + uvicorn (Pydantic, DBUtils PooledDB) |
| Database | MySQL 8.4 LTS |
| Object Storage | MinIO (S3-compatible) |
| Package Manager | uv |
| Infrastructure | Docker Compose |

---

## Getting Started

### Prerequisites

- Docker & Docker Compose

The batch worker image bundles Python 3.13, all dependencies, and Stockfish 18 (compiled from source for reproducibility), so no host-side Python or Stockfish install is required.

### Run

Tactician runs inside the platform's unified dev stack. Clone the [`infra`](https://github.com/ilovepawn/infra) repo as a sibling directory of `tactician/`, then drive the stack from `infra/compose/` — see [infra/compose/README.md](https://github.com/ilovepawn/infra/blob/main/compose/README.md).

```bash
# Bring up the platform stack (MySQL ×3, MinIO, RabbitMQ, ..., tactician api)
cd ../infra/compose && docker compose up -d

# Apply database schema (run from tactician/ — migrations live here)
for f in migrations/*.sql; do
  docker exec -i ilovepawn-tactician-mysql mysql -u mwzz6 -p1234 tactician < "$f"
done

# Rebuild after Dockerfile / deps change
cd ../infra/compose && docker compose build tactician tactician-batch

# Daily batch (production mode, pulls from S3)
cd ../infra/compose && docker compose run --rm tactician-batch --date 2026-04-26

# Ad-hoc: run on a local PGN file. Mount its host directory via LICHESS_DUMP_DIR.
LICHESS_DUMP_DIR=/Volumes/bobo-01 \
  docker compose -f ../infra/compose/docker-compose.yml run --rm tactician-batch \
    --file /mnt/lichess/lichess_db_standard_rated_2026-03_eval.pgn.zst \
    --max-games 200
```

> `tactician-batch` is `profiles: [batch]`-gated in the infra compose so it does **not** auto-start with `up -d`. Invoke it explicitly via `docker compose run --rm tactician-batch ...`. The `tactician` (api) service has no profile and starts with the default `up`.

---

## Batch CLI

```bash
cd ../infra/compose && docker compose run --rm tactician-batch [options]
```

| Option | Description |
|---|---|
| `--date YYYY-MM-DD` | Pull annotated PGNs from S3 for the given date. Defaults to yesterday. |
| `--file PATH` | Run on a local `.pgn` or `.pgn.zst` file. Bypasses S3. |
| `--max-games N` | Process only the first N games (testing convenience). |

The batch runs three stages in order: **download → generate → tag**. Per-game timing and tagging stats are logged.

---

## HTTP API

The API serves puzzles from MySQL on port **8000**. Auto-generated OpenAPI docs at <http://localhost:8000/docs>.

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness probe (no DB access) |
| GET | `/themes` | All themes with puzzle counts, sorted by count desc |
| GET | `/puzzles/{id}` | Single puzzle (`404` if missing or hidden) |
| GET | `/puzzles/random?theme=...` | Random puzzle, optional theme filter |

### Response shape

JSON fields are camelCase (auto-converted from snake_case Python via Pydantic's `to_camel` alias generator).

`GET /puzzles/1`:

```json
{
  "id": 1,
  "gameId": "mtLpMvxs",
  "fen": "8/p3k3/2p1P1p1/P3K1P1/8/8/8/8 b - - 0 42",
  "moves": ["c6c5", "e5d5", "c5c4", "d5c4", "e7e6", "c4b5", "e6d5", "b5a6"],
  "difficulty": 0,
  "themes": ["crushing", "pawnEndgame", "veryLong"]
}
```

Errors follow FastAPI defaults: `{"detail": "..."}` for handled errors, structured validation errors for `422`.

---

## Data Model

### `puzzle`

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT AUTO_INCREMENT | PK |
| `game_id` | VARCHAR(64) | Source game identifier |
| `fen` | VARCHAR(100) `utf8mb4_bin` | Starting position (case-sensitive) |
| `ply` | INT | Half-move index in the original game |
| `moves` | VARCHAR(255) | Solution sequence (UCI, space-separated) |
| `cp` | INT | Centipawn evaluation; magic values for mate |
| `generator_version` | INT | Algorithm version |
| `is_hidden` | BOOLEAN | Soft-hide flag |
| `created_at` | DATETIME | Insert timestamp |
| `difficulty` | INT | Difficulty score (0 until rating algorithm wired up) |

### `puzzle_theme`

Junction table. `(puzzle_id, theme)` composite primary key. Themes are emitted by the upstream tagger from a fixed list of ~60 patterns.

---

## Project Structure

```
tactician/
├── upstream/          # Vendored lichess-puzzler (AGPL-3.0, untouched)
│   ├── generator/     # Puzzle candidate detection
│   └── tagger/        # Theme classifier (~60 patterns)
├── src/tactician/
│   ├── batch.py       # Daily batch entry point
│   ├── api.py         # FastAPI app (HTTP service)
│   ├── db.py          # MySQL connection pool (used by api)
│   ├── config.py      # Environment configuration
│   └── adapters/      # mysql_writer (batch), mysql_reader (api), s3_reader, mysql_tagger_io
├── migrations/        # Plain SQL migrations (apply in filename order)
├── Dockerfile         # Shared image for batch + api (Python + Stockfish 18)
└── pyproject.toml
```

The upstream code is plugged into our infrastructure via runtime monkey-patching of its `Server` class — no upstream source modification required.

---

## Attribution

Vendors and adapts code from [lichess-puzzler](https://github.com/ornicar/lichess-puzzler) by Thibault Duplessis (ornicar). The vendored code lives in `upstream/` and retains its original AGPL-3.0 license. See `upstream/UPSTREAM.md` for the exact commit and update procedure.

---

## License

This project is licensed under the **AGPL-3.0-or-later License** — see the [LICENSE](LICENSE) file for details.

AGPL-3.0-or-later is required because we vendor `lichess-puzzler` (AGPL) and depend on `python-chess` (GPL).
