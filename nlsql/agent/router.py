"""Pick a db_id. One DB: no LLM call. Several: a small model chooses from the descriptions."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .. import registry
from ..llm.factory import build_model
from ..llm.structured import structured_call


class Route(BaseModel):
    db_id: str
    reason: str = Field(description="One short sentence.")


SYSTEM = """Pick the single database best suited to the user's question.
Answer with one db_id from the list, exactly as written.

DATABASES:
{dbs}"""


def route(question: str, model_nick: str | None = None) -> str:
    dbs = registry.describe_all()
    if not dbs:
        raise RuntimeError("No databases registered. Run the ingest pipeline first.")
    if len(dbs) == 1:
        return next(iter(dbs))
    listing = "\n".join(f"- {k}: {v or '(no description)'}" for k, v in dbs.items())
    r = structured_call(build_model(model_nick), Route, SYSTEM.format(dbs=listing), question)
    if r.db_id not in dbs:
        raise ValueError(f"Router returned unknown db_id '{r.db_id}'. Options: {list(dbs)}")
    return r.db_id