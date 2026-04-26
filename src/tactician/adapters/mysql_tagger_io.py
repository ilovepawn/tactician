"""MySQL adapter for tagger I/O.

The upstream tagger reads puzzles from MongoDB and writes back tag tokens
into puzzle2_round. This adapter replaces both ends with MySQL access:
- read untagged puzzles from `puzzle` table
- write resulting themes into `puzzle_theme` table

Pure tagging logic (cook.cook(), zugzwang()) lives in upstream/ and uses
the Puzzle dataclass — we reconstruct it here from MySQL rows.
"""
import logging
from collections.abc import Iterator
from typing import Any

import pymysql
from chess import Board, Move
from chess.pgn import Game, GameNode

from tactician.config import MySQLConfig


def _connect(mysql_config: MySQLConfig) -> pymysql.Connection:
    return pymysql.connect(
        host=mysql_config.host,
        port=mysql_config.port,
        user=mysql_config.user,
        password=mysql_config.password,
        database=mysql_config.database,
        autocommit=False,
    )


def _row_to_puzzle(row: dict[str, Any]) -> Any:
    """Reconstruct upstream Puzzle dataclass from a MySQL row."""
    from model import Puzzle  # imported here so upstream sys.path is set first

    board = Board(row["fen"])
    node: GameNode = Game.from_board(board)
    for uci in row["moves"].split():
        move = Move.from_uci(uci)
        node = node.add_main_variation(move)
    return Puzzle(str(row["id"]), node.game(), int(row["cp"]))


def iter_untagged_puzzles(
    logger: logging.Logger, mysql_config: MySQLConfig
) -> Iterator[Any]:
    """Yield puzzles that have no entries in puzzle_theme yet."""
    conn = _connect(mysql_config)
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(
                """
                SELECT p.id, p.fen, p.moves, p.cp
                FROM puzzle p
                LEFT JOIN puzzle_theme t ON t.puzzle_id = p.id
                WHERE t.puzzle_id IS NULL AND p.is_hidden = FALSE
                """
            )
            rows = cur.fetchall()
        logger.info(f"found {len(rows)} untagged puzzles")
        for row in rows:
            yield _row_to_puzzle(row)
    finally:
        conn.close()


def insert_themes(
    logger: logging.Logger,
    mysql_config: MySQLConfig,
    puzzle_id: int,
    themes: list[str],
) -> None:
    if not themes:
        return
    conn = _connect(mysql_config)
    try:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT IGNORE INTO puzzle_theme (puzzle_id, theme) VALUES (%s, %s)",
                [(puzzle_id, t) for t in themes],
            )
        conn.commit()
        logger.info(f"tagged puzzle id={puzzle_id} themes={themes}")
    finally:
        conn.close()
