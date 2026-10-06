from __future__ import annotations

import hmac
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import registry
from .agent import service
from .config import settings
from .db.executor import QueryRejected, QueryTimeout, run_query
from .llm.factory import UnknownModel, load_model_config
from .observability import setup_tracing

setup_tracing()
app = FastAPI(title="nl-sql")
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-API-Key"])


def auth(x_api_key: str = Header(default="")):
    if settings.api_key and not hmac.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(401, "Invalid or missing X-API-Key")


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    db_id: Optional[str] = None
    model: Optional[str] = None


class SqlBody(BaseModel):
    db_id: str
    sql: str = Field(max_length=5000)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/dbs", dependencies=[Depends(auth)])
def dbs():
    return {k: {"description": v, **registry.get_config(k)} for k, v in registry.describe_all().items()}


@app.get("/models", dependencies=[Depends(auth)])
def models():
    cfg = load_model_config()
    return {"active": cfg["active"],
            "models": {k: {"provider": v["provider"], "model": v["model"]} for k, v in cfg["models"].items()}}


@app.post("/ask", dependencies=[Depends(auth)])
def ask(body: Question):
    try:
        return service.ask(body.question, body.db_id, body.model)
    except (KeyError, UnknownModel, ValueError) as e:
        raise HTTPException(404 if isinstance(e, (KeyError, UnknownModel)) else 400, str(e))
    except Exception as e:
        raise HTTPException(502, f"{type(e).__name__}: {e}")


@app.post("/sql", dependencies=[Depends(auth)])
def sql(body: SqlBody):
    try:
        path = registry.get(body.db_id)["path"]
        return run_query(path, body.sql, limit=settings.api_row_limit,
                         timeout_s=settings.query_timeout_s).to_dict()
    except KeyError as e:
        raise HTTPException(404, str(e))
    except (QueryRejected, QueryTimeout) as e:
        raise HTTPException(400, str(e))