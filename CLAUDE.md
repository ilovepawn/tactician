# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tactician is the puzzle service for the ilovepawn chess platform. It mines tactical puzzles from platform games (daily batch) and will serve them to users via API.

The puzzle detection and theme classification logic is vendored from [Lichess's puzzle generator](https://github.com/ornicar/lichess-puzzler) under AGPL-3.0 and used **without modification**. Our code lives in `src/tactician/` and is composed of thin adapters that plug the vendored code into our MySQL/S3 stack via runtime monkey-patching.

## Commands

```bash
# Start MySQL + MinIO
docker compose up -d

# Apply schema (idempotent on fresh DB)
docker exec -i tactician-db-1 mysql -u tactician -ptactician tactician < migrations/001_init.sql

# Build the batch worker image (Python + Stockfish 18 bundled)
docker compose build batch

# Daily batch (production mode — pulls from S3)
docker compose run --rm batch --date 2026-04-26

# Ad-hoc: run on a local PGN file mounted from the host via LICHESS_DUMP_DIR
LICHESS_DUMP_DIR=/Volumes/bobo-01 \
  docker compose run --rm batch \
    --file /mnt/lichess/lichess_db_standard_rated_2026-03_eval.pgn.zst \
    --max-games 200

# Host-mode (developer convenience — needs uv + host Stockfish)
uv sync
uv run python -m tactician.batch --file path/to/games.pgn.zst --max-games 100

# Inspect generated puzzles
docker exec tactician-db-1 mysql -u tactician -ptactician tactician \
  -e "SELECT id, game_id, ply, cp FROM puzzle ORDER BY id DESC LIMIT 10;"
```

## Architecture

**Pipeline:** annotated PGN (`.pgn.zst` with `%eval`) → upstream generator → MySQL `puzzle` → upstream tagger → MySQL `puzzle_theme`

- `src/tactician/batch.py` — Orchestrator. Sets up sys.path, monkey-patches upstream's `Server` class with `MySQLServer`, runs generator then tagger.
- `src/tactician/adapters/mysql_writer.py` — `MySQLServer` mirrors upstream's `Server` interface (`is_seen`, `set_seen`, `is_seen_pos`, `post`). Drops in via monkey-patching; upstream code is unaware it's writing to MySQL instead of HTTP.
- `src/tactician/adapters/s3_reader.py` — Downloads per-game PGNs from MinIO under `<YYYY>/<MM>/<DD>/` prefix, concatenates them, and emits a single `.pgn.zst` for the generator.
- `src/tactician/adapters/mysql_tagger_io.py` — Reads untagged puzzles from `puzzle`, reconstructs the upstream `Puzzle` dataclass from `fen` + `moves`, writes themes back to `puzzle_theme`.
- `src/tactician/config.py` — Loads env vars (MySQL, S3, Stockfish path).

## Key Technical Details

- **Upstream is untouched.** All code in `upstream/` is vendored verbatim from lichess-puzzler at commit `c188837`. To update, see `upstream/UPSTREAM.md`. Do **not** edit files under `upstream/`.
- **Module collision workaround.** Both `upstream/generator/model.py` and `upstream/tagger/model.py` define different `Puzzle` dataclasses. They cannot coexist on `sys.path`. `batch.py:_use_upstream()` swaps the active path per stage (generator vs tagger) and clears cached modules in between.
- **Magic eval values.** Upstream signals mate puzzles via `cp = 999999998` / `999999999` instead of NULL. We persist these as-is (not NULLs) to keep upstream behavior intact. Aggregate queries (`AVG(cp)` etc.) need to filter `cp < 999999000`.
- **MySQL collation.** The `fen` column uses `utf8mb4_bin` because FEN is case-sensitive (`K` = white king, `k` = black king). The default `utf8mb4_0900_ai_ci` would silently treat them as equal.
- **Stockfish.** Generator invokes Stockfish via UCI subprocess (`chess.engine.SimpleEngine.popen_uci`). Path is configured via `STOCKFISH_PATH` env var. The batch container builds Stockfish 18 from source (Dockerfile stage 1) so analysis is reproducible across machines; host-mode runs use whatever `STOCKFISH_PATH` points at and should match (currently Stockfish 18).
- **Batch container.** `docker compose run --rm batch ...` is the canonical entrypoint. The service uses `profiles: [batch]` so it does not auto-start with `docker compose up -d`. Compose passes container hostnames (`MYSQL_HOST=db`, `S3_ENDPOINT_URL=http://s3:9000`) and the bundled Stockfish path as env vars, overriding `.env`. Mount ad-hoc PGN dumps via `LICHESS_DUMP_DIR=<host-dir> docker compose run ...` — the dir lands at `/mnt/lichess` read-only inside the container.
- **`pymysql[rsa]` extras.** MySQL 8.x uses `caching_sha2_password` by default, which requires `cryptography`. The `[rsa]` extras pull it in. Don't strip the brackets.
- **Tier filter is aggressive.** Most low-rated bullet games are filtered before Stockfish even runs. Expect ~10–20% of input games to reach analysis, and ~3–5% of those to yield puzzles.
- **`--file` bypasses S3.** Useful for replay testing on Lichess monthly dumps. The upstream generator natively reads `.zst`, so no decompression needed.
- **`--max-games N`.** Truncates the input to the first N games via PGN-level scan (counts `[Event ` headers). Implemented in `_truncate_to_games`.
- **Commit messages.** Single-line conventional commits (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`). Body only when the *why* is non-obvious. English. `Co-Authored-By` footer for Claude commits.
- **Branch workflow.** Work on `dev`, merge to `main` only at deployment.
- **License.** AGPL-3.0-or-later (forced by lichess-puzzler vendoring + python-chess GPL dependency).
