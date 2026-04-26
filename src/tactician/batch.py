"""Daily batch entry point.

Wires upstream lichess-puzzler (generator + tagger) into our MySQL/S3 stack
without modifying upstream code. The integration approach is sys.path setup
+ monkey-patching the upstream `Server` class with our MySQL-backed adapter.

Usage:
    uv run python -m tactician.batch --date 2026-04-26
"""
import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

# Make upstream packages importable.
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "upstream" / "generator"))
sys.path.insert(0, str(ROOT / "upstream" / "tagger"))

from tactician.adapters import mysql_tagger_io  # noqa: E402
from tactician.adapters.mysql_writer import MySQLServer  # noqa: E402
from tactician.adapters.s3_reader import download_pgn_for_date  # noqa: E402
from tactician.config import load_config  # noqa: E402

logger = logging.getLogger("tactician.batch")


def run_generator(pgn_path: Path, cfg) -> None:
    """Run upstream generator with our MySQL server plugged in."""
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
        "--url", "",  # empty disables HTTP, our factory ignores anyway
        "--parts", "1",
        "--part", "1",
    ]
    upstream_generator.main()


def run_tagger(cfg) -> None:
    """Run upstream tagger logic against our MySQL puzzles."""
    import cook  # type: ignore  (from upstream/tagger)

    count = 0
    for puzzle in mysql_tagger_io.iter_untagged_puzzles(logger, cfg.mysql):
        themes = cook.cook(puzzle)
        mysql_tagger_io.insert_themes(logger, cfg.mysql, int(puzzle.id), themes)
        count += 1
    logger.info(f"tagged {count} puzzles")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tactician.batch")
    parser.add_argument(
        "--date",
        default=None,
        help="target date (YYYY-MM-DD). Defaults to yesterday in local time.",
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

    if args.date:
        target = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        from datetime import timedelta
        target = date.today() - timedelta(days=1)

    logger.info(f"running batch for {target}")

    pgn_path = download_pgn_for_date(logger, cfg.s3, target)
    if pgn_path.stat().st_size == 0:
        logger.warning(f"no games found for {target}, skipping")
        pgn_path.unlink(missing_ok=True)
        return

    try:
        run_generator(pgn_path, cfg)
        run_tagger(cfg)
    finally:
        pgn_path.unlink(missing_ok=True)

    logger.info("batch complete")


if __name__ == "__main__":
    main()
