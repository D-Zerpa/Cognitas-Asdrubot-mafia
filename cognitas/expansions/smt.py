# cognitas/expansions/smt.py
from . import Expansion

MOON_ORDER = ["Nueva", "Creciente", "Llena", "Menguante"]

class SMTExpansion(Expansion):
    name = "smt"

    def __init__(self):
        self._idx = 0  # puedes persistir en game_state si quieres

    def on_phase_change(self, game_state, new_phase: str):
        # avanzar ciclo en cada cambio de fase
        self._idx = (self._idx + 1) % len(MOON_ORDER)
        phase = MOON_ORDER[self._idx]
        game_state.moon_phase = phase  # persistido en tu GameState si lo guardas
