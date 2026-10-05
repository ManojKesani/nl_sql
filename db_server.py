# db_server.py
import sqlite3

import anyio
from mcp.server.mcpserver import MCPServer

DB_FILE = "longlist.db"

mcp = MCPServer("longlist-db")


def run_query(sql: str, limit: int = 100) -> dict:
    s = sql.strip().rstrip(";").strip()
    if not s.lower().startswith(("select", "with")) or ";" in s:
        raise ValueError("Only a single SELECT/WITH statement is allowed.")
    conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    try:
        cur = conn.execute(s)
        rows = cur.fetchmany(limit)
        return {"columns": [c[0] for c in cur.description], "rows": rows}
    finally:
        conn.close()


@mcp.tool()
def query_database(sql: str) -> str:
    """Run a read-only SQLite SELECT on the books database.
    Returns columns and up to 20 rows, or an ERROR you should use to fix the query."""
    try:
        r = run_query(sql, limit=20)
        return f"columns={r['columns']} rows={r['rows']}"
    except Exception as e:
        return f"ERROR: {e}"


if __name__ == "__main__":
    anyio.run(lambda: mcp.run_streamable_http_async(host="0.0.0.0", port=8001))
