import logging
import random
from typing import Optional, TYPE_CHECKING
from cognitas.expansions.base import BaseExpansion
from cognitas.conditions.engine import Condition
from cognitas.conditions.factory import register_condition
from cognitas.core.actions import ActionTag
from cognitas.core.models import Player


if TYPE_CHECKING:
    from cognitas.core.state import GameState

logger = logging.getLogger("cognitas.expansions.dnd")


class VenomCondition(Condition):
    id_name = "venom"
    name = "Venom (DnD Expansion)"
    is_negative = True
    stacking_type = "refresh"
    category = "Physical"

    ui_on_apply = "{mention} ¡Has sido Envenenado con una toxina letal!"
    ui_on_expire = "{mention} Tu cuerpo ha expulsado la toxina."
    


class RootedCondition(Condition):
    id_name = "rooted"
    name = "Rooted (DnD Expansion)"
    is_negative = True
    stacking_type = "refresh"
    category = "Physical"

    ui_on_apply = "{mention} ¡Has sido Enraizado!"
    ui_on_expire = "{mention} Las raíces se han marchitado, eres libre."

    def __init__(self, duration: int = 1, stacks: int = 1, source_id=None):
        super().__init__(duration, stacks, source_id)
        # Default block message in case it's checked statically
        self.ui_on_block = "Estás Enraizado y no puedes moverte."
        self.ui_on_success_temp = None

    def can_use_ability(self, tag: 'ActionTag') -> bool:
        """
        Dynamically rolls 1d10 upon attempting an action.
        Even = Success, Odd = Blocked.
        """
        roll = random.randint(1, 10)
        
        if roll % 2 != 0:
            # Odd (Impar) -> Block the action and set the failure message
            self.ui_on_block = f"🌿 **¡Imposible!** Las raíces te han bloqueado por completo. (Dado Impar: {roll})"
            return False
        else:
            # Even (Par) -> Allow the action and set the success feedback
            self.ui_on_success_temp = f"🌿 **¡Lograste liberarte a tiempo para actuar!** (Dado Par: {roll})"
            return True


class ExpansionGimmick(BaseExpansion):
    """
    Cartridge for the Mafia x DnD Expansion.
    Handles random events during phase transitions.
    """
    name: str = "dnd"

    def __init__(self):
        super().__init__()
        
        # Register expansion-exclusive conditions into the engine dynamically
        register_condition(VenomCondition)
        register_condition(RootedCondition)
        
        self.random_events = [
            "🎭 **Evento Aleatorio:** Una densa niebla cubre el campamento. (El GM debe ambientar con música de tensión).",
            "🎉 **Evento Aleatorio:** ¡Es hora de la fiesta en la taberna! (El GM saca los parlantes y las bubuzelas).",
            "🌧️ **Evento Aleatorio:** Lluvia torrencial. Las tiradas de ataques a distancia fallan automáticamente esta noche.",
            "🐺 **Evento Aleatorio:** Aullidos a lo lejos. Nadie puede dormir bien."
        ]
        # The chance (in percentage) for a random event to trigger on phase change
        self.event_chance = 15

    def process_phase_change(self, state: "GameState") -> Optional[str]:
        """
        Triggered by TimeManager precisely after the phase or cycle has advanced.
        Processes Venom (HP/Cure) and calculates RNG for random events.
        """
        reports = []

        # 1. Process Venom Condition Statuses
        for player in state.get_alive_players():
            # Find the venom condition instance if the player has it
            venom_cond = next((c for c in player.statuses if c.id_name == "venom"), None)
            
            if venom_cond:
                coin = random.choice(["heads", "tails"])
                if coin == "heads":
                    # Successfully cured
                    player.statuses.remove(venom_cond)
                    reports.append(f"🧪 <@{player.user_id}> ha superado el Veneno (Salió Cara).")
                else:
                    # Failed, take 5 Damage
                    result = self.modify_player_hp(player, 5, "damage")
                    if result.get("died"):
                        reports.append(f"💀 <@{player.user_id}> ha sucumbido ante el Veneno (Salió Sello).")
                    else:
                        reports.append(f"🩸 <@{player.user_id}> sufre 5 de daño por Veneno (Salió Sello). HP Restante: {result.get('new_hp')}.")

        # 2. Process Random Events (Original Logic)
        roll = random.randint(1, 100)
        if roll <= self.event_chance:
            selected_event = random.choice(self.random_events)
            logger.info(f"DnD Gimmick triggered a random event: {selected_event}")
            reports.append(selected_event)
            
        # 3. Compile the phase report
        if reports:
            return "\n".join(reports)
            
        return None
    
    def modify_player_hp(self, player: 'Player', amount: int, action_type: str) -> dict:
        """
        Core business logic for modifying a player's Health Points.
        Handles the mathematical rules for damage, healing, and temporary HP.
        Returns a dictionary with the transaction results.
        """
        if not player.role:
            return {"error": "Player has no role assigned."}

        flags = player.role.flags
        current_hp = int(flags.get("hp", 0))
        max_hp = int(flags.get("max_hp", 100))
        temp_hp = int(flags.get("temp_hp", 0))

        if action_type == "damage":
            if temp_hp >= amount:
                flags["temp_hp"] = temp_hp - amount
            else:
                remaining_damage = amount - temp_hp
                flags["temp_hp"] = 0
                flags["hp"] = max(0, current_hp - remaining_damage)
                
        elif action_type == "heal":
            flags["hp"] = min(max_hp, current_hp + amount)
            
        elif action_type == "temp_hp":
            flags["temp_hp"] = max(temp_hp, amount)

        # Determine if the player just died from this specific transaction
        is_dead = (int(flags.get("hp", 0)) <= 0 and player.is_alive)

        return {
            "error": None,
            "new_hp": int(flags.get("hp", 0)),
            "max_hp": max_hp,
            "temp_hp": int(flags.get("temp_hp", 0)),
            "died": is_dead
        }
