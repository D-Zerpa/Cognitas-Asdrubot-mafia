import random
import logging
from enum import Enum
from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from cognitas.core.models import Player
    from cognitas.core.state import GameState
    from cognitas.expansions.base import BaseExpansion

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
                 resolution: ResolutionTime = ResolutionTime.QUEUED, requires_note: bool = False):
        self.identifier = identifier
        self.name = name
        self.tag = tag
        self.priority = priority
        self.accuracy = accuracy
        self.target_type = target_type
        self.resolution = resolution
        self.requires_note = requires_note

class ActionRecord:
    def __init__(self, source_id: int, target_id: Optional[int], ability: Ability, note: Optional[str] = None, roll: Optional[int] = None, state: Optional['GameState'] = None):
        self.source_id = source_id
        self.target_id = target_id
        self.ability = ability
        self.note = note
        
        # RNG lock-in
        self.roll = roll if roll is not None else random.randint(1, 100)
        
       # Certainty verification (Safely checking for id_name to prevent AttributeError)
        has_certainty = False
        if state:
            player = state.get_player(source_id)
            if player:
                has_certainty = any(getattr(cond, "id_name", None) == "certainty" for cond in player.statuses)
                
        # Success or failure
        self.is_success = True if has_certainty else (self.roll <= self.ability.accuracy)
        self.used_certainty = has_certainty and (self.ability.accuracy < 100)
        
class ActionManager:
    """
    Handles the validation, queueing, and sorting of player abilities.
    Volatile memory (self.queue) has been removed in favor of GameState persistence.
    """
    def __init__(self):
        pass

    def submit_action(self, source_player: 'Player', target_id: Optional[int], 
                      ability: Ability, state: 'GameState', 
                      gimmick: Optional['BaseExpansion'] = None,
                      note: Optional[str] = None) -> Dict[str, Any]:
        """
        Evaluates conditions (Blocks and Redirects), triggers Gimmick hooks, 
        and queues the action into the GameState.
        """
        # 0. Validate target integrity strictly against the Ability's TargetType
        if ability.target_type == TargetType.SINGLE and target_id is None:
            logger.warning(f"Player {source_player.user_id} attempted single-target ability {ability.identifier} without a target.")
            return {
                "status": "error", 
                "ui_text": "This ability requires a valid target."
            }
            
        if ability.target_type in (TargetType.NONE, TargetType.SELF):
            target_id = None  # Force None to prevent injection of invalid targets

        alive_player_ids = [p.user_id for p in state.get_alive_players()]

        # 1. Check for absolute blocks
        for condition in source_player.statuses:
            if not condition.can_use_ability(ability.tag):
                logger.info(f"Action blocked by {condition.name} for player {source_player.user_id}.")
                return {
                    "status": "blocked",
                    "reason": condition.name,
                    "ui_text": getattr(condition, "ui_on_block", "You cannot use abilities right now.")
                }

        # 2. Check for redirections (ONLY if the ability is targetable)
        final_target = target_id
        redirect_condition = None
        
        if ability.target_type in (TargetType.SINGLE, TargetType.ALL):
            for condition in source_player.statuses:
                new_target = condition.get_redirection(final_target, alive_player_ids)
                if new_target is not None:
                    final_target = new_target
                    redirect_condition = condition
                    break

        # 3. Clean up previous action from the same player (changing minds)
        state.action_queue = [
            a for a in state.action_queue 
            if not (a["source_id"] == source_player.user_id and a["ability_id"] == ability.identifier)
        ]
        
        # 4. Queue the final action
        temp_record = ActionRecord(source_player.user_id, final_target, ability, note, state=state)
        
        state.action_queue.append({
            "source_id": source_player.user_id,
            "target_id": final_target,  
            "ability_id": ability.identifier,
            "note": note,
            "roll": temp_record.roll    
        })
        logger.info(f"Action submitted: {source_player.user_id} used {ability.name} on {final_target}. Roll: {temp_record.roll}")

        # 5. Trigger Expansion Gimmicks
        secret_notifications = {}
        if gimmick:
            secret_notifications = gimmick.on_action_submitted(
                state=state,
                source_id=source_player.user_id,
                target_id=final_target,
                ability_tag=ability.tag.value
            )

        # 6. Build the result payload
        success_messages = ["Action registered successfully."]
        
        for condition in source_player.statuses:
            if getattr(condition, "ui_on_success_temp", None):
                success_messages.append(condition.ui_on_success_temp)
                condition.ui_on_success_temp = None  # Reset to prevent repeating on next actions

        base_response = {
            "status": "success",
            "ui_text": "\n\n".join(success_messages),
            "secret_notifications": secret_notifications
        }

        # Safely check for condition identifier
        if redirect_condition and getattr(redirect_condition, "id_name", None) == "confusion":
            base_response.update({
                "status": "redirected",
                "condition": "confusion",
                "new_target": final_target,
                "ui_try": getattr(redirect_condition, "ui_on_try_act", "You try to act..."),
                "ui_result": getattr(redirect_condition, "ui_on_tails", "Redirected to {new_target}.")
            })
        elif redirect_condition:
            base_response.update({
                "status": "redirected",
                "condition": redirect_condition.name,
                "new_target": final_target
            })
            
        return base_response

    def get_resolution_report(self, state: 'GameState', temp_registry: Optional[Dict[str, Any]] = None) -> List[ActionRecord]:
        """
        Reconstructs the queued actions from the GameState, sorted by strict priority.
        Now safely searches through temporary abilities (flags) if they are provided.
        """
        reconstructed_queue = []
        temp_registry = temp_registry or {}
        
        for action_dict in state.action_queue:
            source_player = state.get_player(action_dict["source_id"])
            if not source_player or not source_player.role:
                continue
                
            ability_id = action_dict["ability_id"]
            
            # 1. Search in base role abilities
            ability = next((ab for ab in source_player.role.abilities if ab.identifier == ability_id), None)
            
            # 2. Search in temporary abilities (Flags) if not found in base role
            if not ability:
                for temp_data in temp_registry.values():
                    # Support both single abilities and lists of abilities per flag
                    temp_list = temp_data if isinstance(temp_data, list) else [temp_data]
                    found = next((ab for ab in temp_list if ab.identifier == ability_id), None)
                    if found:
                        ability = found
                        break
            
            if ability:
                record = ActionRecord(
                    source_id=action_dict["source_id"],
                    target_id=action_dict["target_id"],
                    ability=ability,
                    note=action_dict.get("note"),
                    roll=action_dict.get("roll"),
                    state=state
                )
                reconstructed_queue.append(record)
                
        return sorted(reconstructed_queue, key=lambda x: x.ability.priority, reverse=True)

    def clear_queue(self, state: 'GameState') -> None:
        """Wipes the action slate clean (typically called at dawn)."""
        state.action_queue.clear()
        logger.info("Action queue cleared from state.")