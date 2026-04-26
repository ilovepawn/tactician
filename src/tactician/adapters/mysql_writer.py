"""MySQL adapter that mirrors the upstream Server interface.

Drop-in replacement for upstream/generator/server.py's Server class.
Generator code calls server.is_seen(game_id) and server.post(game_id, puzzle)
without knowing whether the backend is HTTP+MongoDB (Lichess) or MySQL (us).
"""
import logging
from typing import Any

import pymysql

from tactician.config import MySQLConfig


class MySQLServer:
    def __init__(self, logger: logging.Logger, mysql_config: MySQLConfig, version: int) -> None:
        self.logger = logger
        self.version = version
        self.conn = pymysql.connect(
            host=mysql_config.host,
            port=mysql_config.port,
            user=mysql_config.user,
            password=mysql_config.password,
            database=mysql_config.database,
            autocommit=True,
        )

    def is_seen(self, id: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM puzzle WHERE game_id = %s LIMIT 1", (id,))
            return cur.fetchone() is not None

    def set_seen(self, game: Any) -> None:
        # No-op: INSERT into puzzle table records the game implicitly.
        pass

    def is_seen_pos(self, node: Any) -> bool:
        # Position-level dedup not implemented; return False to allow processing.
        return False

    def post(self, game_id: str, puzzle: Any) -> None:
        parent = puzzle.node.parent
        assert parent
        fen = parent.board().fen()
        ply = parent.ply()
        moves = " ".join([puzzle.node.uci()] + [m.uci() for m in puzzle.moves])
        cp = puzzle.cp

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO puzzle
                        (game_id, fen, ply, moves, cp, generator_version)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (game_id, fen, ply, moves, cp, self.version),
                )
                puzzle_id = cur.lastrowid
                self.logger.info(f"inserted puzzle id={puzzle_id} game={game_id} ply={ply}")
        except Exception as e:
            self.logger.error(f"Failed to insert puzzle for game {game_id}: {e}")

    def close(self) -> None:
        self.conn.close()
