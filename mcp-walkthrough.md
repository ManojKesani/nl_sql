# Moving `query_database` into an MCP server: a walkthrough

A reading guide for what we built, why each step existed, and what went wrong along the way. Read it top to bottom once, then use the sections as reference.

---

## 1. The big idea

### Before

The database tool was a Python function inside `agent.py`:

```
agent.py  ──calls──►  query_database()  ──reads──►  longlist.db
```

Everything lived in one program. The model, the tool and the database access were all the same process.

### After

The tool is its own small program (a server). The agent asks it to run queries over the network:

```
agent.py (api container) ──"run this SQL"──►  db_server.py (mcp container) ──► longlist.db
                         ◄────"here are rows"──
```

### What MCP is

MCP (Model Context Protocol) is an agreed message format between an agent (the **client**) and a tool provider (the **server**). It standardizes two questions:

1. "What tools do you have?" The server answers with each tool's name, description and input schema.
2. "Run this tool with these inputs." The server runs it and returns the result.

Because the format is standard, any MCP-capable agent can use your database tool without custom glue code. That is the payoff: the tool is no longer tied to LangChain or to `agent.py`.

### Your first intuition was right

You thought MCP "moves the tool's scope from a LangChain tool to a server". Correct: the *real work* (running SQL, owning the database file) moved to the server. The reason a `@tool` function still exists in `agent.py` is covered in section 6.

---

## 2. Final architecture

```
browser ──► nginx (:3000) ──/api/──► api (FastAPI + agent) ──MCP :8001──► mcp (db server) ──► longlist.db
                                          │
                                          └──traces──► phoenix (:6006)
```

| Service | Role | Published port |
|---------|------|----------------|
| `web` | nginx serves `index.html`, proxies `/api/` to `api` | 3000 |
| `api` | FastAPI app + LangChain agent | none |
| `mcp` | MCP server exposing the `query_database` tool | none |
| `phoenix` | Tracing UI | 6006 |

Only `web` and `phoenix` are reachable from your machine. `api` and `mcp` are reachable only from other containers, by service name (Compose gives each service a DNS name equal to its name).

---

## 3. Two MCP transports: stdio vs Streamable HTTP

| | stdio | Streamable HTTP |
|---|---|---|
| How it works | The client launches the server as a subprocess and talks through its input/output | The server runs on its own and clients connect over the network |
| Good for | Local tools launched by a desktop app | Separate processes and containers, deployments |
| Used in this project | Only by `mcp dev` (the Inspector) | By the agent in Docker |

Why Docker needs HTTP: `api` and `mcp` are different containers, so `api` cannot launch `mcp` as a subprocess. It has to connect over the network.

### Why `mcp dev` and `uv run db_server.py` were separate things

- `uv run db_server.py` runs your file directly. The `__main__` block starts an HTTP server on port 8001 and waits.
- `uv run mcp dev db_server.py` imports your file, finds the `mcp` object, **ignores the `__main__` block**, launches its own copy over stdio, and connects the Inspector web page to that copy.

So when you tested in the Inspector, you tested the stdio copy, not the HTTP server in the other terminal. The tool code is identical, so the results matched, but the HTTP path was only truly exercised later by `test_mcp.py` and the agent.

---

## 4. MCP Python SDK v2: what changed from v1

Your `pyproject.toml` has `mcp>=2.3.0`, so you are on v2. Most tutorials still show v1 code. Differences that matter here:

| v1 | v2 |
|----|----|
| `from mcp.server.fastmcp import FastMCP` | `from mcp.server.mcpserver import MCPServer` |
| `FastMCP("name", host=..., port=...)` | host and port are passed to `run_streamable_http_async(...)` |
| `streamablehttp_client` | `streamable_http_client`, or just `Client("http://.../mcp")` |
| `McpError` | `MCPError` |
| Pydantic model fields in camelCase | snake_case |

If you copy code from a blog or an LLM and get `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`, it is v1 code. The migration guide is at `https://py.sdk.modelcontextprotocol.io/migration/`.

---

## 5. The server: `db_server.py`

```python
import sqlite3

import anyio
from mcp.server.mcpserver import MCPServer

DB_FILE = "longlist.db"

mcp = MCPServer("longlist-db")


def run_query(sql: str, limit: int = 100) -> dict:
    s = sql.strip().rstrip(";").strip()
    if not s.lower().startswith(("select", "with")) or ";" in s:
        raise ValueError("Only a single SELECT/WITH statement is allowed.")
    conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)  # read-only
    try:
        cur = conn.execute(s)
        rows = cur.fetchmany(limit)
        return {"columns": [c[0] for c in cur.description], "rows": rows}
    finally:
        conn.close()


@mcp.tool()
def query_database(sql: str) -> str:
    """Run a read-only SQLite SELECT on the books database.
    Returns columns and up to 20 rows, or an ERROR you should use to fix the query."""
    try:
        r = run_query(sql, limit=20)
        return f"columns={r['columns']} rows={r['rows']}"
    except Exception as e:
        return f"ERROR: {e}"


if __name__ == "__main__":
    anyio.run(lambda: mcp.run_streamable_http_async(host="0.0.0.0", port=8001))
```

Notes:

- `@mcp.tool()` turns the function into an MCP tool. The **name** comes from the function name, the **description** from the docstring, and the **input schema** from the type hints.
- Errors are returned as text (`"ERROR: ..."`), not raised. That lets the model read the error and fix its query, the same trick as before.
- `host="0.0.0.0"` is required inside Docker. Bound to `127.0.0.1`, the server would only accept connections from inside its own container, so `api` could not reach it. (Locally, `127.0.0.1` was fine.)
- `mode=ro` makes the SQLite connection read-only, in addition to the SELECT/WITH check.

### What the Inspector and `test_mcp.py` showed

Listing the tool returned its name, description and schema:

```
name='query_database'
description='Run a read-only SQLite SELECT on the books database. ...'
input_schema={'properties': {'sql': {'type': 'string'}}, 'required': ['sql'], ...}
```

Calling it returned a `CallToolResult`:

```
content=[TextContent(type='text', text="columns=['count(*)'] rows=[(78,)]")]
structured_content={'result': "columns=['count(*)'] rows=[(78,)]"}
is_error=False
```

The text lives in `result.content[0].text`. `is_error=False` is MCP's own success flag; your `ERROR: ...` strings still arrive as normal text with `is_error=False`.

One small clarification: the Inspector call that returned `ERROR: no such column: oops` was `SELECT oops`. A typo like `SELEC oops` would have been rejected by your guard in `run_query` with "Only a single SELECT/WITH statement is allowed." Both are valid error paths.

---

## 6. The client side: the "shim" in `agent.py`

### The problem

`create_agent(...)` only understands LangChain tools. It cannot talk to an MCP server directly. So `agent.py` needs one object that **looks like a LangChain tool** to the agent but **forwards the work to the server**:

```
model ──► LangChain tool (shim in agent.py) ──MCP──► server ──► database
```

### Why we wrote it by hand

The package `langchain-mcp-adapters` builds that shim automatically (`tools = await client.get_tools()`). Version 0.3.1 installed fine, but crashed on import with MCP 2.3.0:

```
ImportError: cannot import name 'RequestContext' from 'mcp.shared.context'
```

The adapter was written against the v1 SDK. Rather than downgrade `mcp` (which would break the server code), we used the v2 SDK's own `Client` and wrote the shim ourselves.

### The code

```python
import asyncio
import os
from mcp import Client

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8001/mcp")


@tool
def query_database(sql: str) -> str:
    """Run a read-only SQLite SELECT on the books database.
    Returns columns and up to 20 rows, or an ERROR you should use to fix the query."""
    async def _call():
        async with Client(MCP_URL) as client:
            return await client.call_tool("query_database", {"sql": sql})
    try:
        result = asyncio.run(_call())
        return result.content[0].text
    except Exception as e:
        return f"ERROR: could not reach database tool: {e}"
```

### Line by line

- `@tool` and the signature/docstring: this is what the **model** sees. Same as before the migration.
- `async with Client(MCP_URL) as client:` opens a connection to the server and closes it afterwards.
- `client.call_tool("query_database", {"sql": sql})` says "run your tool named `query_database` with this input" and returns the reply.
- `asyncio.run(_call())`: the tool function is ordinary (sync) code, but `_call` is async. `asyncio.run` runs it to completion. This works because FastAPI runs a sync `/ask` handler in a worker thread. We can convert the app to fully async later.
- `result.content[0].text` pulls the text out of the reply.
- The `except` returns an error as text, so a down server produces a readable message rather than a crash.
- `MCP_URL` comes from an environment variable: `127.0.0.1` locally, `http://mcp:8001/mcp` in Docker.

### Known downsides

- **Duplicated description:** the tool's description now exists on the server and in the shim. The model only sees the shim's. This is exactly what the adapter would remove once it supports MCP 2.x.
- **A new connection per call:** each tool call opens a fresh MCP connection (a handshake plus the call). Fine for now, wasteful at scale.

---

## 7. Docker setup

### `docker-compose.yaml`

```yaml
services:
  api:
    build: .
    env_file: .env
    environment:
      MCP_URL: http://mcp:8001/mcp
    depends_on:
      - mcp

  web:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - api

  phoenix:
    image: arizephoenix/phoenix:latest
    ports:
      - "6006:6006"

  mcp:
    build: .
    command: python db_server.py
```

- `mcp` reuses the same image as `api` (`build: .`) but overrides the start command. One Dockerfile, two services.
- `mcp` has no `ports:`, so it is not published. Only containers on the Compose network can reach it.
- `MCP_URL` uses the service name `mcp` as the hostname. Compose's built-in DNS resolves it. This is the same mechanism by which nginx finds `http://api:8000/`.
- `depends_on` only controls start order, not readiness.

### `Dockerfile` (the two lines that mattered)

```dockerfile
COPY agent.py db_server.py sys_prompt.json models.json longlist.db ./
ENV PATH="/app/.venv/bin:$PATH"
```

- `db_server.py` had to be added to the `COPY` line. The Dockerfile copies files by name, so a new file is not in the image until you list it.
- The `ENV PATH` line puts the virtual environment first on the path, so plain `python` and `uvicorn` use the installed dependencies. That is why `command: python db_server.py` works without `uv run`.

---

## 8. Errors we hit, and what caused each

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: mcp.server.fastmcp` (would occur with v1 code) | v2 renamed `FastMCP` to `MCPServer` | Import from `mcp.server.mcpserver` |
| `ImportError: cannot import name 'RequestContext'` | `langchain-mcp-adapters` 0.3.1 targets MCP v1 | Use the SDK `Client` and a hand-written shim |
| `Expected a Python module at: src/nl_sql/__init__.py` in the `mcp` container | `uv run` tries to build the project as a package, because `pyproject.toml` has a `[build-system]` and a `[project.scripts]` entry | Don't use `uv run` in the container; run `python db_server.py` with the venv on `PATH` (or `uv run --no-install-project`) |
| `mcp` container exits right after "Started" | Same as above. Compose reports "Started" when the process launches, not when it stays healthy | Always check `docker compose logs <service>` |
| Would have failed: "can't open file db_server.py" | `db_server.py` wasn't in the Dockerfile's `COPY` line | Add it |
| Phoenix export errors when running locally (`Failed to resolve 'phoenix'`) | `phoenix` is a Docker service name; it only resolves inside the Compose network | Expected outside Docker; disappears in Compose |

A general lesson: "Started" in `docker compose up` means a process was launched, not that it is healthy. Read the logs.

---

## 9. How we verified it

Each layer was checked on its own before the next was added:

1. **Server alone:** the Inspector listed the tool and ran queries (`rows=[(78,)]`, plus an `ERROR:` case).
2. **HTTP client alone:** `test_mcp.py` listed the tool and called it over HTTP.
3. **Agent plus local server:** `curl` to `/ask` returned `tool_calls: 1` and an answer containing 78.
4. **Everything in Docker:** a question in the browser returned a correct answer.
5. **Proof the MCP path was used:** `docker compose logs mcp` showed `POST /mcp ... 200 OK` lines from `172.18.0.4` (the `api` container). The answer alone would look identical if the tool had run locally inside `api`, so the server log is the real evidence.

The three `POST /mcp` lines per question are probably the connection handshake plus the tool call (this is an inference, not something we confirmed).

### What Phoenix showed

The trace you pasted was the model's final step: a call to a pseudo-tool named `SQLResponse`. That is how `ToolStrategy` makes the model fill your `thought_process`, `sql` and `answer` fields. It is not the database call. The actual `query_database` call should appear as its own span earlier in the same trace.

---

## 10. Repo cleanup status

Done:

- `.gitignore` covers `.env`, `.venv/`, `__pycache__/`, `*.pyc`, and editor/OS files.
- Verified `.env` was never committed (`git ls-files` and `git log -- .env` both empty).
- `.env.example` created with names only.
- Removed `log.sql` (an empty scratch file).
- Committed: "Move query_database into a standalone MCP server".

Still to do:

- Finish `README.md`. The architecture section is drafted; still needed are Quick start (including the required API keys), example questions, supported models, and how to change the prompt and models.
- Add `.dockerignore` (keep `.env`, `.venv`, `.git` and `__pycache__` out of the image).
- Add a `LICENSE` (MIT is the usual default).
- Decide what to do with `src/nl_sql/__init__.py` and the `nl-sql = "nl_sql:main"` script. They exist only to satisfy the build system, and `main()` does not exist.
- Check that `longlist.db` is fine to share and note where the data came from.
- For the move to Windows: add a `.gitattributes` with `* text=auto eol=lf` so line endings don't break files inside Linux containers.

---

## 11. Loose ends in the code

1. **`/sql` bypasses MCP.** `agent.py` still has its own `run_query` and its own copy of `longlist.db` for the `/sql` endpoint. The SQL logic now exists in two places. Options: call the MCP tool from `/sql` too, or remove the endpoint (the eval harness only needs `/ask`).
2. **Duplicated tool description** (see section 6).
3. **Connection per call** (see section 6).
4. **Sync-in-async shortcut.** `asyncio.run` inside a sync tool works but is a workaround. Moving `/ask` to `async def` with `agent.ainvoke` would be the proper fix.
5. **Adapter compatibility.** Revisit `langchain-mcp-adapters` when it supports MCP 2.x; it would delete the hand-written shim.

---

## 12. Glossary

- **MCP:** a standard message format between an agent and a tool server.
- **MCP server:** a program that exposes tools (and other things) via MCP. Here, `db_server.py`.
- **MCP client:** the side that connects and calls tools. Here, the `Client` in `agent.py`.
- **Tool:** a named function with a description and an input schema, which the model can choose to call.
- **Transport:** how MCP messages travel. stdio (subprocess) or Streamable HTTP (network).
- **Shim:** a thin adapter. Here, the LangChain `@tool` that forwards to the MCP server.
- **Inspector:** a web UI for manually listing and calling an MCP server's tools.
- **`0.0.0.0`:** "listen on all network interfaces". Needed inside a container so other containers can connect.
- **Service-name DNS:** inside a Compose network, a service's name works as its hostname (`mcp`, `api`, `phoenix`).
- **Trace / span:** Phoenix records each model call and tool call as a span; the spans of one request form a trace.

---

## 13. What to try next

- Run the hard questions that were still untested: fan-out (highest-rated author), zero rows (2015), and the unanswerable one (publisher country), then compare `groq-qwen` and `groq-gpt-oss`.
- Open a Phoenix trace and find the `query_database` span; compare its input and output with the `ToolMessage` in the API log.
- Stop the `mcp` container (`docker compose stop mcp`), ask a question, and watch the `ERROR: could not reach database tool` path behave.
- Build the eval harness (question file, expected rows, a runner that calls `/ask`, a score per model).
