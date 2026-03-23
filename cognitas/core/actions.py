import random
import logging
from enum import Enum
from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import Player
    from core.state import GameState
    from expansions.base import BaseExpansion

logger = logging.getLogger("cognitas.actions")

class ActionTag(str, Enum):
    DAY_ACT = "day_act"
    NIGHT_ACT = "night_act"
    PASSIVE = "passive"

class TargetType(str, Enum):
    SINGLE = "single"
    ALL = "all"
    NONE = "none"
    SELF = "self"

class ResolutionTime(str, Enum):
    """Defines when the payload of the ability is actually executed."""
    INSTANT = "instant"
    QUEUED = "queued"

class Ability:
    def __init__(self, identifier: str, name: str, tag: ActionTag, 
                 priority: int, accuracy: int = 100, target_type: TargetType = TargetType.SINGLE,
                 resolution: ResolutionTime = ResolutionTime.QUEUED):
        self.identifier = identifier
        self.name = name
        self.tag = tag
        self.priority = priority
        self.accuracy = accuracy
        self.target_type = target_type
        self.resolution = resolution

class ActionRecord:
    def __init__(self, source_id: int, target_id: Optional[int], ability: Ability, note: Optional[str] = None):
        self.source_id = source_id
        self.target_id = target_id
        self.ability = ability
        self.note = note
        
        # RNG lock-in at the moment of submission
        self.roll = random.randint(1, 100)
        self.is_success = self.roll <= self.ability.accuracy

class ActionManager:
    """
    Handles the validation, queueing, and sorting of player abilities.
    """
    def __init__(self):
        self.queue: List[ActionRecord] = []

    def submit_action(self, source_player: 'Player', target_id: Optional[int], 
                      ability: Ability, state: 'GameState', 
                      gimmick: Optional['BaseExpansion'] = None,
                      note: Optional[str] = None) -> Dict[str, Any]:
        """
        Evaluates conditions (Blocks and Redirects), triggers Gimmick hooks, 
        and queues the action. Returns a payload for Discord UI rendering.
        """
        alive_player_ids = [p.user_id for p in state.get_alive_players()]

        # 1. Check for absolute blocks (Paralyzed, Drowsiness, Jailed)
        for condition in source_player.statuses:
            if not condition.can_use_ability(ability.tag):
                logger.info(f"Action blocked by {condition.name} for player {source_player.user_id}.")
                return {
                    "status": "blocked",
                    "reason": condition.name,
                    "ui_text": getattr(condition, "ui_on_block", "No puedes usar habilidades en este momento.")
                }

        # 2. Check for redirections (Confusion, Taunts)
        final_target = target_id
        redirect_condition = None
        
        for condition in source_player.statuses:
            new_target = condition.get_redirection(final_target, alive_player_ids)
            if new_target is not None:
                final_target = new_target
                redirect_condition = condition
                break # Only apply the first redirection we find to avoid infinite loops

        # 3. Clean up previous action from the same player (changing minds)
        self.queue = [a for a in self.queue if a.source_id != source_player.user_id]
        
        # 4. Queue the final action
        record = ActionRecord(source_player.user_id, final_target, ability, note)
        self.queue.append(record)
        logger.info(f"Action submitted: {source_player.user_id} used {ability.name} on {final_target}.")

        # 5. Trigger Expansion Gimmicks (e.g., Persona 3 Oracle Radar)
        secret_notifications = {}
        if gimmick:
            secret_notifications = gimmick.on_action_submitted(
                state=state,
                source_id=source_player.user_id,
                target_id=final_target,
                ability_tag=ability.tag.value
            )

        # 6. Build the result payload for Discord UI
        base_response = {
            "status": "success",
            "ui_text": "Acción registrada con éxito.",
            "secret_notifications": secret_notifications
        }

        if redirect_condition and redirect_condition.id_name == "confusion":
            # Specific payload for Confusion UI flavor text
            base_response.update({
                "status": "redirected",
                "condition": "confusion",
                "new_target": final_target,
                "ui_try": getattr(redirect_condition, "ui_on_try_act", "Intentas actuar..."),
                "ui_result": getattr(redirect_condition, "ui_on_tails", "Redirigido a {new_target}.")
            })
        elif redirect_condition:
            base_response.update({
                "status": "redirected",
                "condition": redirect_condition.name,
                "new_target": final_target
            })
            
        return base_response

    def get_resolution_report(self) -> List[ActionRecord]:
        """
        Returns the queued actions sorted by strict priority (Highest first).
        Used by the Game Master at the end of the phase to resolve the night.
        """
        return sorted(self.queue, key=lambda x: x.ability.priority, reverse=True)

    def clear_queue(self) -> None:
        """Wipes the action slate clean (typically called at dawn)."""
        self.queue.clear()
        logger.info("Action queue cleared.")