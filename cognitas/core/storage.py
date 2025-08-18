import json
from .state import game

def load_state(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    game.players = data.get("players", {})
    game.votes = data.get("votes", {})
    game.day_channel_id = data.get("day_channel_id", None)
    game.current_day_number = data.get("current_day_number", 1)
    game.day_deadline_epoch = data.get("day_deadline_epoch", None)
    game.admin_log_channel_id = data.get("admin_log_channel_id", None)
    game.default_day_channel_id = data.get("default_day_channel_id", None)
    game.game_over = data.get("game_over", False)

def save_state(path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "players": game.players,
            "votes": game.votes,
            "day_channel_id": game.day_channel_id,
            "current_day_number": game.current_day_number,
            "day_deadline_epoch": game.day_deadline_epoch,
            "admin_log_channel_id": game.admin_log_channel_id,
            "default_day_channel_id": game.default_day_channel_id,
            "game_over": game.game_over
        }, f, ensure_ascii=False, indent=2)