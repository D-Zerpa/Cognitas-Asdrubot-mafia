# cognitas/core/storage.py
from __future__ import annotations

import json
import os
import tempfile
import asyncio
from pathlib import Path
from typing import Any, Dict
import logging
from .. import config as cfg
from .state import game
from ..expansions import load_expansion_instance

log = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Atomic JSON writer
# -------------------------------------------------------------------
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

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _effective_path(path: str | Path | None) -> str:
    p = Path(path) if path else Path(cfg.STATE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)

def _ensure_defaults():
    defaults = {
        "players": {},
        "votes": {},
        "game_channel_id": None,
        "admin_channel_id": None,
        "admin_log_channel_id": None,
        "default_game_channel_id": None,
        "game_over": False,
        "current_day_number": 1,
        "day_deadline_epoch": None,
        "night_deadline_epoch": None,
        "profile": "default",
        "roles_def": {},
        "day_timer_task": None,
        "night_timer_task": None,
        "night_actions": {},
        # --- NUEVO ---
        "infra": {},      # Datos de infraestructura (roles, canales)
        "tzclocks": {},   # Relojes de zona horaria
        # -------------
    }
    for k, v in defaults.items():
        if not hasattr(game, k):
            setattr(game, k, v)

    try:
        if not hasattr(game, "expansion") or game.expansion is None:
            game.expansion = load_expansion_instance(getattr(game, "profile", "default"))
        if not hasattr(game, "status_map"): game.status_map = {}
        if not hasattr(game, "status_log"): game.status_log = []
    except Exception:
        pass

def _rehydrate_roles_index():
    try:
        from .game import _build_roles_index
        game.roles = _build_roles_index(getattr(game, "roles_def", {}) or {})
    except Exception:
        game.roles = {}

# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------
def load_state(path: str | Path | None = None) -> Dict[str, Any]:
    _ensure_defaults()
    eff_path = _effective_path(path)

    data: Dict[str, Any] = {}
    try:
        with open(eff_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e_main:
        try:
            with open(eff_path + ".bak", "r", encoding="utf-8") as f:
                data = json.load(f)
            log.warning("[storage] Main state file failed, loaded from backup.")
        except Exception as e_bak:
            log.critical(f"[storage] FATAL: Could not load state. {e_main} | {e_bak}")
            raise RuntimeError("State load failed check state.json integrity.")

    # Hydrate game object
    game.players = data.get("players", {})
    game.votes = data.get("votes", {})
    game.game_channel_id = data.get("game_channel_id") or data.get("day_channel_id")
    game.admin_log_channel_id = data.get("admin_log_channel_id", data.get("admin_channel_id"))
    game.admin_channel_id = data.get("admin_channel_id")
    game.phase = data.get("phase","day")
    game.default_game_channel_id = data.get("default_game_channel_id") or data.get("default_day_channel_id")
    game.game_over = data.get("game_over", False)
    game.current_day_number = data.get("current_day_number", 1)
    game.lunar_index = data.get("lunar_index", 0)
    game.day_deadline_epoch = data.get("day_deadline_epoch")
    game.night_deadline_epoch = data.get("night_deadline_epoch")
    game.profile = data.get("profile", "default")
    try:
        game.expansion = load_expansion_instance(game.profile)
        log.info(f"[storage] Expansion rehydrated: {getattr(game.expansion, 'name', 'None')}")
    except Exception as e:
        log.error(f"[storage] Failed to rehydrate expansion '{game.profile}': {e}")
    
    game.roles_def = data.get("roles_def", {})
    game.night_actions = data.get("night_actions", {})
    game.day_actions = data.get("day_actions", {})
    game.status_map = data.get("status_map", {})
    game.status_log = data.get("status_log", [])
    game.infra = data.get("infra", {})
    game.tzclocks = data.get("tzclocks", {})

    # ------------------------------------------

    _rehydrate_roles_index()
    return data

async def save_state(path: str | Path | None = None):
    _ensure_defaults()
    eff_path = _effective_path(path)

    payload = {
        "players": game.players,
        "votes": game.votes,
        "game_channel_id": game.game_channel_id,  # GUARDAR NUEVO NOMBRE
        "admin_log_channel_id": game.admin_log_channel_id,
        "admin_channel_id": game.admin_channel_id,
        "default_game_channel_id": game.default_game_channel_id,
        "admin_log_channel_id": game.admin_log_channel_id,
        "admin_channel_id": game.admin_channel_id,
        "game_over": game.game_over,
        "current_day_number": game.current_day_number,
        "day_deadline_epoch": game.day_deadline_epoch,
        "night_deadline_epoch": game.night_deadline_epoch,
        "phase": getattr(game, "phase", "day"),
        "profile": getattr(game, "profile", "default"),
        "roles_def": getattr(game, "roles_def", {}),
        "night_actions": getattr(game, "night_actions", {}),
        "day_actions": getattr(game, "day_actions", {}),
        "lunar_index": getattr(game, "lunar_index", 0),
        "status_map": getattr(game, "status_map", {}),
        "status_log": getattr(game, "status_log", []),
        
        # --- GUARDAR INFRAESTRUCTURA Y TIMEZONES ---
        "infra": getattr(game, "infra", {}),
        "tzclocks": getattr(game, "tzclocks", {}),
        # -------------------------------------------
    }

    def _write():
        _atomic_write_json(eff_path, payload, make_backup=True)

    try:
        await asyncio.to_thread(_write)
    except Exception as e:
        log.info(f"[storage] Failed to write state to {eff_path}: {e!r}")