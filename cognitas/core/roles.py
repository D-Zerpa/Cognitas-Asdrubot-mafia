import json

def load_roles(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("roles.json must be an object {code: {...}}")
            normalized = {}
            for k, v in data.items():
                code = str(k).upper()
                v = v or {}
                v.setdefault("name", code)
                v.setdefault("faction", "NEUTRAL")
                v.setdefault("defaults", {})
                v["defaults"].setdefault("vote_weight_base", 1)
                normalized[code] = v
            return normalized
    except FileNotFoundError:
        raise FileNotFoundError("roles.json not found next to bot.py")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid roles.json (JSON): {e}")
