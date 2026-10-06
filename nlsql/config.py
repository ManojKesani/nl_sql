"""Central settings. load_dotenv() runs BEFORE any os.getenv (fixes the old ordering bug)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path = ROOT / "data"
    models_file: Path = ROOT / "models.json"
    mcp_url: str = os.getenv("MCP_URL", "http://127.0.0.1:8001/mcp")
    # Empty string disables tracing. In Docker set PHOENIX_ENDPOINT=http://phoenix:6006/v1/traces
    phoenix_endpoint: str = os.getenv("PHOENIX_ENDPOINT", "")
    phoenix_project: str = os.getenv("PHOENIX_PROJECT", "nl-sql")
    query_timeout_s: float = float(os.getenv("QUERY_TIMEOUT_S", "5"))
    tool_row_limit: int = int(os.getenv("TOOL_ROW_LIMIT", "20"))
    api_row_limit: int = int(os.getenv("API_ROW_LIMIT", "100"))
    api_key: str = os.getenv("API_KEY", "")  # empty = auth disabled (dev only)
    cors_origins: tuple = tuple(os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","))


settings = Settings()