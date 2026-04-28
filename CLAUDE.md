# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tactician is the puzzle service for the ilovepawn chess platform. It mines tactical puzzles from platform games (daily batch) and serves them to clients via an HTTP API. Both responsibilities live in this single repo; they share the same Docker image but run as separate compose services with different entrypoints.

The puzzle detection and theme classification logic is vendored from [Lichess's puzzle generator](https://github.com/ornicar/lichess-puzzler) under AGPL-3.0 and used **without modification**. Our code lives in `src/tactician/` and is composed of thin adapters that plug the vendored code into our MySQL/S3 stack via runtime monkey-patching.

## Commands

All container workflows are driven from the sibling `infra` repo's unified compose
(`../infra/compose/docker-compose.yml`). Tactician no longer ships its own compose file.
See `../infra/compose/README.md` for the full stack layout.

```bash
# Bring up the platform stack (MySQL ×3, MinIO, RabbitMQ, ..., tactician api)
cd ../infra/compose && docker compose up -d

# Apply schema (run from tactician/ — migrations live here)
for f in migrations/*.sql; do
  docker exec -i ilovepawn-tactician-mysql mysql -u mwzz6 -p1234 tactician < "$f"
done

# Rebuild the tactician image after Dockerfile / deps change
cd ../infra/compose && docker compose build tactician tactician-batch

# Daily batch (production mode — pulls from S3)
cd ../infra/compose && docker compose run --rm tactician-batch --date 2026-04-26

# Ad-hoc: run on a local PGN file mounted from the host via LICHESS_DUMP_DIR
LICHESS_DUMP_DIR=/Volumes/bobo-01 \
  docker compose -f ../infra/compose/docker-compose.yml run --rm tactician-batch \
    --file /mnt/lichess/lichess_db_standard_rated_2026-03_eval.pgn.zst \
    --max-games 200

# API smoke check
curl http://localhost:8000/health
curl http://localhost:8000/themes
curl http://localhost:8000/puzzles/1
curl 'http://localhost:8000/puzzles/random?theme=fork'

# Inspect generated puzzles
docker exec ilovepawn-tactician-mysql mysql -u mwzz6 -p1234 tactician \
  -e "SELECT id, game_id, ply, cp, difficulty FROM puzzle ORDER BY id DESC LIMIT 10;"
```

## Architecture

**Pipeline:** annotated PGN (`.pgn.zst` with `%eval`) → upstream generator → MySQL `puzzle` → upstream tagger → MySQL `puzzle_theme` → HTTP API → clients

### Batch worker
- `src/tactician/batch.py` — Orchestrator. Sets up sys.path, monkey-patches upstream's `Server` class with `MySQLServer`, runs generator then tagger.
- `src/tactician/adapters/mysql_writer.py` — `MySQLServer` mirrors upstream's `Server` interface (`is_seen`, `set_seen`, `is_seen_pos`, `post`). Drops in via monkey-patching; upstream code is unaware it's writing to MySQL instead of HTTP.
- `src/tactician/adapters/s3_reader.py` — Downloads per-game PGNs from MinIO under `<YYYY>/<MM>/<DD>/` prefix, concatenates them, and emits a single `.pgn.zst` for the generator.
- `src/tactician/adapters/mysql_tagger_io.py` — Reads untagged puzzles from `puzzle`, reconstructs the upstream `Puzzle` dataclass from `fen` + `moves`, writes themes back to `puzzle_theme`.

### HTTP API
- `src/tactician/api.py` — FastAPI app. Endpoints: `/health`, `/themes`, `/puzzles/{id}`, `/puzzles/random?theme=`. Uses sync route handlers (FastAPI auto-threadpools them) — no async/await DB layer.
- `src/tactician/db.py` — `init_pool(cfg)` + `get_db()` FastAPI dependency. Wraps `dbutils.pooled_db.PooledDB` over `pymysql`. Connection released back to pool when the request finishes.
- `src/tactician/adapters/mysql_reader.py` — Read-only SELECT queries used by the API. Kept separate from `mysql_writer` (batch INSERT path) to keep boundaries explicit.

### Shared
- `src/tactician/config.py` — Loads env vars (MySQL, S3, Stockfish path). API also reads this on startup but only uses the MySQL section.

## Key Technical Details

- **Upstream is untouched.** All code in `upstream/` is vendored verbatim from lichess-puzzler at commit `c188837`. To update, see `upstream/UPSTREAM.md`. Do **not** edit files under `upstream/`.
- **Module collision workaround.** Both `upstream/generator/model.py` and `upstream/tagger/model.py` define different `Puzzle` dataclasses. They cannot coexist on `sys.path`. `batch.py:_use_upstream()` swaps the active path per stage (generator vs tagger) and clears cached modules in between.
- **Magic eval values.** Upstream signals mate puzzles via `cp = 999999998` / `999999999` instead of NULL. We persist these as-is (not NULLs) to keep upstream behavior intact. Aggregate queries (`AVG(cp)` etc.) need to filter `cp < 999999000`.
- **MySQL collation.** The `fen` column uses `utf8mb4_bin` because FEN is case-sensitive (`K` = white king, `k` = black king). The default `utf8mb4_0900_ai_ci` would silently treat them as equal.
- **MinIO is platform-level, not tactician's.** MinIO is defined in the `infra` repo's unified compose and shared with sibling services (the producer is a separate analysis service — `deep-thought`). Tactician is a pure consumer. Don't expand tactician's S3 surface area or treat the bucket layout as something we own.
- **Stockfish.** Generator invokes Stockfish via UCI subprocess (`chess.engine.SimpleEngine.popen_uci`). Path is configured via `STOCKFISH_PATH` env var. The batch container builds Stockfish 18 from source (Dockerfile stage 1) so analysis is reproducible across machines.
- **Batch container.** `cd ../infra/compose && docker compose run --rm tactician-batch ...` is the canonical entrypoint. Service is `profiles: [batch]`-gated in the infra compose so it does not auto-start. Infra passes container hostnames (`MYSQL_HOST=tactician-mysql`, `S3_ENDPOINT_URL=http://minio:9000`) and the bundled Stockfish path as env vars, overriding `.env`. Mount ad-hoc PGN dumps via `LICHESS_DUMP_DIR=<host-dir> docker compose -f ../infra/compose/docker-compose.yml run --rm tactician-batch ...` — the dir lands at `/mnt/lichess` read-only inside the container.
- **API container.** Long-running, port 8000, no profile (auto-starts with infra `docker compose up -d`). Reuses the batch image; entrypoint is `uvicorn tactician.api:app --host 0.0.0.0 --port 8000`. Same env vars as batch (config requires all keys; S3/Stockfish are stubbed for the api).
- **API stack choices.** FastAPI + uvicorn + Pydantic. DB access is sync `pymysql` via `DBUtils.PooledDB` (init in lifespan, dependency-injected per request). No ORM (raw SQL, mirrors the "plain SQL migrations" decision). No async DB driver — sync routes are fine for MVP load and easier to debug; switch to `asyncmy`/`aiomysql` only if measurement shows it's needed.
- **Route order matters.** `/puzzles/random` MUST be declared before `/puzzles/{puzzle_id}` in `api.py`. Otherwise FastAPI matches "random" against `{puzzle_id}` and returns 422.
- **camelCase JSON via alias generator.** `Puzzle` Pydantic model uses `model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)` so Python snake_case fields (`game_id`) serialize as camelCase (`gameId`). DB / SQL / adapter layers stay snake_case throughout — conversion happens once at the response boundary.
- **API doesn't expose `cp` / `mate`.** The internal magic-cp values are filtered out of the response shape; mate puzzles are recognizable from theme strings (`mateIn1`, `mateIn3`, ...). Don't add `cp` to the `Puzzle` model unless a real client requirement appears.
- **Metrics.** Two surfaces: (1) API exposes `/metrics` via `prometheus-fastapi-instrumentator` — standard HTTP histograms plus custom counters/gauges defined in `src/tactician/metrics.py` (puzzles served by endpoint/theme, 404s, DB pool in-use). `/health` and `/metrics` are excluded from HTTP tracking to cut probe noise. (2) Batch is a one-shot job — Prometheus pull doesn't fit, so `src/tactician/batch_metrics.py` accumulates run/stage gauges and counters in a dedicated `CollectorRegistry` and pushes the registry to a pushgateway in main's `finally`. `PUSHGATEWAY_URL` env var is optional; empty/unset disables push silently. Push failures log a warning but never break the batch.
- **Migrations.** Apply in filename order (`migrations/*.sql`). Currently `001_init.sql` (puzzle + puzzle_theme), `002_add_difficulty.sql` (adds `difficulty INT NOT NULL DEFAULT 0` to puzzle), and `003_unique_game_ply.sql` (adds `UNIQUE (game_id, ply)` to enforce dedup at the schema level — `is_seen` only skips whole games and races on re-runs).
- **`pymysql[rsa]` extras.** MySQL 8.x uses `caching_sha2_password` by default, which requires `cryptography`. The `[rsa]` extras pull it in. Don't strip the brackets.
- **Tier filter is aggressive.** Most low-rated bullet games are filtered before Stockfish even runs. Expect ~10–20% of input games to reach analysis, and ~3–5% of those to yield puzzles.
- **`--file` bypasses S3.** Useful for replay testing on Lichess monthly dumps. The upstream generator natively reads `.zst`, so no decompression needed.
- **`--max-games N`.** Truncates the input to the first N games via PGN-level scan (counts `[Event ` headers). Implemented in `_truncate_to_games`.
- **Commit messages.** Single-line conventional commits (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`). No body — ever. Pack the why into the subject or omit it. English. `Co-Authored-By` footer for Claude commits.
- **Branch workflow.** Work on `dev`, merge to `main` only at deployment.
- **License.** AGPL-3.0-or-later (forced by lichess-puzzler vendoring + python-chess GPL dependency).
