from __future__ import annotations

import json

from .. import registry
from ..db.introspect import profile_db, render_schema_card, save_profile


def run(db_id: str) -> dict:
    path = registry.get(db_id)["path"]
    p = profile_db(path)
    save_profile(p, registry.db_dir(db_id) / "profile.json")
    return p


def load_card(db_id: str, with_samples: bool = True) -> str:
    p = json.loads((registry.db_dir(db_id) / "profile.json").read_text(encoding="utf-8"))
    return render_schema_card(p, with_samples)