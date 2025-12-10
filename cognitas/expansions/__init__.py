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

    # ---- Easter Egg message loader ----
    memes: dict[str, str | list[str]] = {}

    # ---- Lifecycle / phase hooks ----
    async def on_phase_change(self, guild: Any, game_state, new_phase: str) -> None: pass
    def banner_for_day(self, game_state) -> Optional[str]: return None
    def banner_for_night(self, game_state) -> Optional[str]: return None

    # Optional hooks
    def on_game_start(self, game_state) -> None: ...
    def on_game_end(self, game_state, *, reason: Optional[str] = None) -> None: ...
    def on_player_death(self, game_state, uid: str, *, cause: str) -> None: ...
    def validate_setup(self, roles_def: Dict[str, Any]) -> None: ...
    def get_status_lines(self, game_state) -> list[str]: return []

    # Specific ability-related hooks
    async def on_action_commit(self,interaction: Any, game_state, actor_uid: str, target_uid: str | None, action_data: dict) -> None:
        """
        Called after a player successfully registers an action via /act.
        Useful for passive reactions like Watchers, Trackers or Oracles.
        """
        pass

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

def get_unique_profiles() -> list[str]:
    """
    Returns a list of unique canonical names from registered expansions.
    Deduplicates aliases by checking the class.
    """
    unique_classes = set(_EXPANSION_REGISTRY.values())
    # Sort by name for consistent UI
    return sorted([cls.name for cls in unique_classes if hasattr(cls, "name")])
    
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
    for mod in ("philosophers", "smt", "myexp", "persona3"):
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

