import os
import anyio
from mcp.server.mcpserver import MCPServer

from nlsql.config import settings
from nlsql.db.executor import run_query

DB_FILE = os.getenv("DB_FILE", "longlist.db")  # becomes per-db_id once the registry exists

mcp = MCPServer("longlist-db")


@mcp.tool()
def query_database(sql: str) -> str:
    """Run a read-only SQLite SELECT on the books database.
    Returns columns and up to 20 rows, or an ERROR you should use to fix the query."""
    try:
        return run_query(DB_FILE, sql, limit=settings.tool_row_limit,
                         timeout_s=settings.query_timeout_s).to_text()
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


if __name__ == "__main__":
    anyio.run(lambda: mcp.run_streamable_http_async(host="0.0.0.0", port=8001))