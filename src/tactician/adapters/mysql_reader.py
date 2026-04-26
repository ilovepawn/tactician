"""Read-side queries used by the API. Kept separate from `mysql_writer`
(batch INSERT path) and `mysql_tagger_io` (tagger read+write) because the
SELECT shapes here exist solely to serve user-facing endpoints.
"""
from pymysql.connections import Connection
from pymysql.cursors import DictCursor


def list_themes(conn: Connection) -> list[dict]:
    with conn.cursor(DictCursor) as cur:
        cur.execute(
            "SELECT theme AS name, COUNT(*) AS count "
            "FROM puzzle_theme "
            "GROUP BY theme "
            "ORDER BY count DESC, theme ASC"
        )
        return list(cur.fetchall())
