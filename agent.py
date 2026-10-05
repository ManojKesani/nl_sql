import json
import sqlite3
from pprint import pprint
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain.tools import tool
from pydantic import BaseModel, Field

load_dotenv()

DB_FILE = "longlist.db"


# ---------- request / response shapes ----------
class Question(BaseModel):
    question: str
    model: Optional[str] = None  # a nickname from models.json; empty = use "active"


class SqlBody(BaseModel):
    sql: str


class SQLResponse(BaseModel):
    thought_process: str = Field(
        description="Brief reasoning: which tables, joins, filters, aggregations, and any assumptions."
    )
    sql: str = Field(
        description="The final SQLite query, exactly as it was run with query_database. "
                    "Empty string only if the schema cannot answer the question."
    )
    answer: str = Field(
        description="The direct answer to the user's question in plain English, based ONLY on the rows "
                    "returned by query_database. Include the key values (names, counts, numbers). "
                    "If the question cannot be answered, explain why."
    )


# ---------- config files ----------
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


sys_data = load_json("sys_prompt.json")
system_content = json.dumps(sys_data, indent=2) if isinstance(sys_data, dict) else str(sys_data)
MODEL_CONFIG = load_json("models.json")


# ---------- the one place SQL is executed ----------
def run_query(sql: str, limit: int = 100) -> dict:
    s = sql.strip().rstrip(";").strip()
    if not s.lower().startswith(("select", "with")) or ";" in s:
        raise ValueError("Only a single SELECT/WITH statement is allowed.")
    conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)  # ro = read-only
    try:
        cur = conn.execute(s)
        rows = cur.fetchmany(limit)
        return {"columns": [c[0] for c in cur.description], "rows": rows}
    finally:
        conn.close()


@tool
def query_database(sql: str) -> str:
    """Run a read-only SQLite SELECT on the books database.
    Returns columns and up to 20 rows, or an ERROR you should use to fix the query."""
    try:
        r = run_query(sql, limit=20)
        return f"columns={r['columns']} rows={r['rows']}"
    except Exception as e:
        return f"ERROR: {e}"


# ---------- model providers ----------
# Imports happen inside each function, so a provider you don't use
# never needs to be installed.
def _groq(**cfg):
    from langchain_groq import ChatGroq
    return ChatGroq(**cfg)


def _nvidia(**cfg):
    from langchain_nvidia_ai_endpoints import ChatNVIDIA
    return ChatNVIDIA(**cfg)


def _openrouter(**cfg):
    from langchain_openrouter import ChatOpenRouter
    return ChatOpenRouter(**cfg)


PROVIDERS = {"groq": _groq, "nvidia": _nvidia, "openrouter": _openrouter}

_agents = {}  # cache: one agent per model nickname


def get_agent(name: str):
    models = MODEL_CONFIG["models"]
    if name not in models:
        raise HTTPException(404, f"Unknown model '{name}'. Options: {list(models)}")
    if name not in _agents:
        cfg = dict(models[name])
        provider = cfg.pop("provider", None)
        if provider not in PROVIDERS:
            raise HTTPException(400, f"Unknown provider '{provider}'. Options: {list(PROVIDERS)}")
        try:
            llm = PROVIDERS[provider](**cfg)
        except Exception as e:
            raise HTTPException(500, f"Could not build '{name}': {type(e).__name__}: {e}")
        _agents[name] = create_agent(
            model=llm,
            tools=[query_database],
            response_format=ToolStrategy(SQLResponse),
        )
    return _agents[name]


# ---------- API ----------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/models")
def list_models():
    return {
        "active": MODEL_CONFIG["active"],
        "models": {k: {"provider": v["provider"], "model": v["model"]}
                   for k, v in MODEL_CONFIG["models"].items()},
    }


@app.post("/ask")
def ask(body: Question):
    name = body.model or MODEL_CONFIG["active"]
    agent = get_agent(name)
    try:
        result = agent.invoke({"messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": body.question},
        ]})
    except Exception as e:
        raise HTTPException(502, f"{name}: {type(e).__name__}: {e}")

    for m in result["messages"][1:]:  # [1:] skips the big system message
        print(type(m).__name__, getattr(m, "tool_calls", ""), str(m.content)[:200])

    answer = result["structured_response"].model_dump()
    answer["tool_calls"] = sum(1 for m in result["messages"] if getattr(m, "name", None) == "query_database")  # <-- NEW
    answer["model"] = name
    pprint(answer)
    return answer


@app.post("/sql")
def run_sql(body: SqlBody):
    try:
        return run_query(body.sql)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))