"""Assemble the versioned system prompt: rules + schema card + docs + few-shot from golden."""
from __future__ import annotations

from itertools import zip_longest

from .. import registry
from . import enrich, golden
from .profile import load_card

RULES = """You answer questions about a SQLite database by writing SQL and running it with the query_database tool.

Rules:
- Use only the tables and columns listed below. Never invent columns.
- Only SELECT/WITH queries, SQLite dialect.
- Always run your SQL with query_database before answering. If it returns ERROR, fix the query and retry.
- The tool returns at most 20 rows, so prefer aggregates and LIMIT over listing everything.
- Match text values exactly as shown in the schema hints; use LIKE for partial names.
- Base the answer ONLY on returned rows. If the schema cannot answer the question, say so."""


def pick_examples(items: list[dict], k: int = 6) -> list[dict]:
    """Round-robin across categories so examples are diverse."""
    by_cat: dict[str, list[dict]] = {}
    for it in items:
        by_cat.setdefault(it["category"], []).append(it)
    picked = []
    for group in zip_longest(*by_cat.values()):
        picked += [g for g in group if g]
        if len(picked) >= k:
            break
    return picked[:k]


def _next_version(d) -> int:
    nums = [int(p.stem.split(".v")[1]) for p in d.glob("prompt.v*.md") if p.stem.split(".v")[1].isdigit()]
    return max(nums, default=0) + 1


def build(db_id: str, k_examples: int = 6) -> tuple[str, str]:
    d = registry.db_dir(db_id)
    parts = [RULES, "## Schema\n" + load_card(db_id)]
    enr = enrich.load(db_id)
    if enr:
        parts.append("## Notes\n" + enrich.render(enr))
    ex = pick_examples(golden.load(db_id, only_agreed=True), k_examples)
    if ex:
        parts.append("## Examples\n" + "\n\n".join(f"Q: {e['question']}\nSQL: {e['sql']}" for e in ex))
    text = "\n\n".join(parts)
    version = f"v{_next_version(d)}"
    (d / f"prompt.{version}.md").write_text(text, encoding="utf-8")
    print(f"[prompt] wrote prompt.{version}.md (~{len(text) // 4} tokens)")
    return version, text


def load_latest(db_id: str) -> tuple[str, str]:
    d = registry.db_dir(db_id)
    files = sorted(d.glob("prompt.v*.md"), key=lambda p: int(p.stem.split(".v")[1]))
    if not files:
        raise FileNotFoundError(f"No prompt for '{db_id}'. Run the ingest pipeline.")
    return files[-1].stem.split(".")[1], files[-1].read_text(encoding="utf-8")