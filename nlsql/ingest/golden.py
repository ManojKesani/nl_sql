"""Generate golden question/SQL pairs with a big model, then validate:
  1. SQL must execute, return rows, and not be truncated
  2. an independent second pass (question only, no SQL shown) must produce the same result set
status = 'agreed' or 'disputed'. Human review still matters: a wrong golden is worse than none."""
from __future__ import annotations

import json
import math

from pydantic import BaseModel

from .. import registry
from ..db.executor import run_query
from ..eval.metrics import results_match
from ..llm.factory import build_model
from ..llm.structured import structured_call
from . import enrich
from .profile import load_card

CATEGORIES = {
    "simple_filter": "single-table filter or lookup",
    "aggregate": "COUNT/SUM/AVG/MIN/MAX over one table",
    "join": "requires joining 2 tables",
    "group_by": "GROUP BY with aggregates, optionally HAVING",
    "top_k": "ranking with ORDER BY ... LIMIT k",
    "multi_join_agg": "3+ table join with aggregation",
    "date_or_range": "date, year or numeric range conditions",
}


class GenItem(BaseModel):
    question: str
    sql: str


class GenBatch(BaseModel):
    items: list[GenItem]


class SqlOnly(BaseModel):
    sql: str


GEN_SYS = """You create evaluation data for a text-to-SQL system over a SQLite database.
Write realistic questions a curious non-technical user would ask, plus correct SQLite SQL.
Rules: SQL must be a single SELECT/WITH; every question needs a deterministic, non-empty answer
with fewer than 100 rows; use ORDER BY when order matters (and tie-breakers for top-k);
use exact text values from the schema hints; vary phrasing and entities.

{context}"""

SOLVE_SYS = """Write one SQLite SELECT/WITH query answering the user's question. Use only the schema below.

{context}"""


def _try(path, sql, cap):
    try:
        return run_query(path, sql, limit=cap, timeout_s=10)
    except Exception:
        return None


def _context(db_id: str) -> str:
    ctx = "SCHEMA:\n" + load_card(db_id)
    enr = enrich.load(db_id)
    return ctx + ("\n\nDOCS:\n" + enrich.render(enr) if enr else "")


def run(db_id: str, model_nick: str, n: int = 40, row_cap: int = 200) -> list[dict]:
    path = registry.get(db_id)["path"]
    llm = build_model(model_nick)
    context = _context(db_id)
    per = math.ceil(n / len(CATEGORIES))
    seen, items, dropped = [], [], 0

    for cat, desc in CATEGORIES.items():
        user = (f"Category: {cat} ({desc}). Write {per} diverse questions.\n"
                f"Already used, avoid similar: {seen[-30:]}")
        batch = structured_call(llm, GenBatch, GEN_SYS.format(context=context), user)
        for it in batch.items:
            seen.append(it.question)
            r = _try(path, it.sql, row_cap)
            if r is None or not r.rows or r.truncated:
                dropped += 1
                continue
            alt = structured_call(llm, SqlOnly, SOLVE_SYS.format(context=context), it.question)
            r2 = _try(path, alt.sql, row_cap)
            agreed = r2 is not None and results_match(r.rows, r2.rows)
            items.append({
                "id": f"{db_id}-{len(items) + 1:03d}",
                "category": cat,
                "question": it.question,
                "sql": it.sql,
                "expected_columns": r.columns,
                "expected_rows": [list(x) for x in r.rows[:50]],
                "n_rows": len(r.rows),
                "status": "agreed" if agreed else "disputed",
                "reviewed": False,
            })
        print(f"[golden] {cat}: kept so far {len(items)}, dropped {dropped}")

    out = registry.db_dir(db_id) / "golden.jsonl"
    out.write_text("\n".join(json.dumps(i, default=str) for i in items), encoding="utf-8")
    agreed_n = sum(i["status"] == "agreed" for i in items)
    print(f"[golden] wrote {len(items)} items ({agreed_n} agreed) -> {out}")
    return items


def load(db_id: str, only_agreed: bool = False) -> list[dict]:
    p = registry.db_dir(db_id) / "golden.jsonl"
    if not p.exists():
        return []
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in rows if r["status"] == "agreed"] if only_agreed else rows