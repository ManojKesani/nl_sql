"""db_id -> path/description. Per-db artifacts live in data/<db_id>/."""
from __future__ import annotations

import json
from pathlib import Path

from .config import settings

REG = settings.data_dir / "registry.json"


def _load() -> dict:
    return json.loads(REG.read_text(encoding="utf-8")) if REG.exists() else {}


def register(db_id: str, db_path, description: str = "") -> None:
    reg = _load()
    reg[db_id] = {"path": str(Path(db_path).resolve()), "description": description}
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    REG.write_text(json.dumps(reg, indent=2), encoding="utf-8")


def get(db_id: str) -> dict:
    reg = _load()
    if db_id not in reg:
        raise KeyError(f"Unknown db_id '{db_id}'. Registered: {list(reg)}")
    return reg[db_id]


def list_ids() -> list[str]:
    return list(_load())


def db_dir(db_id: str) -> Path:
    d = settings.data_dir / db_id
    d.mkdir(parents=True, exist_ok=True)
    return d

DEFAULT_CFG = {"model": None, "fallbacks": [], "escalate_to": None, "run_limit": 8}


def get_config(db_id: str) -> dict:
    p = db_dir(db_id) / "config.json"
    cfg = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {**DEFAULT_CFG, **cfg}


def set_config(db_id: str, **kw) -> dict:
    cfg = {**get_config(db_id), **kw}
    (db_dir(db_id) / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def describe_all() -> dict[str, str]:
    return {k: v.get("description", "") for k, v in _load().items()}