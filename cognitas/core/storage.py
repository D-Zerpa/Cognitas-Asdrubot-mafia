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

    # hidrata 'game'
    game.players = data.get("players", {})
    game.votes = data.get("votes", {})
    game.day_channel_id = data.get("day_channel_id")
    game.admin_channel_id = data.get("admin_channel_id")
    game.default_day_channel_id = data.get("default_day_channel_id")
    game.game_over = data.get("game_over", False)
    game.current_day_number = data.get("current_day_number", 1)
    game.day_deadline_epoch = data.get("day_deadline_epoch")
    game.night_deadline_epoch = data.get("night_deadline_epoch")
    game.profile = data.get("profile", "default")
    game.roles_def = data.get("roles_def", {})

    # Re-index roles (por si el JSON viene de SMT)
    try:
        from .game import _build_roles_index
        game.roles = _build_roles_index(game.roles_def)
    except Exception:
        game.roles = {}

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
