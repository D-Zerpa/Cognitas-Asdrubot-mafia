from __future__ import annotations
from . import Expansion, register

@register("default")
@register("base")
class PhilosophersExpansion(Expansion):
    """
    Default / Base expansion (Philosophers' Game).
    Contains no global mechanics or clocks.
    """
    name = "base"

    # Example of optional flavor you could later add:
    # def banner_for_day(self, game_state):
    #     return "🗳️ A new day rises over the Agora."
