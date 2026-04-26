# Tactician

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![MySQL](https://img.shields.io/badge/MySQL-8.4-4479A1?logo=mysql&logoColor=white)](https://www.mysql.com/)
[![MinIO](https://img.shields.io/badge/MinIO-S3--Compatible-C72E49?logo=minio&logoColor=white)](https://min.io/)
[![Stockfish](https://img.shields.io/badge/Stockfish-18-000000?logo=lichess&logoColor=white)](https://stockfishchess.org/)
[![License](https://img.shields.io/badge/License-AGPL--3.0--or--later-blue)](LICENSE)

[한국어](README.ko.md)

> *Tactician (n.)* — A specialist in finding the move that turns a position decisive.

**Puzzle Service** for the [ilovepawn](https://github.com/ilovepawn) chess platform. Mines tactical puzzles from platform games and serves them to users.

Every puzzle is auto-discovered by Stockfish from real games played on the platform — no hand-crafting, no curation overhead. Spot the blunder, deliver the punishment.

---

## How It Works

1. Users finish their games on the platform
2. Annotated PGNs (with Stockfish `%eval` markers) flow into the service's S3 bucket
3. A nightly batch scans games for blunders and forced wins, extracting puzzle candidates
4. Each candidate is auto-tagged (`fork`, `pin`, `mateIn3`, `zugzwang`, ...) using ~60 themed pattern detectors
5. Tagged puzzles land in MySQL, ready to be served

The pattern recognition logic is vendored from [Lichess's puzzle generator](https://github.com/ornicar/lichess-puzzler) under AGPL-3.0 — battle-tested on millions of Lichess games.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Chess Engine | Stockfish 18 (UCI) |
| Pattern Logic | python-chess + vendored lichess-puzzler |
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

```bash
# Copy environment config (only needed for host-mode runs; compose ignores .env)
cp .env.example .env

# Start MySQL + MinIO
docker compose up -d

# Apply database schema
docker exec -i tactician-db-1 mysql -u tactician -ptactician tactician < migrations/001_init.sql

# Build the batch worker image (one-time / when Dockerfile or deps change)
docker compose build batch

# Daily batch (production mode, pulls from S3)
docker compose run --rm batch --date 2026-04-26

# Ad-hoc: run on a local PGN file. Mount its host directory via LICHESS_DUMP_DIR.
LICHESS_DUMP_DIR=/Volumes/bobo-01 \
  docker compose run --rm batch \
    --file /mnt/lichess/lichess_db_standard_rated_2026-03_eval.pgn.zst \
    --max-games 200
```

> The `batch` service uses a compose `profiles: [batch]` flag so it does **not** auto-start with `docker compose up -d`. Invoke it explicitly with `docker compose run --rm batch ...`.

#### Host-mode (developer convenience)

If you'd rather iterate without rebuilding the image, you can still run the batch on the host. You'll need Python 3.13, [uv](https://docs.astral.sh/uv/), and Stockfish (`brew install stockfish`):

```bash
uv sync
uv run python -m tactician.batch --file games.pgn.zst --max-games 100
```

---

## Batch CLI

```bash
docker compose run --rm batch [options]
```

| Option | Description |
|---|---|
| `--date YYYY-MM-DD` | Pull annotated PGNs from S3 for the given date. Defaults to yesterday. |
| `--file PATH` | Run on a local `.pgn` or `.pgn.zst` file. Bypasses S3. |
| `--max-games N` | Process only the first N games (testing convenience). |

The batch runs three stages in order: **download → generate → tag**. Per-game timing and tagging stats are logged.

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
│   ├── config.py      # Environment configuration
│   └── adapters/      # MySQL writer, S3 reader, tagger I/O
├── migrations/        # Plain SQL migrations
├── Dockerfile         # Batch worker image (Python + Stockfish 18)
├── docker-compose.yml
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
