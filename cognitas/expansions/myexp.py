from __future__ import annotations
from . import Expansion, register
from ..status import register_block_messages


@register("myexp")
class MyExpansion(Expansion):
    """
    Skeleton for a new expansion.
    Implement hooks you actually need; others can be left out.
    """
    name = "myexp"

    def on_phase_change(self, game_state, new_phase: str) -> None:
        # Advance global clocks/effects here if needed
        pass

    def banner_for_day(self, game_state):
        # Return a string to announce every dawn, or None
        # return "✨ A new omen rises…"
        return None

    register_block_messages({"blocked_by:MoonCurse": "The moon ritual prevents that action tonight."})

    # Optional:
    # def on_game_start(self, game_state): ...
    # def on_game_end(self, game_state, *, reason=None): ...
    # def on_player_death(self, game_state, uid: str, *, cause: str): ...
    # def validate_setup(self, roles_def): ...