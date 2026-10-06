"""Per-request token and latency capture via a LangChain callback."""
from __future__ import annotations

import threading
import time

from langchain_core.callbacks import BaseCallbackHandler


class UsageTracker(BaseCallbackHandler):
    def __init__(self):
        self.llm_calls: list[dict] = []
        self.tool_calls: list[dict] = []
        self._starts: dict = {}
        self._lock = threading.Lock()
        self._t0 = time.perf_counter()

    # --- LLM ---
    def on_chat_model_start(self, serialized, messages, *, run_id, **kw):
        self._starts[run_id] = time.perf_counter()

    def on_llm_start(self, serialized, prompts, *, run_id, **kw):
        self._starts[run_id] = time.perf_counter()

    def on_llm_end(self, response, *, run_id, **kw):
        dt = time.perf_counter() - self._starts.pop(run_id, time.perf_counter())
        usage = {}
        try:
            usage = getattr(response.generations[0][0].message, "usage_metadata", None) or {}
        except (IndexError, AttributeError):
            pass
        with self._lock:
            self.llm_calls.append({
                "latency_s": round(dt, 3),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            })

    # --- tools ---
    def on_tool_start(self, serialized, input_str, *, run_id, **kw):
        self._starts[run_id] = time.perf_counter()

    def on_tool_end(self, output, *, run_id, **kw):
        dt = time.perf_counter() - self._starts.pop(run_id, time.perf_counter())
        with self._lock:
            self.tool_calls.append({"latency_s": round(dt, 3)})

    def summary(self) -> dict:
        return {
            "llm_calls": len(self.llm_calls),
            "tool_calls": len(self.tool_calls),
            "input_tokens": sum(c["input_tokens"] for c in self.llm_calls),
            "output_tokens": sum(c["output_tokens"] for c in self.llm_calls),
            "llm_latency_s": round(sum(c["latency_s"] for c in self.llm_calls), 3),
            "tool_latency_s": round(sum(c["latency_s"] for c in self.tool_calls), 3),
            "total_s": round(time.perf_counter() - self._t0, 3),
            "per_call": self.llm_calls,
        }