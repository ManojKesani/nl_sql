"""uv run python -m nlsql.eval.runner longlist --models groq-qwen,groq-gpt-oss --limit 20"""
from __future__ import annotations

import argparse, json, time
from collections import defaultdict

from .. import registry
from ..agent.build import build_agent
from ..db.executor import run_query
from ..ingest import golden
from ..llm.usage import UsageTracker
from ..observability import setup_tracing, trace_context
from .metrics import results_match


def eval_model(db_id: str, model: str, items: list[dict]) -> dict:
    path = registry.get(db_id)["path"]
    agent, version = build_agent(db_id, model)
    rows_out, by_cat = [], defaultdict(lambda: [0, 0])

    for it in items:
        t = UsageTracker()
        ok, err, pred_sql = False, None, ""
        try:
            expected = run_query(path, it["sql"], limit=500, timeout_s=10)
            with trace_context(db_id, model, version):
                res = agent.invoke({"messages": [{"role": "user", "content": it["question"]}]},
                                   config={"callbacks": [t], "recursion_limit": 25})
            pred_sql = res["structured_response"].sql
            got = run_query(path, pred_sql, limit=500, timeout_s=10)
            ok = results_match(got.rows, expected.rows, ordered=it["category"] == "top_k")
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:200]}"
        s = t.summary()
        by_cat[it["category"]][0] += ok
        by_cat[it["category"]][1] += 1
        rows_out.append({"id": it["id"], "category": it["category"], "correct": ok,
                         "pred_sql": pred_sql, "error": err, **{k: s[k] for k in
                         ("llm_calls", "tool_calls", "input_tokens", "output_tokens", "total_s")}})
        print(f"  {model} {it['id']} {'OK ' if ok else 'BAD'} calls={s['llm_calls']} tok={s['input_tokens']} {s['total_s']}s")

    n = len(rows_out)
    return {
        "model": model, "prompt_version": version, "n": n,
        "accuracy": round(sum(r["correct"] for r in rows_out) / n, 3),
        "avg_llm_calls": round(sum(r["llm_calls"] for r in rows_out) / n, 2),
        "avg_input_tokens": round(sum(r["input_tokens"] for r in rows_out) / n),
        "avg_latency_s": round(sum(r["total_s"] for r in rows_out) / n, 2),
        "by_category": {c: f"{a}/{b}" for c, (a, b) in by_cat.items()},
        "rows": rows_out,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db_id")
    ap.add_argument("--models", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    setup_tracing()
    items = golden.load(a.db_id, only_agreed=True)
    if a.limit:
        items = items[: a.limit]
    reports = [eval_model(a.db_id, m, items) for m in a.models.split(",")]

    out = registry.db_dir(a.db_id) / f"report.{int(time.time())}.json"
    out.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(f"\n{'model':22} {'acc':>5} {'calls':>6} {'in_tok':>7} {'lat_s':>6}")
    for r in reports:
        print(f"{r['model']:22} {r['accuracy']:>5} {r['avg_llm_calls']:>6} {r['avg_input_tokens']:>7} {r['avg_latency_s']:>6}")
        print("   ", r["by_category"])
    print("report ->", out)


if __name__ == "__main__":
    main()