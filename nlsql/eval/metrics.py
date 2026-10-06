"""Execution-accuracy helpers. Compare result sets, not SQL strings."""
from __future__ import annotations


def _norm(v):
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, str):
        return v.strip()
    return v


def result_key(rows, ordered: bool = False):
    norm = [tuple(_norm(v) for v in r) for r in rows]
    return norm if ordered else sorted(norm, key=repr)


def results_match(a, b, ordered: bool = False) -> bool:
    return result_key(a, ordered) == result_key(b, ordered)