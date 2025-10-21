from __future__ import annotations
from typing import Optional, Any, Dict

class Expansion:
    """
    Base interface for all game expansions.
    Each expansion can override hooks to modify behavior
    during specific phases or lifecycle events.
    """
    name: str = "base"

    # ---- Game lifecycle / phase hooks ----
    def on_phase_change(self, game_state, new_phase: str) -> None:
        """
        Triggered when the game transitions into a new phase
        ('day' or 'night').
        Use this to progress any expansion-specific counters or clocks.
        """
        return

    def banner_for_day(self, game_state) -> Optional[str]:
        """
        If this returns a string, the core will announce it at
        the start of a Day phase.
        Use this for things like lunar cycles, global effects, etc.
        """
        return None

    # ---- Optional hooks (do nothing by default) ----
    def on_game_start(self, game_state) -> None: ...
    def on_game_end(self, game_state, *, reason: Optional[str] = None) -> None: ...
    def on_player_death(self, game_state, uid: str, *, cause: str) -> None: ...
    def validate_setup(self, roles_def: Dict[str, Any]) -> None: ...


    _EXPANSION_REGISTRY = {}

    def register(name: str):
        """Decorator to register an expansion by profile name."""
        def _wrap(cls):
            _EXPANSION_REGISTRY[name.lower()] = cls
            return cls
        return _wrap

    def get_registered(profile: str):
        return _EXPANSION_REGISTRY.get((profile or "").lower())