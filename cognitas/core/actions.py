# cognitas/core/actions.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional
from .state import game

PHASE_DAY = "day"
PHASE_NIGHT = "night"
PHASES = {PHASE_DAY, PHASE_NIGHT}


# ------------ Phase helpers ------------

def _normalize_phase(phase: str | None) -> str:
    p = (phase or "").strip().lower()
    return p if p in PHASES else PHASE_NIGHT  # default to night for legacy parity


def current_cycle_number(phase: str | None = None) -> int:
    """
    Returns the logical counter for the given phase.
    Convention:
      - Day N is "current_day_number".
      - Night N follows Day N (same N).
    When phase is omitted: use current game.phase to decide.
    """
    p = _normalize_phase(phase or getattr(game, "phase", PHASE_DAY))
    day_no = int(getattr(game, "current_day_number", 1) or 1)
    if p == PHASE_DAY:
        # During night we still consider "current day" to be the same number.
        return max(1, day_no)
    # night
    return max(1, day_no)


# ------------ Actions storage (per phase) ------------

def _ensure_actions_dict(attr: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Ensures an actions dict exists in game.<attr> and normalizes to:
      { "<N>": { "<uid>": { ...action dict... } } }
    Accepts legacy lists and normalizes them.
    """
    na = getattr(game, attr, None)
    if na is None:
        na = {}
        setattr(game, attr, na)
    if isinstance(na, dict):
        normalized: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for k, v in na.items():
            if isinstance(v, list):
                bucket: Dict[str, Dict[str, Any]] = {}
                for item in v:
                    if isinstance(item, dict):
                        uid = str(item.get("uid") or item.get("user_id") or "")
                        if uid:
                            bucket[uid] = item
                normalized[str(k)] = bucket
            elif isinstance(v, dict):
                inner: Dict[str, Dict[str, Any]] = {}
                for uid, act in v.items():
                    if isinstance(act, dict):
                        inner[str(uid)] = act
                normalized[str(k)] = inner
        setattr(game, attr, normalized)
        return normalized
    setattr(game, attr, {})
    return getattr(game, attr)


def _attr_for_phase(phase: str) -> str:
    p = _normalize_phase(phase)
    return "day_actions" if p == PHASE_DAY else "night_actions"


def _flag_for_phase(phase: str) -> str:
    p = _normalize_phase(phase)
    return "day_act" if p == PHASE_DAY else "night_act"


def get_action_bucket(phase: str, number: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    """
    Returns bucket for given phase & number: mapping uid -> action dict.
    """
    p = _normalize_phase(phase)
    attr = _attr_for_phase(p)
    store = _ensure_actions_dict(attr)
    n = number if number is not None else current_cycle_number(p)
    return store.get(str(n), {})


def get_logs(phase: str, number: Optional[int] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns action dicts for the given phase+number, optionally filtered by user_id.
    """
    bucket = get_action_bucket(phase, number)
    out: List[Dict[str, Any]] = []
    for uid, act in bucket.items():
        if user_id and str(uid) != str(user_id):
            continue
        if isinstance(act, dict):
            row = dict(act)
            row.setdefault("uid", str(uid))
            out.append(row)
    return out


def get_user_logs_all(phase: str, user_id: str) -> List[Tuple[int, Dict[str, Any]]]:
    """
    Returns list of (number, action_dict) for the given user across ALL numbers in the given phase.
    Sorted by number asc.
    """
    p = _normalize_phase(phase)
    attr = _attr_for_phase(p)
    store = _ensure_actions_dict(attr)
    rows: List[Tuple[int, Dict[str, Any]]] = []
    for k, bucket in store.items():
        try:
            n = int(k)
        except Exception:
            continue
        if not isinstance(bucket, dict):
            continue
        act = bucket.get(str(user_id))
        if isinstance(act, dict):
            row = dict(act)
            row.setdefault("uid", str(user_id))
            rows.append((n, row))
    rows.sort(key=lambda t: t[0])
    return rows


# ------------ Who can act / who acted ------------

def actors_for_phase(phase: str) -> List[str]:
    """
    Returns uids of alive players who are allowed to act in the given phase.
    Policy: player.alive == True AND player.flags[day_act/night_act] == True.
    """
    p = _normalize_phase(phase)
    flag_name = _flag_for_phase(p)
    players = getattr(game, "players", {}) or {}
    out: List[str] = []
    for uid, pdata in players.items():
        if not pdata or not pdata.get("alive", True):
            continue
        flags = pdata.get("flags", {}) or {}
        if bool(flags.get(flag_name, False)):
            out.append(uid)
    return out


def acted_uids(phase: str, number: Optional[int] = None) -> List[str]:
    """
    Returns uids with an action recorded for given phase+number.
    """
    bucket = get_action_bucket(phase, number)
    return sorted(bucket.keys())
