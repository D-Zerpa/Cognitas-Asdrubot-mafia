from __future__ import annotations
from typing import Dict, Type, Optional, Callable

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
    vote_weight_delta: float = 0.0
    decrement_on: str = "always"
    
    # lifecycle hooks
    def on_apply(self, game, uid: str, entry: dict) -> Optional[str]: return None
    def on_tick(self, game, uid: str, entry: dict, phase: str) -> Optional[str]: return None
    def on_expire(self, game, uid: str, entry: dict) -> Optional[str]: return None

    # action hook (optional redirection etc.)
    # return dict(action_allowed: bool, reason: Optional[str], redirect_to: Optional[str])
    def on_action(self, game, uid: str, entry: dict, action_kind: str, target_uid: Optional[str]) -> dict:
        return {"action_allowed": True, "reason": None, "redirect_to": None}

# --- Block messages (UX) and registration API ---
BLOCK_MESSAGES: dict[str, str] = {
    "blocked_by:Jailed": "Estás encarcelado y no puedes actuar ahora.",
    "blocked_by:Paralyzed": "Estás paralizado y no puedes usar habilidades de día.",
    "blocked_by:Drowsiness": "Estás letárgico y no puedes usar habilidades de noche.",
    "blocked_by:Silenced": "Estás silenciado: no puedes hablar ni realizar esta acción.",
    "blocked_by:Wounded": "Estás herido y no puedes realizar acciones ahora mismo.",
    "blocked_by:Sanctioned": "Estás sancionado y tienes prohibida esta acción.",
    "blocked_by:Confusion": "Sufres confusión y no controlas tus acciones."
}

def get_block_message(reason: str) -> str:
    """Return a user-facing message for a block reason."""
    return BLOCK_MESSAGES.get(reason or "", "Un estado alterado impide esta acción.")

def register_block_messages(extra: dict[str, str]):
    """Allow expansions to add their own localized block messages."""
    BLOCK_MESSAGES.update(extra)
