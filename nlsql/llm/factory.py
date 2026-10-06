"""Build chat models from models.json nicknames, plus resilience middleware."""
from __future__ import annotations

import json
from functools import lru_cache

from ..config import settings
from .providers import PROVIDERS

from langchain_core.rate_limiters import InMemoryRateLimiter


class UnknownModel(KeyError):
    pass


@lru_cache(maxsize=1)
def load_model_config() -> dict:
    return json.loads(settings.models_file.read_text(encoding="utf-8"))


def build_model(nickname: str | None = None):
    cfg_all = load_model_config()
    nickname = nickname or cfg_all["active"]
    models = cfg_all["models"]
    if nickname not in models:
        raise UnknownModel(f"Unknown model '{nickname}'. Options: {list(models)}")
    cfg = dict(models[nickname])
    rpm = cfg.pop("rpm", None)
    provider = cfg.pop("provider", None)
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Options: {list(PROVIDERS)}")

    if rpm:
        cfg["rate_limiter"] = InMemoryRateLimiter(
            requests_per_second=rpm / 60, check_every_n_seconds=0.1, max_bucket_size=1
        )
    cfg.setdefault("max_retries", 6)
    
    return PROVIDERS[provider](**cfg)


def build_middleware(fallbacks: list[str] | None = None, run_limit: int = 8, retries: int = 2) -> list:
    """Retry w/ backoff, model fallback, and a hard cap on LLM calls per run.

    These come from langchain.agents.middleware. Class names/args can shift between
    versions, so check them against your installed version if import or init fails.
    """
    from langchain.agents.middleware import (
        ModelCallLimitMiddleware,
        ModelFallbackMiddleware,
        ModelRetryMiddleware,
    )

    mw = [
        ModelRetryMiddleware(max_retries=retries, backoff_factor=2.0, initial_delay=1.0, jitter=True),
        ModelCallLimitMiddleware(run_limit=run_limit, exit_behavior="end"),
    ]
    if fallbacks:
        mw.append(ModelFallbackMiddleware(*[build_model(n) for n in fallbacks]))
    return mw