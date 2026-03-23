import abc
from typing import Optional, List, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from core.state import GameState
    from core.models import Player

class BaseExpansion(abc.ABC):
    """
    Abstract skeleton for Game Expansions (Gimmicks).
    Acts as a bridge to inject custom mechanics without touching the Core Engine.
    """
    name: str = "Base Expansion"

    def get_status_info(self, state: 'GameState') -> Optional[str]:
        """Called by /status to show custom information (e.g., Lunar Phase, Apocalypse Counter)."""
        return None

    def on_phase_change(self, state: 'GameState') -> Optional[str]:
        """Called by TimeManager exactly when phase changes. Returns an announcement string if any."""
        return None

    def on_player_death(self, state: 'GameState', player: 'Player') -> None:
        """Called by process_player_death immediately when someone dies."""
        pass

    def on_action_submitted(self, state: 'GameState', source_id: int, target_id: Optional[int], ability_tag: str) -> Dict[int, str]:
        """
        Called immediately when a player submits an action (e.g., via /act).
        Returns a dictionary of {player_id: message_string} for players that 
        need to be notified secretly (like the Oracle/Fuuka radar).
        """
        return {}