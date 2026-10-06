"""Structured output with a JSON-parsing fallback (some providers/models are flaky at tool-based structure)."""
from __future__ import annotations

import json
import re

from pydantic import BaseModel


def _extract_json(text: str) -> str:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    return text[min(starts):] if starts else text


def structured_call(llm, schema: type[BaseModel], system: str, user: str, retries: int = 2):
    last = None
    for _ in range(retries + 1):
        try:
            return llm.with_structured_output(schema).invoke([("system", system), ("user", user)])
        except Exception as e:
            last = e
        try:
            hint = "Respond with ONLY valid JSON matching this schema:\n" + json.dumps(schema.model_json_schema())
            r = llm.invoke([("system", system + "\n\n" + hint), ("user", user)])
            text = r.content if isinstance(r.content, str) else str(r.content)
            return schema.model_validate_json(_extract_json(text))
        except Exception as e:
            last = e
    raise RuntimeError(f"structured call failed: {type(last).__name__}: {last}")