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



log = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Atomic JSON writer (kept from your original, great for integrity)
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
    """
    Resolve to an absolute path.
    If not provided, use cfg.STATE_PATH (which is already absolute in our config).
    """
    p = Path(path) if path else Path(cfg.STATE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def _ensure_defaults():
    """
    Make sure required attributes exist on 'game' to avoid AttributeError.
    """
    defaults = {
        "players": {},
        "votes": {},
        "day_channel_id": None,
        "night_channel_id": None,
        "next_day_channel_id": None,
        "admin_channel_id": None,
        "admin_log_channel_id": None,
        "default_day_channel_id": None,
        "game_over": False,
        "current_day_number": 1,
        "day_deadline_epoch": None,
        "night_deadline_epoch": None,
        "profile": "default",
        "roles_def": {},
        # Non-serializable runtime attrs (timers) should exist but won't be saved
        "day_timer_task": None,
        "night_timer_task": None,
        # Night actions container if you use it
        "night_actions": {},
    }
    for k, v in defaults.items():
        if not hasattr(game, k):
            setattr(game, k, v)

    # Ensure a concrete expansion object exists (safe fallback to base)
    try:
        if not hasattr(game, "expansion") or game.expansion is None:
            from ..expansions import load_expansion_instance
            game.expansion = load_expansion_instance(getattr(game, "profile", "default"))

        # Status system containers
        if not hasattr(game, "status_map"): game.status_map = {}
        if not hasattr(game, "status_log"): game.status_log = []

    except Exception:
        # Avoid breaking load paths if expansion resolution fails
        pass


def _rehydrate_roles_index():
    """
    Re-index roles if roles_def exists (compatible with your original logic).
    """
    try:
        from .game import _build_roles_index
        game.roles = _build_roles_index(getattr(game, "roles_def", {}) or {})
    except Exception:
        game.roles = {}


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------
def load_state(path: str | Path | None = None) -> Dict[str, Any]:
    """
    Synchronous load. Safe to call without await (e.g., in bot.setup_hook()).
    Will fall back to reading *.bak if main file is corrupt/missing.
    """
    _ensure_defaults()
    eff_path = _effective_path(path)

    data: Dict[str, Any] = {}
    try:
        with open(eff_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e_main:
        # Try backup
        try:
            with open(eff_path + ".bak", "r", encoding="utf-8") as f:
                data = json.load(f)
            log.warning("[storage] Main state file failed, loaded from backup.")
        except Exception as e_bak:
            # Do not return empty dict on total failure.
            # Fail hard to prevent overwriting data with an empty state.
            log.critical(f"[storage] FATAL: Could not load state or backup. {e_main} | {e_bak}")
            raise RuntimeError("State load failed. Check state.json integrity manually.")

    # --- Hydrate 'game' from data (keep keys consistent with save_state) ---
    game.players = data.get("players", {})
    game.votes = data.get("votes", {})

    game.day_channel_id = data.get("day_channel_id")
    # If you use a single channel for both phases, fall back Night to Day
    game.night_channel_id = data.get("night_channel_id", data.get("day_channel_id"))

    game.next_day_channel_id = data.get("next_day_channel_id")

    # Keep both keys supported; prefer admin_log_channel_id if present
    game.admin_log_channel_id = data.get("admin_log_channel_id", data.get("admin_channel_id"))
    game.admin_channel_id = data.get("admin_channel_id")
    game.phase = data.get("phase","day")
    game.default_day_channel_id = data.get("default_day_channel_id")
    game.game_over = data.get("game_over", False)
    game.current_day_number = data.get("current_day_number", 1)
    game.lunar_index = data.get("lunar_index", 0)

    game.day_deadline_epoch = data.get("day_deadline_epoch")
    game.night_deadline_epoch = data.get("night_deadline_epoch")

    game.profile = data.get("profile", "default")
    game.roles_def = data.get("roles_def", {})

    game.night_actions = data.get("night_actions", {})
    game.day_actions = data.get("day_actions", {})

    # Status engine persistence
    game.status_map = data.get("status_map", {})
    game.status_log = data.get("status_log", [])

    # Re-index roles (compatible with SMT origin files)
    _rehydrate_roles_index()

    return data


async def save_state(path: str | Path | None = None):
    """
    Async save to avoid blocking the event loop. Uses the same absolute path
    resolution as load_state. Writes atomically and keeps a .bak.
    """
    _ensure_defaults()
    eff_path = _effective_path(path)

    # Build serializable snapshot
    payload = {
        "players": game.players,
        "votes": game.votes,
        "day_channel_id": game.day_channel_id,
        "night_channel_id": game.night_channel_id,
        "next_day_channel_id": game.next_day_channel_id,
        "admin_log_channel_id": game.admin_log_channel_id,
        "admin_channel_id": game.admin_channel_id,
        "default_day_channel_id": game.default_day_channel_id,
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
    }

    # Do the write off-thread to keep the loop snappy
    def _write():
        _atomic_write_json(eff_path, payload, make_backup=True)

    try:
        await asyncio.to_thread(_write)
    except Exception as e:
        log.info(f"[storage] Failed to write state to {eff_path}: {e!r}")