import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def _roles_path_for(profile: str | None) -> Path:
    profile = (profile or "default").lower()
    candidate = DATA_DIR / f"roles_{profile}.json"
    return candidate if candidate.exists() else (DATA_DIR / "roles_default.json")

def load_roles(profile: str | None = None) -> dict:
    """
    Carga roles según profile.
    - Busca data/roles_{profile}.json
    - Fallback: data/roles_default.json
    """
    path = _roles_path_for(profile)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
