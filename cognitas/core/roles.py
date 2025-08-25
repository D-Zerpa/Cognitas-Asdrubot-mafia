# cognitas/core/roles.py
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def _roles_path_for(profile: str | None) -> Path:
    profile = (profile or "default").lower()
    candidate = DATA_DIR / f"roles_{profile}.json"
    return candidate if candidate.exists() else (DATA_DIR / "roles_default.json")

def validate_roles(defn: dict) -> dict:
    if not isinstance(defn, dict) or "roles" not in defn or not isinstance(defn["roles"], list):
        raise ValueError("Invalid roles file: missing 'roles' array.")
    for r in defn["roles"]:
        r.setdefault("alignment", "Neutral")
        r.setdefault("notes", "")
    return defn

def load_roles(profile: str | None = None) -> dict:
    path = _roles_path_for(profile)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return validate_roles(data)


