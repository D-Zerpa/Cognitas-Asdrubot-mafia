from __future__ import annotations
from typing import Optional, Any, Dict, Type, Callable
from importlib import import_module
import pkgutil as _pkgutil


class Expansion:
    """
    Base interface for all game expansions.
    Expansions can override lifecycle/phase hooks.
    """
    name: str = "base"

    # ---- Lifecycle / phase hooks ----
    def on_phase_change(self, game_state, new_phase: str) -> None: ...
    def banner_for_day(self, game_state) -> Optional[str]: return None

    # Optional hooks
    def on_game_start(self, game_state) -> None: ...
    def on_game_end(self, game_state, *, reason: Optional[str] = None) -> None: ...
    def on_player_death(self, game_state, uid: str, *, cause: str) -> None: ...
    def validate_setup(self, roles_def: Dict[str, Any]) -> None: ...

# ---- Module-level registry ----
_EXPANSION_REGISTRY: Dict[str, Type[Expansion]] = {}

def register(name: str) -> Callable[[Type[Expansion]], Type[Expansion]]:
    """Decorator to register an expansion by profile name."""
    key = (name or "").lower().strip()
    def _wrap(cls: Type[Expansion]) -> Type[Expansion]:
        _EXPANSION_REGISTRY[key] = cls
        return cls
    return _wrap

def get_registered(profile: str):
    return _EXPANSION_REGISTRY.get((profile or "").lower().strip())


# ---- Utilities for discovery ----
def list_registered_keys() -> list[str]:
    """Return registered expansion keys (ensure discovery first)."""
    _auto_import_all()
    return sorted(_EXPANSION_REGISTRY.keys())

def _auto_import_all() -> None:
    """
    Import known expansion modules so their @register decorators run.
    You can keep this static list or do pkgutil discovery.
    """
    for mod in ("philosophers", "smt", "myexp"):
        try:
            import_module(f".{mod}", __name__)
        except Exception:
            pass


def load_expansion_instance(profile: str) -> Optional[Expansion]:
    """
    Factory function to instantiate an expansion by profile name.
    Falls back to 'default' or 'base' if not found.
    """
    cls = get_registered(profile)
    if not cls:
        cls = get_registered("default") or get_registered("base")
    return cls() if cls else None

# Ensure registry is populated on package import
_auto_import_all()

