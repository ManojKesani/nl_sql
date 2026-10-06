"""CLI:  uv run python -m nlsql.ingest.pipeline longlist --path longlist.db --big-model groq-gpt-oss"""
from __future__ import annotations

import argparse

from .. import registry
from . import enrich, golden, profile, promptgen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db_id")
    ap.add_argument("--path", help="SQLite file; registers/updates the db_id")
    ap.add_argument("--desc", default="")
    ap.add_argument("--big-model", help="nickname in models.json (needed for enrich/golden)")
    ap.add_argument("--stages", default="profile,enrich,golden,prompt")
    ap.add_argument("-n", type=int, default=40, help="target golden questions")
    a = ap.parse_args()

    if a.path:
        registry.register(a.db_id, a.path, a.desc)
    stages = a.stages.split(",")

    if "profile" in stages:
        p = profile.run(a.db_id)
        print(f"[profile] {len(p['tables'])} tables")
    if "enrich" in stages:
        enrich.run(a.db_id, a.big_model)
        print("[enrich] wrote enrichment.json (review it!)")
    if "golden" in stages:
        golden.run(a.db_id, a.big_model, n=a.n)
    if "prompt" in stages:
        promptgen.build(a.db_id)


if __name__ == "__main__":
    main()