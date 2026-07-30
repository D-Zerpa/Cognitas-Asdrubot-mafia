from typing import Optional, TYPE_CHECKING
from cognitas.expansions.base import BaseExpansion

if TYPE_CHECKING:
    from cognitas.core.state import GameState

class ExpansionGimmick(BaseExpansion):
    """
    Shin Megami Tensei expansion featuring an isolated, self-contained lunar cycle system.
    Phases: Full Moon, Waning Phase, Waxing Phase, New Moon.
    """
    name = "smt"
    
    # Define the 4 strict lunar phases with UI text in Spanish
    LUNAR_PHASES = [
        "🌕 Luna Llena",
        "🌗 Cuarto Menguante",
        "🌓 Cuarto Creciente",
        "🌑 Luna Nueva"
    ]

    def _get_lunar_index(self, state: 'GameState') -> int:
        """Retrieves the current lunar index safely from state configuration."""
        return state.discord_setup.get("smt_lunar_index", 0)

    def _set_lunar_index(self, state: 'GameState', index: int) -> None:
        """Saves the current lunar index into state configuration."""
        state.discord_setup["smt_lunar_index"] = index % len(self.LUNAR_PHASES)

    def get_status_info(self, state: 'GameState') -> Optional[str]:
        """Provides the current lunar phase in Spanish for the global /status command."""
        idx = self._get_lunar_index(state)
        current_phase_name = self.LUNAR_PHASES[idx]
        return f"**Ciclo Lunar:** {current_phase_name}"

    def on_phase_change(self, state: 'GameState') -> Optional[str]:
        """Advances the lunar cycle automatically when a new phase begins, notifying in Spanish."""
        current_idx = self._get_lunar_index(state)
        new_idx = current_idx + 1
        self._set_lunar_index(state, new_idx)
        
        phase_name = self.LUNAR_PHASES[new_idx % len(self.LUNAR_PHASES)]
        return f"🌙 Los astros se alinean... La fase lunar actual es: **{phase_name}**"