import abc
import logging
from typing import List, TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.models import Player
    from core.state import GameState
    from core.actions import ActionTag

logger = logging.getLogger("cognitas.conditions")

class Condition(abc.ABC):
    """
    Abstract base class for all altered conditions.
    Now supports advanced mechanics like Stacking and Vote Modifiers.
    """
    id_name: str = "base_condition"
    name: str = "Base Condition"
    is_negative: bool = True
    stacking_type: str = "refresh"  # Options: "refresh", "sum", "none"

    def __init__(self, duration: int = 1, stacks: int = 1):
        self.duration = duration
        self.stacks = stacks

    def tick(self) -> bool:
        """Decreases duration. Returns True if expired."""
        if self.duration > 0:
            self.duration -= 1
        return self.duration == 0

    # --- ACTION ENGINE HOOKS ---
    def can_use_ability(self, tag: 'ActionTag') -> bool:
        """Determines if a specific type of ability (day/night) can be used."""
        return True

    def get_redirection(self, original_target: Optional[int], valid_targets: List[int]) -> Optional[int]:
        """
        Action Engine hook: Returns a new target ID if the condition forces a redirect.
        Returns None if the target remains unchanged.
        """
        return None

    def is_protected(self) -> bool:
        return False

    def is_silenced(self) -> bool:
        """Determines if the player is muted in the Day channel."""
        return False

    # --- VOTING ENGINE HOOKS ---
    def get_vote_multiplier(self) -> float:
        """
        Returns a multiplier for the vote weight. 
        e.g., 2.0 for Double Vote, 0.5 for Sanctioned, 0.0 for disabled.
        """
        return 1.0

    # --- LIFECYCLE HOOKS ---
    def on_apply(self, player: 'Player', state: 'GameState') -> None:
        pass

    def on_stack(self, player: 'Player', state: 'GameState') -> None:
        """Executed when a 'sum' stacking condition is applied again."""
        pass

    def on_expire(self, player: 'Player', state: 'GameState') -> None:
        pass


class ConditionManager:
    """Handles the lifecycle and stacking logic of conditions."""
    def __init__(self, state: 'GameState'):
        self.state = state

    def apply_condition(self, target_id: int, condition: Condition) -> None:
        player = self.state.get_player(target_id)
        if not player or not player.is_alive:
            return
        
        # Check if player already has this condition
        for existing in player.statuses:
            if existing.id_name == condition.id_name:
                if condition.stacking_type == "refresh":
                    existing.duration = max(existing.duration, condition.duration)
                    logger.debug(f"Refreshed duration of '{condition.name}' on {target_id}.")
                elif condition.stacking_type == "sum":
                    existing.stacks += condition.stacks
                    existing.duration = max(existing.duration, condition.duration)
                    logger.debug(f"Stacked '{condition.name}' on {target_id}. Total stacks: {existing.stacks}")
                    existing.on_stack(player, self.state)
                return

        # If new condition, append and apply
        player.statuses.append(condition)
        condition.on_apply(player, self.state)
        logger.info(f"Applied '{condition.name}' to player {target_id}.")

    def process_phase_end(self) -> None:
        """Ticks down all conditions and removes expired ones."""
        for player in self.state.get_alive_players():
            expired_conditions: List[Condition] = []
            
            for condition in player.statuses:
                if condition.tick():
                    expired_conditions.append(condition)

            for expired in expired_conditions:
                expired.on_expire(player, self.state)
                player.statuses.remove(expired)
                logger.info(f"Condition '{expired.name}' expired on {player.user_id}.")