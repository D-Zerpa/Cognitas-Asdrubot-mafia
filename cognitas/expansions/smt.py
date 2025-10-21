from . import Expansion, register
from ..core import lunar

@register("smt")
@register("persona")
@register("megaten")
class SMTExpansion(Expansion):
    name = "smt"

    def on_phase_change(self, game_state, new_phase: str):
        # Advance the lunar cycle at the start of the Night phase
        if new_phase == "night":
            lunar.advance(game_state, steps=1)

    def banner_for_day(self, game_state):
        # Announce the current lunar phase at dawn
        _code, label = lunar.current(game_state)
        return f"{label}"
