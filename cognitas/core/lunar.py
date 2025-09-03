from __future__ import annotations

from typing import Tuple

# You can customize these. 8-step cycle by default.
LUNAR_PHASES = [
    ("new", "🌑 New Moon"),
    ("first_quarter", "🌓 First Quarter"),
    ("full", "🌕 Full Moon"),,
    ("last_quarter", "🌗 Last Quarter"),
]

DEFAULT_CYCLE_STEPS = len(LUNAR_PHASES)

def announcement(idx: int) -> str:
    """Return a short message announcing the current lunar phase."""
    key, label = get_phase_by_index(idx)
    if key == "new":
        return f"{label} rises..."
    if key == "first_quarter":
        return f"{label} ascends."
    if key == "full":
        return f"{label} shines bright."
    if key == "last_quarter":
        return f"{label} wanes."
    return label

def get_phase_by_index(idx: int) -> Tuple[str, str]:
    phases = LUNAR_PHASES
    if not phases:
        return ("unknown", "○")
    i = idx % len(phases)
    return phases[i]

def advance(game, *, steps: int = 1):
    """
    Advance the lunar index by `steps`. Persisting is up to caller.
    """
    current = int(getattr(game, "lunar_index", 0) or 0)
    setattr(game, "lunar_index", (current + steps) % DEFAULT_CYCLE_STEPS)

def current(game) -> Tuple[str, str]:
    idx = int(getattr(game, "lunar_index", 0) or 0)
    return get_phase_by_index(idx)
