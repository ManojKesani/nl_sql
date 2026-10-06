"""Deterministic profiling of a SQLite DB (no LLM). Produces a profile dict and a compact schema card."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .executor import connect_ro

import re
_DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?")

def _q(name: str) -> str:
    """Quote an identifier."""
    return '"' + name.replace('"', '""') + '"'


def _clip(v, n: int = 60):
    if isinstance(v, bytes):
        return f"<{len(v)} bytes>"
    if isinstance(v, str) and len(v) > n:
        return v[:n] + "…"
    return v


def _profile_column(conn, table: str, col: str, ctype: str, max_distinct: int, top_k: int) -> dict:
    t, c = _q(table), _q(col)
    nulls, distinct, mn, mx = conn.execute(
        f"SELECT SUM({c} IS NULL), COUNT(DISTINCT {c}), MIN({c}), MAX({c}) FROM {t}"
    ).fetchone()
    info = {"null_count": nulls or 0, "distinct_count": distinct, "min": _clip(mn), "max": _clip(mx)}
    if distinct and distinct <= max_distinct:
        vals = conn.execute(
            f"SELECT {c}, COUNT(*) n FROM {t} WHERE {c} IS NOT NULL GROUP BY {c} ORDER BY n DESC"
        ).fetchall()
        info["values"] = [_clip(v[0]) for v in vals]
    elif distinct and "INT" not in ctype.upper() and "REAL" not in ctype.upper() and not (isinstance(mn, str) and _DATE.match(mn)):
        top = conn.execute(
            f"SELECT {c}, COUNT(*) n FROM {t} WHERE {c} IS NOT NULL "
            f"GROUP BY {c} ORDER BY n DESC LIMIT {top_k}"
        ).fetchall()
        info["top_values"] = [_clip(v[0]) for v in top]
    return info


def profile_db(db_path, sample_rows: int = 3, max_distinct: int = 15, top_k: int = 5) -> dict:
    conn = connect_ro(db_path)
    try:
        objs = conn.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        tables = {}
        for name, typ in objs:
            cols_raw = conn.execute(f"PRAGMA table_info({_q(name)})").fetchall()
            fks = conn.execute(f"PRAGMA foreign_key_list({_q(name)})").fetchall()
            n_rows = conn.execute(f"SELECT COUNT(*) FROM {_q(name)}").fetchone()[0]
            columns = []
            for _cid, cname, ctype, notnull, _dflt, pk in cols_raw:
                col = {"name": cname, "type": ctype or "", "pk": bool(pk), "notnull": bool(notnull)}
                if n_rows:
                    try:
                        col.update(_profile_column(conn, name, cname, ctype or "", max_distinct, top_k))
                    except sqlite3.Error as e:
                        col["profile_error"] = str(e)
                columns.append(col)
            sample = conn.execute(f"SELECT * FROM {_q(name)} LIMIT {sample_rows}").fetchall()
            tables[name] = {
                "type": typ,
                "row_count": n_rows,
                "columns": columns,
                "foreign_keys": [
                    {"from": fk[3], "to_table": fk[2], "to": fk[4]} for fk in fks
                ],
                "sample_rows": [[_clip(v) for v in row] for row in sample],
            }
        return {"db_file": Path(db_path).name, "tables": tables}
    finally:
        conn.close()


def render_schema_card(profile: dict, with_samples: bool = True) -> str:
    """Compact text the LLM reads. Far cheaper than indented JSON."""
    out = []
    for tname, t in profile["tables"].items():
        out.append(f"## {tname} ({t['row_count']} rows)")
        for c in t["columns"]:
            line = f"- {c['name']} {c['type']}".rstrip()
            if c["pk"]:
                line += " PK"
            hints = []
            if c.get("values"):
                hints.append("values: " + ", ".join(map(repr, c["values"])))
            elif c.get("top_values"):
                hints.append(f"{c['distinct_count']} distinct, e.g. " + ", ".join(map(repr, c["top_values"])))
            elif c.get("min") is not None and c.get("distinct_count"):
                hints.append(f"range {c['min']!r}..{c['max']!r}")
            if c.get("null_count"):
                hints.append(f"{c['null_count']} nulls")
            if hints:
                line += "  — " + "; ".join(hints)
            out.append(line)
        for fk in t["foreign_keys"]:
            out.append(f"FK: {tname}.{fk['from']} -> {fk['to_table']}.{fk['to']}")
        if with_samples and t["sample_rows"]:
            out.append("sample: " + json.dumps(t["sample_rows"][0], default=str))
        out.append("")
    return "\n".join(out).strip()


def save_profile(profile: dict, path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(profile, indent=2, default=str), encoding="utf-8")