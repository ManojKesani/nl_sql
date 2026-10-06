"""uv run python -m nlsql.ingest.review longlist   -> walk disputed/unreviewed items; y=keep, n=drop, s=skip"""
import json, sys
from .. import registry
from . import golden


def main(db_id: str):
    items = golden.load(db_id)
    keep = []
    for it in items:
        if it["status"] == "agreed" or it["reviewed"]:
            keep.append(it); continue
        print(f"\n[{it['id']}] {it['category']}\nQ: {it['question']}\nSQL: {it['sql']}")
        print(f"rows({it['n_rows']}): {it['expected_rows'][:5]}")
        c = input("keep as correct? [y/n/s] ").strip().lower()
        if c == "y":
            it["status"], it["reviewed"] = "agreed", True; keep.append(it)
        elif c == "s":
            keep.append(it)
    out = registry.db_dir(db_id) / "golden.jsonl"
    out.write_text("\n".join(json.dumps(i, default=str) for i in keep), encoding="utf-8")
    print(f"saved {len(keep)} items")


if __name__ == "__main__":
    main(sys.argv[1])