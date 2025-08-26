import json, os, tempfile
from .state import game

def _atomic_write_json(path: str, data: dict, *, make_backup: bool = True):
    dirpath = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(dirpath, exist_ok=True)

    if make_backup and os.path.exists(path):
        try:
            bak = path + ".bak"
            if os.path.exists(bak):
                os.remove(bak)
            os.replace(path, bak)
        except Exception:
            pass

    fd, tmp_path = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=dirpath)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise
    


def load_state(path: str):
    # Try main file; if missing/corrupt, fallback to .bak
    data = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        try:
            with open(path + ".bak", "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    # A partir de aquí conserva tu lógica actual para hidratar 'game' desde 'data'
    game.players = data.get("players", {})
    game.votes = data.get("votes", {})
    game.day_channel_id = data.get("day_channel_id", None)
    game.admin_channel_id = data.get("admin_channel_id", None)
    game.default_day_channel_id = data.get("default_day_channel_id", None)
    game.game_over = data.get("game_over", False)
    game.current_day_number = data.get("current_day_number", 1)
    game.day_deadline_epoch = data.get("day_deadline_epoch")
    game.night_deadline_epoch = data.get("night_deadline_epoch")
    game.profile = data.get("profile", "default")
    game.roles_def = data.get("roles_def", {})
    # Si quieres re-indexar roles al cargar estado:
    try:
        roles_list = []
        if isinstance(game.roles_def, dict):
            roles_list = list(game.roles_def.get("roles") or [])
        elif isinstance(game.roles_def, list):
            roles_list = game.roles_def
        idx = {}
        for r in roles_list:
            if not isinstance(r, dict): continue
            keys = []
            for k in (r.get("code"), r.get("id"), r.get("name")):
                if isinstance(k, str) and k.strip():
                    keys.append(k.strip().upper())
            for a in (r.get("aliases") or []):
                if isinstance(a, str) and a.strip():
                    keys.append(a.strip().upper())
            for key in keys:
                idx[key] = r
        game.roles = idx
    except Exception:
        pass

    return data

def save_state(path: str):
    _atomic_write_json(path, {
        "players": game.players,
        "votes": game.votes,
        "day_channel_id": game.day_channel_id,
        "current_day_number": game.current_day_number,
        "day_deadline_epoch": game.day_deadline_epoch,
        "night_channel_id": game.night_channel_id,
        "night_deadline_epoch": game.night_deadline_epoch,
        "next_day_channel_id": game.next_day_channel_id,
        "night_actions": game.night_actions,
        "admin_log_channel_id": game.admin_log_channel_id,
        "default_day_channel_id": game.default_day_channel_id,
        "game_over": game.game_over
    })
