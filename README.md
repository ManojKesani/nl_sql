![alt text](<Screenshot 2026-10-06 at 03-08-30 nl-sql - Projects.png>)
![alt text](<Screenshot 2026-10-06 at 03-08-54 The Longlist Library.png>)


# nl-sql: Ask the Books Database

A natural-language-to-SQL app. Type a question in plain English (e.g. *"Which books did Yale University Press publish?"*), and an LLM agent writes a read-only SQLite query, runs it against the `longlist.db` books database, and returns a structured answer: the reasoning, the SQL, and a plain-English result.

## Features

- **LLM agent with tool use**: a LangChain agent iterates on its own SQL, using database errors to fix its queries.
- **Structured responses**: every answer returns `thought_process`, `sql`, and `answer` (enforced via `ToolStrategy(SQLResponse)`).
- **Swappable models**: switch between Groq, NVIDIA, and OpenRouter models per request using nicknames defined in `models.json`.
- **MCP database server**: the database is exposed to the agent as a tool through a Model Context Protocol (MCP) server over streamable HTTP.
- **Read-only by design**: only a single `SELECT`/`WITH` statement is accepted, and SQLite is opened with `mode=ro`.
- **Observability**: LLM and tool traces are sent to [Arize Phoenix](https://github.com/Arize-ai/phoenix).
- **Minimal web UI**: a static HTML page served by nginx.

## Architecture

```
Browser ──► nginx (web, :3000)
               │  /api/*
               ▼
          FastAPI (api, :8000)  ──traces──►  Phoenix (:6006)
          agent.py + LangChain agent
               │  MCP (streamable HTTP)
               ▼
          MCP server (mcp, :8001)
          db_server.py
               │
               ▼
          SQLite: longlist.db (read-only)
```

| Service   | Description                                              | Port |
|-----------|----------------------------------------------------------|------|
| `web`     | nginx serving `frontend/index.html`, proxying `/api/` to the API | 3000 |
| `api`     | FastAPI app (`agent.py`) hosting the agent               | 8000 (internal) |
| `mcp`     | MCP server (`db_server.py`) exposing the `query_database` tool | 8001 (internal) |
| `phoenix` | Arize Phoenix tracing UI                                 | 6006 |

## Project Structure

```
.
├── agent.py            # FastAPI app, agent construction, model providers
├── db_server.py        # MCP server exposing query_database
├── test_mcp.py         # Quick script to test the MCP server
├── sys_prompt.json     # System prompt (schema description, instructions)
├── models.json         # Model nicknames, providers, and settings
├── longlist.db         # SQLite database
├── Dockerfile          # Python 3.13 + uv image for api and mcp
├── docker-compose.yml  # api, mcp, web, phoenix
├── pyproject.toml      # Dependencies (managed with uv)
├── .env                # API keys (not committed)
└── frontend/
    ├── Dockerfile      # nginx:alpine
    ├── nginx.conf      # Static hosting + /api/ reverse proxy
    └── index.html      # Simple question UI
```

## Prerequisites

- Docker and Docker Compose (recommended), **or**
- Python 3.13+ and [uv](https://docs.astral.sh/uv/) for local development
- An API key for at least one model provider (Groq, NVIDIA, or OpenRouter)

## Configuration

### 1. Environment variables

Create a `.env` file in the project root with the keys for the providers you plan to use:

```env
GROQ_API_KEY=your_groq_key
NVIDIA_API_KEY=your_nvidia_key
OPENROUTER_API_KEY=your_openrouter_key
```

Optional:

```env
MCP_URL=http://127.0.0.1:8001/mcp   # set automatically to http://mcp:8001/mcp in Docker
```

### 2. Models (`models.json`)

Each entry under `models` is a nickname. `provider` selects the backend (`groq`, `nvidia`, or `openrouter`); every other field is passed straight to the provider's LangChain chat class. `active` is the default used when a request doesn't specify a model.

```json
{
  "active": "groq-qwen",
  "models": {
    "groq-qwen": {
      "provider": "groq",
      "model": "qwen/qwen3.8-27b",
      "temperature": 0
    }
  }
}
```

Currently configured: `groq-qwen`, `groq-gpt-oss`, `nvidia-nemotron`, `openrouter-free`.

### 3. System prompt (`sys_prompt.json`)

Holds the instructions and database schema the agent sees. Edit this to change how the agent reasons about your tables.

## Running with Docker

```bash
docker compose up --build
```

Then open:

- **App**: http://localhost:3000
- **Phoenix traces**: http://localhost:6006

## Running Locally (without Docker)

```bash
# Install dependencies
uv sync

# Terminal 1: start the MCP database server
uv run python db_server.py

# Terminal 2: start the API
uv run uvicorn agent:app --host 0.0.0.0 --port 8000 --reload
```

Notes for local runs:

- `agent.py` sends traces to `http://phoenix:6006/v1/traces`, which only resolves inside Docker Compose. For local runs, either run Phoenix locally and change the endpoint, or comment out the tracing block.
- The default `MCP_URL` is `http://127.0.0.1:8001/mcp`.
- The bundled frontend calls `/api/ask` via nginx. To use it locally, serve it behind a proxy, or call the API directly on port 8000.

### Testing the MCP server

```bash
uv run python test_mcp.py
```

This lists the available tools and runs `SELECT count(*) FROM books`.

## Deployment (Windows, macOS, Linux)

Because the project is containerized, deployment is essentially the same on every operating system. Only the Docker install step differs.

### Option 1: Docker (recommended)

**Install Docker**

| OS | Steps |
|----|-------|
| **Windows** | Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) with the WSL 2 backend enabled. Keep the project inside your WSL filesystem (e.g. `~/nl-sql`) rather than `C:\`, since builds are faster there. |
| **macOS** | Install Docker Desktop. Apple Silicon and Intel both work, since the Python, nginx, and uv images are multi-arch. |
| **Linux** | Install [Docker Engine and the Compose plugin](https://docs.docker.com/engine/install/). Then run `sudo usermod -aG docker $USER` and log out and back in so you don't need `sudo`. |

**Run (identical on all systems)**

```bash
# from the project folder, with .env and longlist.db present
docker compose up --build -d
docker compose logs -f api     # follow API logs
docker compose down            # stop everything
```

Open http://localhost:3000 for the app and http://localhost:6006 for Phoenix.

### Option 2: Without Docker

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

**Install uv**

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Run (two terminals)**

```bash
# Terminal 1: MCP database server
uv sync
uv run python db_server.py
```

```bash
# Terminal 2: API
uv run uvicorn agent:app --host 0.0.0.0 --port 8000
```

If you set environment variables by hand instead of using `.env`:

```bash
# macOS / Linux
export MCP_URL=http://127.0.0.1:8001/mcp
```

```powershell
# Windows PowerShell
$env:MCP_URL = "http://127.0.0.1:8001/mcp"
```

Without Docker you also need to:

1. Change the Phoenix endpoint in `agent.py` to `http://localhost:6006/v1/traces`, or remove the tracing block.
2. Serve `frontend/index.html` behind something that proxies `/api/` to port 8000, or call the API directly.

### Deploying to a server (Linux VPS)

The same Compose setup works on any Linux VM (AWS, DigitalOcean, Hetzner, etc.):

1. Install Docker, copy the project over, and add your `.env`.
2. Run `docker compose up --build -d`.
3. Open only ports 80/443 in the firewall, and put a reverse proxy such as Caddy or nginx in front for HTTPS.
4. Do not expose Phoenix (port 6006) publicly.
5. Change the CORS origin in `agent.py` from `http://localhost:3000` to your domain.
6. `/sql` is unauthenticated, so add authentication or block it at the proxy.

### Common gotchas

- **Windows line endings**: if scripts fail with odd errors, check files didn't get CRLF endings (Git's `core.autocrlf` can cause this).
- **Port conflicts**: if 3000 or 6006 is taken, change the left side of the mapping in `docker-compose.yml` (e.g. `"3001:80"`).
- **Code changes**: rebuild with `docker compose up --build`, since code is copied into the image rather than mounted.

## API Reference

### `GET /models`

Returns the active model and all configured models.

```json
{
  "active": "groq-qwen",
  "models": {
    "groq-qwen": { "provider": "groq", "model": "qwen/qwen3.8-27b" }
  }
}
```

### `POST /ask`

Ask a natural-language question.

**Request**

```json
{
  "question": "Which books did Yale University Press publish?",
  "model": "groq-qwen"
}
```

`model` is optional; omit it to use the `active` model.

**Response**

```json
{
  "thought_process": "Filter books by publisher...",
  "sql": "SELECT title FROM books WHERE publisher = 'Yale University Press'",
  "answer": "Yale University Press published ...",
  "tool_calls": 1,
  "model": "groq-qwen"
}
```

`tool_calls` is the number of `query_database` calls the agent made.

**Errors**: `404` unknown model, `400` unknown provider, `500` model could not be built, `502` the model/agent call failed.

### `POST /sql`

Run a read-only query directly, bypassing the LLM (up to 100 rows).

```bash
curl -X POST http://localhost:8000/sql \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT count(*) FROM books"}'
```

```json
{ "columns": ["count(*)"], "rows": [[123]] }
```

Returns `400` for invalid or non-`SELECT` SQL.

> When running via Docker Compose, the API port is not published to the host. Reach these endpoints through nginx at `http://localhost:3000/api/...` (e.g. `/api/ask`), or add a `ports` mapping for `api`.

## Safety Notes

- Queries must be a single read-only SELECT or WITH statement. Subqueries, CTEs, joins, and UNION are allowed; multiple statements and writes are rejected.
- The database connection is opened read-only (`?mode=ro`).
- The agent tool returns at most 20 rows per call; `/sql` returns up to 100.
- CORS is limited to `http://localhost:3000` (GET and POST only).
- `/sql` is unauthenticated, so don't expose this stack publicly as-is.

## Tech Stack

FastAPI · LangChain (`create_agent`) · MCP (`mcp`, `langchain-mcp-adapters`) · SQLite · Groq / NVIDIA / OpenRouter · Arize Phoenix + OpenInference · nginx · uv · Docker

## License

Add a license of your choice.