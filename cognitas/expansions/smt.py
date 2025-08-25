from . import Expansion

MOON_ORDER = ["New", "Waxing", "Full", "Waning"]

class SMTExpansion(Expansion):
    name = "smt"

    def on_phase_change(self, game_state, new_phase: str):
        current = getattr(game_state, "moon_phase", "New")
        try:
            idx = MOON_ORDER.index(current)
        except ValueError:
            idx = 0
        game_state.moon_phase = MOON_ORDER[(idx + 1) % len(MOON_ORDER)]
