"""One agent per (db_id, model). The tool is bound to the db, so the LLM can't pick another one."""
from __future__ import annotations

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain.tools import tool

from .. import registry
from ..config import settings
from ..db.executor import run_query
from ..ingest import promptgen
from ..llm.factory import build_middleware, build_model
from .schema import SQLResponse


def make_tool(db_path: str):
    @tool
    def query_database(sql: str) -> str:
        """Run a read-only SQLite SELECT. Returns columns and up to 20 rows, or an ERROR to fix."""
        try:
            return run_query(db_path, sql, limit=settings.tool_row_limit,
                             timeout_s=settings.query_timeout_s).to_text()
        except Exception as e:
            return f"ERROR: {type(e).__name__}: {e}"
    return query_database


def build_agent(db_id: str, model_nick: str, fallbacks: list[str] | None = None, run_limit: int = 8):
    version, prompt = promptgen.load_latest(db_id)
    agent = create_agent(
        model=build_model(model_nick),
        tools=[make_tool(registry.get(db_id)["path"])],
        system_prompt=prompt,
        response_format=ToolStrategy(SQLResponse),
        middleware=build_middleware(fallbacks, run_limit=run_limit),
    )
    return agent, version