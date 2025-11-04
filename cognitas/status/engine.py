from __future__ import annotations
import random
from typing import Optional, Dict, Any, List, Tuple
from . import get_state_cls, list_registered, Status

# game.status_map structure:
# { uid: { state_name: {"remaining": int, "stacks": int, "source": str|"system"|"GM",
#                       "meta": {...}, "visibility": "public|private|hidden"} } }

def _ensure_maps(game):
    if not hasattr(game, "status_map") or not isinstance(game.status_map, dict):
        game.status_map = {}
    if not hasattr(game, "status_log") or not isinstance(game.status_log, list):
        game.status_log = []

def list_active(game, uid: str) -> Dict[str, dict]:
    _ensure_maps(game)
    return game.status_map.get(uid, {}).copy()

def has(game, uid: str, name: str) -> bool:
    return name.lower().strip() in (game.status_map.get(uid, {}) if hasattr(game, "status_map") else {})

def apply(game, uid: str, name: str, *, source: Optional[str] = "GM",
          duration: Optional[int] = None, meta: Optional[dict] = None) -> Tuple[bool, Optional[str]]:
    """
    Returns (applied: bool, banner_text: Optional[str for DM/public depending on visibility])
    """
    _ensure_maps(game)
    cls = get_state_cls(name)
    if not cls:
        return False, None
    state = cls()
    dur = int(duration if duration is not None else state.default_duration)
    if dur <= 0:
        dur = 1

    per_user = game.status_map.setdefault(uid, {})
    key = state.name.lower()

    # stacking policy (global default: refresh)
    if key in per_user:
        entry = per_user[key]
        if state.stack_policy == "refresh":
            entry["remaining"] = dur
            entry["stacks"] = 1
        elif state.stack_policy == "add":
            entry["remaining"] += dur
        elif state.stack_policy == "multiple":
            entry["stacks"] += 1
            entry["remaining"] = max(entry["remaining"], dur)
        else:  # none -> ignore
            pass
    else:
        per_user[key] = entry = {
            "remaining": dur,
            "stacks": 1,
            "source": source or "GM",
            "meta": meta or {},
            "visibility": getattr(state, "visibility", "public"),
            "type": getattr(state, "type", "debuff"),
        }

    banner = state.on_apply(game, uid, per_user[key]) or None
    _audit(game, f"APPLY {state.name} to {uid} (dur={per_user[key]['remaining']}, stacks={per_user[key]['stacks']})")
    return True, banner

def heal(game, uid: str, name: Optional[str] = None, *, all_: bool = False) -> List[str]:
    """
    Removes status(es). Returns list of banners to announce (expire messages).
    If all_=True remove all; otherwise remove only given name.
    """
    _ensure_maps(game)
    banners: List[str] = []
    if uid not in game.status_map:
        return banners
    if all_:
        to_remove = list(game.status_map[uid].keys())
    else:
        if not name:
            return banners
        to_remove = [name.lower().strip()]
    for key in to_remove:
        entry = game.status_map[uid].get(key)
        if not entry:
            continue
        st_cls = get_state_cls(key)
        st = st_cls() if st_cls else None
        if st:
            b = st.on_expire(game, uid, entry)
            if b:
                banners.append(b)
        del game.status_map[uid][key]
        _audit(game, f"HEAL {key} from {uid}")
    if not game.status_map[uid]:
        del game.status_map[uid]
    return banners

def tick(game, phase: str) -> List[Tuple[str, str]]:
    """
    Decrement remaining and resolve per-phase. Returns list of (uid, banner_text) to announce.
    Phase values: "day" or "night".
    """
    _ensure_maps(game)
    banners: List[Tuple[str, str]] = []
    # collect expirations & on_tick banners
    expirations: List[Tuple[str, str]] = []
    for uid, effects in list(game.status_map.items()):
        for key, entry in list(effects.items()):
            st_cls = get_state_cls(key)
            state = st_cls() if st_cls else None
            # Resolution timing: fire on_tick first
            if state:
                tb = state.on_tick(game, uid, entry, phase)
                if tb:
                    banners.append((uid, tb))
            # decrement
            entry["remaining"] = max(0, int(entry.get("remaining", 0)) - 1)
            if entry["remaining"] == 0:
                # expire
                eb = state.on_expire(game, uid, entry) if state else None
                if eb:
                    expirations.append((uid, eb))
                del effects[key]
                _audit(game, f"EXPIRE {key} on {uid}")
        if not effects:
            del game.status_map[uid]
    banners.extend(expirations)
    return banners

def check_action(game, uid: str, action_kind: str, target_uid: Optional[str] = None) -> dict:
    """
    Returns {"allowed": bool, "reason": Optional[str], "redirect_to": Optional[str]}
    Combines all active statuses; any block wins.
    """
    _ensure_maps(game)
    entry_map = game.status_map.get(uid, {})
    # init result
    res = {"allowed": True, "reason": None, "redirect_to": None}
    # blocks & on_action
    for key, entry in entry_map.items():
        st_cls = get_state_cls(key)
        state = st_cls() if st_cls else None
        if not state:
            continue
        # static blocks by action_kind
        if state.blocks.get(action_kind, False):
            res["allowed"] = False
            res["reason"] = f"blocked_by:{state.name}"
            return res
        # dynamic hook (confusion may redirect)
        hook = state.on_action(game, uid, entry, action_kind, target_uid)
        if not hook.get("action_allowed", True):
            res["allowed"] = False
            res["reason"] = hook.get("reason")
            return res
        if hook.get("redirect_to"):
            res["redirect_to"] = hook["redirect_to"]
    return res

def compute_vote_weight(game, uid: str, base: float = 1.0) -> float:
    """
    Adds up vote deltas from active statuses (e.g., +1 for DoubleVote, -0.5 per Sanction).
    Clamp at 0..max reasonable (e.g., 4).
    """
    _ensure_maps(game)
    weight = base
    for key, entry in game.status_map.get(uid, {}).items():
        st_cls = get_state_cls(key)
        st = st_cls() if st_cls else None
        if not st:
            continue
        # stacking: apply per stack
        delta = getattr(st, "vote_weight_delta", 0.0) * max(1, int(entry.get("stacks", 1)))
        weight += delta
    if weight < 0: weight = 0.0
    if weight > 4: weight = 4.0
    return weight

def _audit(game, text: str):
    log = getattr(game, "status_log", None)
    if isinstance(log, list):
        log.append(text)
        if len(log) > 200:
            del log[:len(log)-200]

# utility for Confusion
def pick_random_alive(game, *, exclude: Optional[str] = None) -> Optional[str]:
    players = [uid for uid, info in getattr(game, "players", {}).items()
               if info.get("alive", True)]
    if exclude and exclude in players:
        players.remove(exclude)
    return random.choice(players) if players else None
