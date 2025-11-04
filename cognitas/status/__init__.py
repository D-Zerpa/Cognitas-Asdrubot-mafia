from __future__ import annotations
from typing import Dict, Type, Optional, Callable, Any

# ---- registry ----
_REGISTRY: Dict[str, "Type[Status]"] = {}

def register(name: str) -> Callable[[Type["Status"]], Type["Status"]]:
    key = name.lower().strip()
    def _wrap(cls: Type["Status"]) -> Type["Status"]:
        _REGISTRY[key] = cls
        return cls
    return _wrap

def get_state_cls(name: str) -> Optional["Type[Status]"]:
    return _REGISTRY.get((name or "").lower().strip())

def list_registered() -> Dict[str, "Type[Status]"]:
    return dict(_REGISTRY)

# ---- exported base ----
class Status:
    """
    Base class for a status effect. Subclasses override what they need.
    """
    name: str = "Status"
    type: str = "debuff"            # debuff|buff|neutral
    visibility: str = "public"      # public|private|hidden
    stack_policy: str = "refresh"   # none|refresh|add|multiple
    default_duration: int = 1       # ticks (phases)
    blocks: Dict[str, bool] = {}    # e.g. {"vote": True, "day_action": True}
    # vote_weight_delta: used by buffs/debuffs that modify voting (Sanctioned/DoubleVote)
    # If set, engine will compute weight from all active statuses
    # Example: +1 for DoubleVote (base 1 -> 2), -0.5 for Sanctioned
    vote_weight_delta: float = 0.0

    # lifecycle hooks
    def on_apply(self, game, uid: str, entry: dict) -> Optional[str]: return None
    def on_tick(self, game, uid: str, entry: dict, phase: str) -> Optional[str]: return None
    def on_expire(self, game, uid: str, entry: dict) -> Optional[str]: return None

    # action hook (optional redirection etc.)
    # return dict(action_allowed: bool, reason: Optional[str], redirect_to: Optional[str])
    def on_action(self, game, uid: str, entry: dict, action_kind: str, target_uid: Optional[str]) -> dict:
        return {"action_allowed": True, "reason": None, "redirect_to": None}
