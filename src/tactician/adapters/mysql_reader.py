"""Read-side queries used by the API. Kept separate from `mysql_writer`
(batch INSERT path) and `mysql_tagger_io` (tagger read+write) because the
SELECT shapes here exist solely to serve user-facing endpoints.
"""
from pymysql.connections import Connection
from pymysql.cursors import DictCursor


def list_themes(conn: Connection) -> list[dict]:
    with conn.cursor(DictCursor) as cur:
        cur.execute(
            "SELECT t.theme AS name, COUNT(*) AS count "
            "FROM puzzle_theme t "
            "JOIN puzzle p ON p.id = t.puzzle_id AND p.is_hidden = 0 "
            "GROUP BY t.theme "
            "ORDER BY count DESC, t.theme ASC"
        )
        return list(cur.fetchall())


_PUZZLE_COLS = "p.id, p.game_id, p.fen, p.moves, p.difficulty"


def get_puzzle(conn: Connection, puzzle_id: int) -> dict | None:
    """Return puzzle row + themes list, or None if missing/hidden."""
    with conn.cursor(DictCursor) as cur:
        cur.execute(
            f"SELECT {_PUZZLE_COLS} FROM puzzle p "
            "WHERE p.id = %s AND p.is_hidden = 0",
            (puzzle_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _hydrate(cur, row)


def random_puzzle(conn: Connection, theme: str | None) -> dict | None:
    """Return one random non-hidden puzzle, optionally constrained to a theme.

    `ORDER BY RAND()` is O(n); fine for the puzzle volumes we expect at MVP.
    Swap for an indexed offset trick if the table grows past ~100k rows.
    """
    with conn.cursor(DictCursor) as cur:
        if theme is None:
            cur.execute(
                f"SELECT {_PUZZLE_COLS} FROM puzzle p "
                "WHERE p.is_hidden = 0 ORDER BY RAND() LIMIT 1"
            )
        else:
            cur.execute(
                f"SELECT {_PUZZLE_COLS} FROM puzzle p "
                "JOIN puzzle_theme t ON t.puzzle_id = p.id "
                "WHERE p.is_hidden = 0 AND t.theme = %s "
                "ORDER BY RAND() LIMIT 1",
                (theme,),
            )
        row = cur.fetchone()
        if row is None:
            return None
        return _hydrate(cur, row)


def _hydrate(cur, row: dict) -> dict:
    """Split the space-separated moves string into a list and attach themes."""
    row["moves"] = row["moves"].split()
    cur.execute(
        "SELECT theme FROM puzzle_theme WHERE puzzle_id = %s ORDER BY theme",
        (row["id"],),
    )
    row["themes"] = [r["theme"] for r in cur.fetchall()]
    return row
