"""Big model writes descriptions, join paths and quirks. REVIEW data/<db_id>/enrichment.json before trusting it."""
from __future__ import annotations

import json

from pydantic import BaseModel, Field

from .. import registry
from ..llm.factory import build_model
from ..llm.structured import structured_call
from .profile import load_card


class ColumnDoc(BaseModel):
    name: str
    description: str


class TableDoc(BaseModel):
    name: str
    description: str
    columns: list[ColumnDoc] = Field(default_factory=list)


class Enrichment(BaseModel):
    db_description: str = Field(description="2-3 sentences: what this database contains and is good for.")
    tables: list[TableDoc]
    join_paths: list[str] = Field(description="Common joins, e.g. 'books.publisher_id = publishers.id'.")
    quirks: list[str] = Field(description="Data gotchas grounded in the profile: name variants, units, nulls, derived columns.")


SYSTEM = """You document a SQLite database for a text-to-SQL assistant.
Use ONLY facts visible in the schema profile below. Do not invent columns, tables or values.
Be concise. Flag redundancies (e.g. a column derivable from another) and ambiguous columns.

SCHEMA PROFILE:
{card}"""


def run(db_id: str, model_nick: str) -> Enrichment:
    llm = build_model(model_nick)
    enr = structured_call(llm, Enrichment, SYSTEM.format(card=load_card(db_id)),
                          "Produce the documentation.")
    out = registry.db_dir(db_id) / "enrichment.json"
    out.write_text(enr.model_dump_json(indent=2), encoding="utf-8")
    return enr


def load(db_id: str) -> Enrichment | None:
    p = registry.db_dir(db_id) / "enrichment.json"
    return Enrichment.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else None


def render(enr: Enrichment) -> str:
    lines = [enr.db_description, ""]
    for t in enr.tables:
        lines.append(f"- {t.name}: {t.description}")
        lines += [f"    - {c.name}: {c.description}" for c in t.columns]
    if enr.join_paths:
        lines += ["", "Join paths:"] + [f"- {j}" for j in enr.join_paths]
    if enr.quirks:
        lines += ["", "Notes:"] + [f"- {q}" for q in enr.quirks]
    return "\n".join(lines)