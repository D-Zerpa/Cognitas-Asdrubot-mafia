from __future__ import annotations

import time
import logging
from typing import Any, Dict, List, Tuple, Optional
from .state import game
from ..status import engine as SE

log = logging.getLogger(__name__)

PHASE_DAY = "day"
PHASE_NIGHT = "night"
PHASES = {PHASE_DAY, PHASE_NIGHT}

# ------------ Phase helpers ------------

def _normalize_phase(phase: str | None) -> str:
    p = (phase or "").strip().lower()
    return p if p in PHASES else PHASE_NIGHT

def current_cycle_number(phase: str | None = None) -> int:
    p = _normalize_phase(phase or getattr(game, "phase", PHASE_DAY))
    day_no = int(getattr(game, "current_day_number", 1) or 1)
    return max(1, day_no)

# ------------ Actions storage (per phase) ------------

def _ensure_actions_dict(attr: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
    na = getattr(game, attr, None)
    if na is None:
        na = {}
        setattr(game, attr, na)
    if isinstance(na, dict):
        # Ensure struct is Dict[Cycle, Dict[Uid, Record]]
        return na
    setattr(game, attr, {})
    return getattr(game, attr)

def _attr_for_phase(phase: str) -> str:
    p = _normalize_phase(phase)
    return "day_actions" if p == PHASE_DAY else "night_actions"

def _flag_for_phase(phase: str) -> str:
    p = _normalize_phase(phase)
    return "day_act" if p == PHASE_DAY else "night_act"

def get_action_bucket(phase: str, number: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    p = _normalize_phase(phase)
    attr = _attr_for_phase(p)
    store = _ensure_actions_dict(attr)
    n = number if number is not None else current_cycle_number(p)
    return store.get(str(n), {})

def get_logs(phase: str, number: Optional[int] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
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

_RESERVED_ACTION_KEYS = {"uid", "action", "target", "at"}

def _ensure_action_store(phase: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
    p = _normalize_phase(phase)
    attr = _attr_for_phase(p)
    store = _ensure_actions_dict(attr)
    return store

def enqueue_action(
    game,
    actor_uid: str,
    action_kind: str,                  
    target_uid: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    number: Optional[int] = None,
    action_name: str = "act",
) -> Dict[str, Any]:
    
    if action_kind not in ("day_action", "night_action"):
        return {"ok": False, "reason": f"invalid_action_kind:{action_kind}"}

    phase_norm = PHASE_DAY if action_kind == "day_action" else PHASE_NIGHT

    # Gate check
    chk = SE.check_action(game, actor_uid, action_kind, target_uid)
    if not chk.get("allowed", True):
        return {"ok": False, "reason": chk.get("reason") or "blocked"}

    # Cycle number
    if number is None:
        number = current_cycle_number(phase_norm)

    # 1. Build Record
    record: Dict[str, Any] = {
        "uid": str(actor_uid),
        "action": str((payload or {}).get("action") or action_name),
        "target": (str(target_uid) if target_uid else None),
        "at": int(time.time()),
    }

    # 2. Merge Payload (CRITICAL: This adds 'note')
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k not in _RESERVED_ACTION_KEYS:
                record[k] = v

    # 3. Store
    store = _ensure_action_store(phase_norm)
    bucket = store.setdefault(str(number), {})
    
    # Check replacement
    replaced = str(actor_uid) in bucket
    bucket[str(actor_uid)] = record

    return {"ok": True, "number": number, "record": record, "replaced": replaced}

# ------------ Who can act / who acted ------------

def actors_for_phase(phase: str) -> List[str]:
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
    bucket = get_action_bucket(phase, number)
    return sorted(bucket.keys())