"""ask(): route -> run agent -> detect failure -> escalate once to the bigger model."""
from __future__ import annotations

import threading

from .. import registry
from ..llm.usage import UsageTracker
from ..observability import trace_context
from .build import build_agent
from .router import route

_agents: dict = {}
_lock = threading.Lock()


def _get_agent(db_id: str, model: str, fallbacks: list[str], run_limit: int):
    key = (db_id, model)
    with _lock:
        if key not in _agents:
            _agents[key] = build_agent(db_id, model, fallbacks, run_limit)
        return _agents[key]


def _failed(result: dict, tracker: UsageTracker) -> str | None:
    """Return a reason string if the run looks bad, else None."""
    sr = result.get("structured_response")
    if sr is None:
        return "no structured response (call limit or parse failure)"
    tool_msgs = [m for m in result["messages"] if getattr(m, "name", None) == "query_database"]
    if tool_msgs and str(tool_msgs[-1].content).startswith("ERROR"):
        return "last query still errored"
    if not tool_msgs and sr.sql:
        return "answered without running the query"
    return None


def _attempt(db_id: str, model: str, question: str, cfg: dict) -> dict:
    agent, version = _get_agent(db_id, model, cfg["fallbacks"], cfg["run_limit"])
    t = UsageTracker()
    try:
        with trace_context(db_id, model, version):
            result = agent.invoke({"messages": [{"role": "user", "content": question}]},
                                  config={"callbacks": [t], "recursion_limit": 25})
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {str(e)[:200]}",
                "usage": t.summary(), "model": model, "prompt_version": version}
    reason = _failed(result, t)
    out = {"ok": reason is None, "reason": reason, "usage": t.summary(),
           "model": model, "prompt_version": version}
    if result.get("structured_response") is not None:
        out["response"] = result["structured_response"].model_dump()
    return out


def ask(question: str, db_id: str | None = None, model: str | None = None) -> dict:
    db_id = db_id or route(question)
    cfg = registry.get_config(db_id)
    model = model or cfg["model"]
    if not model:
        raise ValueError(f"No model configured for '{db_id}'. Use registry.set_config or pass model.")

    first = _attempt(db_id, model, question, cfg)
    final, escalated = first, False
    if not first["ok"] and cfg["escalate_to"] and cfg["escalate_to"] != model:
        second = _attempt(db_id, cfg["escalate_to"], question, cfg)
        escalated = True
        # keep the escalated result if it worked, else keep whichever produced a response
        final = second if second["ok"] or "response" not in first else first

    return {
        "db_id": db_id,
        "model": final["model"],
        "prompt_version": final["prompt_version"],
        "escalated": escalated,
        "ok": final["ok"],
        "reason": final["reason"],
        "usage": {"first_attempt": first["usage"],
                  **({"escalation": second["usage"]} if escalated else {})},
        **(final.get("response") or {}),
    }