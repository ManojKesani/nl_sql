"""The ONE place SQL is executed. Shared by the MCP server, /sql, ingest, and evals.

Defense in depth:
  1. sqlglot parse: exactly one statement, root must be a query, no write/DDL nodes
  2. connection opened mode=ro
  3. sqlite authorizer: only SELECT / READ / FUNCTION / RECURSIVE actions allowed
  4. progress handler: hard wall-clock timeout
  5. row cap (fetch limit+1 to detect truncation)
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


class QueryRejected(ValueError):
    """SQL failed validation (not a read-only single query)."""


class QueryTimeout(RuntimeError):
    """Query exceeded the time budget."""


_FORBIDDEN_NAMES = ("Insert", "Update", "Delete", "Drop", "Create", "Alter",
                    "Command", "Attach", "Pragma", "TruncateTable", "Merge")
_FORBIDDEN = tuple(getattr(exp, n) for n in _FORBIDDEN_NAMES if hasattr(exp, n))

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}


def _authorizer(action, *_args):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def validate_sql(sql: str) -> str:
    """Return cleaned SQL (no trailing semicolon) or raise QueryRejected."""
    s = (sql or "").strip()
    if not s:
        raise QueryRejected("Empty SQL.")
    try:
        stmts = [t for t in sqlglot.parse(s, read="sqlite") if t is not None]
    except ParseError as e:
        raise QueryRejected(f"SQL parse error: {e}") from e
    if len(stmts) != 1:
        raise QueryRejected("Only a single statement is allowed.")
    tree = stmts[0]
    if not isinstance(tree, exp.Query):  # Select, Union, etc. (CTEs parse as Select)
        raise QueryRejected("Only SELECT / WITH queries are allowed.")
    if _FORBIDDEN and tree.find(*_FORBIDDEN):
        raise QueryRejected("Write or DDL operations are not allowed.")
    return s.rstrip(";").strip()


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool
    elapsed_ms: float

    def to_dict(self) -> dict:
        return {"columns": self.columns, "rows": [list(r) for r in self.rows],
                "truncated": self.truncated, "elapsed_ms": round(self.elapsed_ms, 1)}

    def to_text(self) -> str:
        note = f" (truncated to {len(self.rows)} rows)" if self.truncated else ""
        return f"columns={self.columns} rows={self.rows}{note}"


def connect_ro(db_path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def run_query(db_path, sql: str, limit: int = 100, timeout_s: float = 5.0) -> QueryResult:
    clean = validate_sql(sql)
    conn = connect_ro(db_path)
    deadline = time.monotonic() + timeout_s
    timed_out = False

    def _progress():
        nonlocal timed_out
        if time.monotonic() > deadline:
            timed_out = True
            return 1  # non-zero aborts the query
        return 0

    start = time.perf_counter()
    try:
        conn.set_authorizer(_authorizer)
        conn.set_progress_handler(_progress, 10_000)  # check every 10k VM steps
        cur = conn.execute(clean)
        fetched = cur.fetchmany(limit + 1)
        cols = [c[0] for c in cur.description] if cur.description else []
        return QueryResult(
            columns=cols,
            rows=fetched[:limit],
            truncated=len(fetched) > limit,
            elapsed_ms=(time.perf_counter() - start) * 1000,
        )
    except sqlite3.OperationalError as e:
        if timed_out:
            raise QueryTimeout(f"Query exceeded {timeout_s}s. Simplify it or add filters.") from e
        raise
    finally:
        conn.close()