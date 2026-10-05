import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="NL to SQL Prompt Studio", layout="wide")
st.title("NL → SQL Prompt Studio")

# ---------- sidebar: file locations ----------
BASE = Path(st.sidebar.text_input("Project folder", str(Path.cwd()))).expanduser().resolve()
if not BASE.is_dir():
    st.sidebar.error(f"Folder not found: {BASE}")
    st.stop()


def pick(label, patterns, preferred, must_exist=True, exclude=()):
    """Dropdown of files in BASE matching the glob patterns."""
    files = sorted({p.name for pat in patterns for p in BASE.glob(pat)
                    if p.is_file() and p.name not in exclude})
    if not must_exist and preferred not in files:
        files.insert(0, preferred)  # lets the app create it on first save
    if not files:
        st.sidebar.warning(f"{label}: no matching files in {BASE}")
        return BASE / preferred
    idx = files.index(preferred) if preferred in files else 0
    return BASE / st.sidebar.selectbox(label, files, index=idx)


SYS_PATH = pick("System prompt file", ["*.json"], "sys_prompt.json", must_exist=False)
IN_PATH = pick("Input file", ["*.json"], "input.json", must_exist=False)
OUT_PATH = pick("Output file", ["*.json"], "output.json", must_exist=False)
SCRIPT = pick("Agent script", ["*.py"], "agent.py", exclude=("prompt_studio.py",))
DB_PATH = pick("SQLite database", ["*.db", "*.sqlite", "*.sqlite3"], "books.db")


def load(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save(path, data):
    if path.exists():  # keep a backup of the previous version
        shutil.copy(path, path.with_suffix(path.suffix + ".bak"))
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def kv_df(d):
    return pd.DataFrame({"name": list(d.keys()), "description": list(d.values())})


def df_to_kv(df):
    return {
        str(r["name"]).strip(): str(r["description"])
        for _, r in df.iterrows()
        if pd.notna(r["name"]) and str(r["name"]).strip()
    }


def run_query(db_path, sql, limit=500, timeout_s=10):
    """Run one read-only SELECT/WITH query and return a DataFrame."""
    s = sql.strip().rstrip(";").strip()
    if not s:
        raise ValueError("The query is empty.")
    if not s.lower().startswith(("select", "with")) or ";" in s:
        raise ValueError("Only a single SELECT/WITH statement is allowed.")
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path.resolve()}")
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    start = time.time()
    conn.set_progress_handler(lambda: 1 if time.time() - start > timeout_s else 0, 10000)
    try:
        cur = conn.execute(s)
        rows = cur.fetchmany(limit)
        return pd.DataFrame(rows, columns=[c[0] for c in cur.description])
    finally:
        conn.close()


sp = load(SYS_PATH, {})
inp = load(IN_PATH, {"content": ""})
schema = sp.get("database_schema", {})

tab_in, tab_role, tab_schema, tab_rules, tab_out, tab_ex, tab_raw, tab_run = st.tabs(
    ["Question", "Role", "Schema", "Rules", "Output format", "Examples", "Raw JSON", "Run"]
)

# ---------- question (input.json) ----------
with tab_in:
    q = st.text_area("User question", inp.get("content", ""), height=150)
    if st.button("Save input.json", type="primary"):
        save(IN_PATH, {**inp, "content": q})
        st.success(f"Saved {IN_PATH}")

# ---------- role ----------
with tab_role:
    role = st.text_area("Role", sp.get("role", ""), height=120)

# ---------- schema ----------
with tab_schema:
    dialect = st.text_input("Dialect", schema.get("dialect", "SQLite 3"))
    ddl = st.text_area("DDL (one statement per line)", "\n".join(schema.get("ddl", [])), height=220)
    rels = st.text_area("Relationships (one per line)", "\n".join(schema.get("relationships", [])), height=120)
    st.markdown("**Table descriptions**")
    td_df = st.data_editor(kv_df(schema.get("table_descriptions", {})), num_rows="dynamic",
                           use_container_width=True, key="td")
    st.markdown("**Column notes**")
    cn_df = st.data_editor(kv_df(schema.get("column_notes", {})), num_rows="dynamic",
                           use_container_width=True, key="cn")

# ---------- rules ----------
with tab_rules:
    rules_df = st.data_editor(pd.DataFrame({"rule": sp.get("rules", [])}), num_rows="dynamic",
                              use_container_width=True, key="rules")

# ---------- output format ----------
with tab_out:
    of = sp.get("output_format", {})
    of_new = {k: st.text_area(k, of.get(k, ""), height=100, key=f"of_{k}")
              for k in ["thought_process", "sql", "explanation"]}

# ---------- examples ----------
with tab_ex:
    cols = ["question", "thought_process", "sql", "explanation"]
    ex_df = st.data_editor(pd.DataFrame(sp.get("examples", []), columns=cols), num_rows="dynamic",
                           use_container_width=True, key="ex")

# ---------- assemble ----------
def build():
    new = dict(sp)
    new["role"] = role
    new["database_schema"] = {
        **schema,
        "dialect": dialect,
        "ddl": [l for l in ddl.splitlines() if l.strip()],
        "table_descriptions": df_to_kv(td_df),
        "relationships": [l for l in rels.splitlines() if l.strip()],
        "column_notes": df_to_kv(cn_df),
    }
    new["rules"] = [r for r in rules_df["rule"].dropna() if str(r).strip()]
    new["output_format"] = of_new
    new["examples"] = ex_df.dropna(how="all").fillna("").to_dict("records")
    return new


st.sidebar.divider()
if st.sidebar.button("Save sys_prompt.json", type="primary"):
    save(SYS_PATH, build())
    st.sidebar.success(f"Saved {SYS_PATH} (backup: .bak)")

# ---------- raw JSON ----------
with tab_raw:
    st.caption("Preview of what will be saved, or paste a whole file and apply it.")
    raw = st.text_area("JSON", json.dumps(build(), indent=2, ensure_ascii=False), height=450)
    if st.button("Validate & save raw JSON"):
        try:
            save(SYS_PATH, json.loads(raw))
            st.success("Valid JSON, saved. Reload the page to see it in the other tabs.")
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON: {e}")

# ---------- run ----------
with tab_run:
    st.caption("Runs your agent script using the saved files. Save first.")
    if st.button("Run agent"):
        with st.spinner("Running..."):
            try:
                env = {**os.environ, "SYS_PROMPT_FILE": str(SYS_PATH),
                       "INPUT_FILE": str(IN_PATH), "OUTPUT_FILE": str(OUT_PATH)}
                p = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True,
                                   timeout=300, cwd=BASE, env=env)
                st.code(p.stdout or "(no stdout)")
                if p.stderr:
                    st.code(p.stderr)
            except Exception as e:
                st.error(str(e))
    if OUT_PATH.exists():
        out = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        st.subheader("Latest output")
        gen_sql = out.get("sql", "")
        st.markdown("**SQL** (editable; re-runs when you click outside the box)")
        sql_text = st.text_area("SQL", gen_sql, height=160, key=f"sql_{hash(gen_sql)}",
                                label_visibility="collapsed")
        st.markdown("**Results**")
        try:
            df = run_query(DB_PATH, sql_text)
            st.caption(f"{len(df)} row(s) (max 500 shown)")
            st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error(f"{type(e).__name__}: {e}")
        st.markdown("**Explanation**")
        st.write(out.get("explanation", ""))
        with st.expander("Thought process"):
            st.write(out.get("thought_process", ""))