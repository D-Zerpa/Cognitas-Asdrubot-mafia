class ActionRecord:
    def __init__(self, source_id: int, target_id: Optional[int], ability: Ability, note: Optional[str] = None, roll: Optional[int] = None):
        self.source_id = source_id
        self.target_id = target_id
        self.ability = ability
        self.note = note
        
        self.roll = roll if roll is not None else random.randint(1, 100)
        self.is_success = self.roll <= self.ability.accuracy

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
        alive_player_ids = [p.user_id for p in state.get_alive_players()]

        # 1. Check for absolute blocks
        for condition in source_player.statuses:
            if not condition.can_use_ability(ability.tag):
                logger.info(f"Action blocked by {condition.name} for player {source_player.user_id}.")
                return {
                    "status": "blocked",
                    "reason": condition.name,
                    "ui_text": getattr(condition, "ui_on_block", "No puedes usar habilidades en este momento.")
                }

        # 2. Check for redirections
        final_target = target_id
        redirect_condition = None
        
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
        temp_record = ActionRecord(source_player.user_id, final_target, ability, note)
        
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
        base_response = {
            "status": "success",
            "ui_text": "Acción registrada con éxito.",
            "secret_notifications": secret_notifications
        }

        if redirect_condition and redirect_condition.id_name == "confusion":
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

    def get_resolution_report(self, state: 'GameState') -> List[ActionRecord]:
        """
        Reconstructs the queued actions from the GameState, sorted by strict priority.
        NOTE: You must now pass 'state' to this function when calling it from time.py!
        """
        reconstructed_queue = []
        
        for action_dict in state.action_queue:
            source_player = state.get_player(action_dict["source_id"])
            if not source_player or not source_player.role:
                continue
                
            ability_id = action_dict["ability_id"]
            ability = next((ab for ab in source_player.role.abilities if ab.identifier == ability_id), None)
            
            if ability:
                record = ActionRecord(
                    source_id=action_dict["source_id"],
                    target_id=action_dict["target_id"],
                    ability=ability,
                    note=action_dict.get("note"),
                    roll=action_dict.get("roll")
                )
                reconstructed_queue.append(record)
                
        return sorted(reconstructed_queue, key=lambda x: x.ability.priority, reverse=True)

    def clear_queue(self, state: 'GameState') -> None:
        """Wipes the action slate clean (typically called at dawn)."""
        state.action_queue.clear()
        logger.info("Action queue cleared from state.")