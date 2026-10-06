"""Phoenix tracing setup (idempotent) + per-request metadata so traces are filterable."""
from __future__ import annotations

from .config import settings

_tracer_provider = None


def setup_tracing():
    global _tracer_provider
    if _tracer_provider is not None or not settings.phoenix_endpoint:
        return _tracer_provider
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from phoenix.otel import register

    _tracer_provider = register(
        project_name=settings.phoenix_project,
        endpoint=settings.phoenix_endpoint,
    )
    LangChainInstrumentor().instrument(tracer_provider=_tracer_provider)
    return _tracer_provider


def trace_context(db_id: str, model: str, prompt_version: str = "v0", session_id: str | None = None):
    """Wrap agent.invoke in `with trace_context(...):` to tag every span."""
    from openinference.instrumentation import using_attributes

    return using_attributes(
        session_id=session_id,
        metadata={"db_id": db_id, "model": model, "prompt_version": prompt_version},
        tags=[f"db:{db_id}", f"model:{model}"],
        prompt_template_version=prompt_version,
    )