from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple, Optional
from .state import game
from ..status import engine as SE

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

# ------------ Centralized enqueue (defense-in-depth) ------------

# Keys we build in the canonical action record (do not allow payload to overwrite them)
_RESERVED_ACTION_KEYS = {"uid", "action", "target", "at"}

def _ensure_action_store(phase: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Ensure the phase store exists and has the canonical structure:
        { "<N>": { "<uid>": action_record } }
    Returns the store mapping.
    """
    p = _normalize_phase(phase)
    attr = _attr_for_phase(p)
    store = _ensure_actions_dict(attr)  # leverage the normalizer/safety net
    return store

def enqueue_action(
    game,
    actor_uid: str,
    action_kind: str,                  # "day_action" | "night_action"
    target_uid: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,  # e.g. {"action": "protect", "note": "..."}
    number: Optional[int] = None,
    action_name: str = "act",
) -> Dict[str, Any]:
    """
    Insert an action into the canonical store, with a second gate check.
    Returns:
        {"ok": True, "number": <int>, "record": {...}} on success
        {"ok": False, "reason": "<blocked_by:StatusName | message>"} on failure
    """
    if action_kind not in ("day_action", "night_action"):
        return {"ok": False, "reason": f"invalid_action_kind:{action_kind}"}

    phase_norm = PHASE_DAY if action_kind == "day_action" else PHASE_NIGHT

    # Gate re-check (defense-in-depth)
    chk = SE.check_action(game, actor_uid, action_kind, target_uid)
    if not chk.get("allowed", True):
        return {"ok": False, "reason": chk.get("reason") or "blocked"}

    # Resolve logical number
    if number is None:
        number = current_cycle_number(phase_norm)

    # Canonical action record
    record: Dict[str, Any] = {
        "uid": str(actor_uid),
        "action": str((payload or {}).get("action") or action_name),
        "target": (str(target_uid) if target_uid else None),
        "at": int(time.time()),
    }
    # Merge additional metadata (without overriding reserved keys)
    safe_payload = {}
    if isinstance(payload, dict):
        # Allow only simple types to be serialized safely
        for k, v in payload.items():
            if k not in _RESERVED_ACTION_KEYS and isinstance(v, (str, int, float, bool, type(None))):
                safe_payload[k] = v

    # Insert into store
    store = _ensure_action_store(phase_norm)
    bucket = store.setdefault(str(number), {})
    bucket[str(actor_uid)] = record

    return {"ok": True, "number": number, "record": record}

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
