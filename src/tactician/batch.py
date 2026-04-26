"""Daily batch entry point.

Wires upstream lichess-puzzler (generator + tagger) into our MySQL/S3 stack
without modifying upstream code. The integration approach is sys.path setup
+ monkey-patching the upstream `Server` class with our MySQL-backed adapter.

Usage:
    # Production: pull yesterday's annotated PGNs from S3 and run.
    uv run python -m tactician.batch --date 2026-04-26

    # Ad-hoc: run on a local PGN file (skips S3).
    uv run python -m tactician.batch --file /path/to/games.pgn.zst

    # Test: limit to first N games (useful with --file).
    uv run python -m tactician.batch --file games.pgn.zst --max-games 10
"""
import argparse
import logging
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import zstandard

# Upstream package paths. They are NOT added to sys.path at import time because
# both subdirs contain a top-level `model.py` and would shadow each other.
# `_use_upstream()` swaps the active path per stage (generator vs tagger).
ROOT = Path(__file__).resolve().parent.parent.parent
GENERATOR_DIR = ROOT / "upstream" / "generator"
TAGGER_DIR = ROOT / "upstream" / "tagger"
_UPSTREAM_MODULE_NAMES = ("model", "util", "server", "generator", "tb", "cook", "zugzwang")

from tactician.adapters import mysql_tagger_io  # noqa: E402
from tactician.adapters.mysql_writer import MySQLServer  # noqa: E402
from tactician.adapters.s3_reader import download_pgn_for_date  # noqa: E402
from tactician.config import load_config  # noqa: E402

logger = logging.getLogger("tactician.batch")


def _use_upstream(target_dir: Path) -> None:
    """Switch sys.path to point at one upstream subdir and clear cached modules."""
    for d in (str(GENERATOR_DIR), str(TAGGER_DIR)):
        while d in sys.path:
            sys.path.remove(d)
    sys.path.insert(0, str(target_dir))
    for name in _UPSTREAM_MODULE_NAMES:
        sys.modules.pop(name, None)


def _truncate_to_games(input_path: Path, max_games: int) -> Path:
    """Write first N games of input PGN (.pgn or .pgn.zst) to a new .pgn.zst file."""
    if str(input_path).endswith(".zst"):
        src = zstandard.open(input_path, "rt")
    else:
        src = open(input_path)

    out_file = Path(tempfile.mktemp(suffix=".pgn.zst"))
    cctx = zstandard.ZstdCompressor()
    games_seen = 0
    try:
        with out_file.open("wb") as raw, cctx.stream_writer(raw) as compressor:
            for line in src:
                if line.startswith("[Event "):
                    games_seen += 1
                    if games_seen > max_games:
                        break
                compressor.write(line.encode())
    finally:
        src.close()
    logger.info(f"truncated input to first {min(games_seen, max_games)} games at {out_file}")
    return out_file


def run_generator(pgn_path: Path, cfg) -> None:
    """Run upstream generator with our MySQL server plugged in."""
    _use_upstream(GENERATOR_DIR)
    import generator as upstream_generator  # type: ignore

    version = upstream_generator.version

    def _server_factory(_logger, _url, _token, _version):
        return MySQLServer(logger, cfg.mysql, version)

    # Monkey-patch the upstream Server class to use our MySQL adapter.
    upstream_generator.Server = _server_factory  # type: ignore

    sys.argv = [
        "generator",
        "--file", str(pgn_path),
        "--engine", cfg.stockfish.path,
        "--threads", str(cfg.stockfish.threads),
        "--url", "",
        "--parts", "1",
        "--part", "1",
    ]
    upstream_generator.main()


def run_tagger(cfg) -> None:
    """Run upstream tagger logic against our MySQL puzzles."""
    _use_upstream(TAGGER_DIR)
    import cook  # type: ignore  (from upstream/tagger)

    count = 0
    for puzzle in mysql_tagger_io.iter_untagged_puzzles(logger, cfg.mysql):
        themes = cook.cook(puzzle)
        mysql_tagger_io.insert_themes(logger, cfg.mysql, int(puzzle.id), themes)
        count += 1
    logger.info(f"tagged {count} puzzles")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tactician.batch")
    src = parser.add_mutually_exclusive_group()
    src.add_argument(
        "--date",
        default=None,
        help="target date (YYYY-MM-DD) to pull from S3. Defaults to yesterday.",
    )
    src.add_argument(
        "--file",
        default=None,
        help="path to a local PGN file (.pgn or .pgn.zst). Bypasses S3.",
    )
    parser.add_argument(
        "--max-games",
        type=int,
        default=None,
        help="process only the first N games (useful for testing).",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    args = parse_args()
    cfg = load_config()

    cleanup_paths: list[Path] = []
    try:
        if args.file:
            pgn_path = Path(args.file)
            if not pgn_path.exists():
                logger.error(f"file not found: {pgn_path}")
                return
            logger.info(f"using local file: {pgn_path}")
        else:
            target = (
                datetime.strptime(args.date, "%Y-%m-%d").date()
                if args.date
                else date.today() - timedelta(days=1)
            )
            logger.info(f"running batch for {target}")
            pgn_path = download_pgn_for_date(logger, cfg.s3, target)
            cleanup_paths.append(pgn_path)
            if pgn_path.stat().st_size == 0:
                logger.warning(f"no games found for {target}, skipping")
                return

        if args.max_games:
            pgn_path = _truncate_to_games(pgn_path, args.max_games)
            cleanup_paths.append(pgn_path)

        run_generator(pgn_path, cfg)
        run_tagger(cfg)
        logger.info("batch complete")
    finally:
        for p in cleanup_paths:
            p.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
