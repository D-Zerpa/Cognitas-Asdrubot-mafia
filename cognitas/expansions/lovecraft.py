import logging
from typing import Optional, Dict, List, Any, TYPE_CHECKING
from cognitas.expansions.base import BaseExpansion
from cognitas.core.time import Phase
from cognitas.conditions.factory import register_condition
from cognitas.conditions.engine import Condition
from cognitas.core.actions import ActionTag
from cognitas.conditions.engine import ConditionManager
from cognitas.conditions.builtin import WoundedCondition
import random

if TYPE_CHECKING:
    from cognitas.core.state import GameState
    from cognitas.core.models import Player

logger = logging.getLogger("cognitas.expansions.lovecraft")



# --------------------------------------------------------------------------
#  SANITY IMPACT DICTIONARY
# --------------------------------------------------------------------------
ABILITY_SANITY_IMPACTS: Dict[str, Dict[str, Any]] = {
    # Penalties (Paranoia +)
    "summary_judgment_error": {"paranoia": 15, "desc": "Ejecución errónea (Juez ejecuta Pueblo)"},
    "unconventional_methods_error": {"paranoia": 15, "desc": "Ejecución errónea (Gangster ejecuta Pueblo)"},
    "voices_from_the_deep_break": {"paranoia": 10, "desc": "Incumplir Orden Real (Acólito)"},
    "jungian_integration_ethics": {"paranoia": 7, "desc": "Revelar info de Asesino (Psicólogo - Rotura de Ética)"},
    "sale_of_indulgences": {"paranoia": 4, "desc": "Uso de la habilidad (Corrupción - Sacerdote)"},
    "compulsive_surgery_error": {"paranoia": 3, "desc": "Activar efecto secundario negativo (Doctor)"},
    "ethereal_transfusion_error": {"paranoia": 2, "desc": "Transferencia de alteración (Ocultista)"},
    "public_tribune_lie": {"paranoia": 2, "desc": "Mentir en debate político (Político)"},
    "virus_spread": {"paranoia": 2, "desc": "Por cada nuevo infectado propagado"},
    
    # Boosts / Heals (Paranoia -)
    "veil_affinity_success": {"paranoia": -4, "desc": "Anular habilidad mafiosa (Cultista Reformado)"},
    "hymn_of_hope": {"paranoia": -5, "desc": "Himno de la Esperanza exitoso (-4 a -7)"},
    "magnum_opus_success": {"paranoia": -2, "desc": "Mensaje Legendario exitoso (Autor)"},
    "collective_fervor_success": {"paranoia": -7, "desc": "Fervor Colectivo Exitoso (Sacerdote)"},
    "gods_vestal": {"paranoia": -3, "desc": "Curación de Alteración Espiritual (Monja)"},
    "student_heal_spirit": {"paranoia": -3, "desc": "Curación de Alteración Espiritual (Estudiante)"},
    "student_heal_mental": {"paranoia": -3, "desc": "Curación de Alteración Mental (Estudiante)"},
    "jungian_integration_success": {"paranoia": -3, "desc": "Curación de Alteración Mental (Psicólogo)"},
    "healing_hands": {"paranoia": -3, "desc": "Curación Física Exitosa (Doctor)"},
    "rashin_dodge": {"paranoia": -3, "desc": "Artista Marcial esquiva y revela perpetrador"},
    "certainty_absolution_used": {"paranoia": -2, "desc": "Uso de Certeza o Absolución (Buffs)"}
}


# --------------------------------------------------------------------------
#  CONDITIONS
# --------------------------------------------------------------------------

class IncapacitatedCondition(Condition):
    id_name = "incapacitated"
    name = "Incapacitated"
    is_negative = True
    stacking_type = "refresh"
    category = "Physical"

    ui_on_apply = "{mention} ⚠️ Has sido Incapacitado. No puedes usar habilidades hasta recibir tratamiento médico."
    ui_on_block = "Estás Incapacitado, tu cuerpo no te responde."
    ui_on_expire = "{mention} Te has recuperado de tu incapacidad."

    def __init__(self, duration: int = 999, stacks: int = 1):
        super().__init__(duration, stacks)

    def can_use_ability(self, tag: 'ActionTag') -> bool:
        return False
    
class VirusCondition(Condition):
    id_name = "virus"
    name = "Virus"
    is_negative = True
    stacking_type = "refresh"
    category = "Physical"

    ui_on_apply = "{mention} 🦠 Sientes que algo oscuro recorre tus venas... (Infectado)."
    ui_on_expire = "{mention} 💀 Tu cuerpo no resistió. El virus te ha consumido por completo."

    def __init__(self, duration: int = 4, stacks: int = 1):
        super().__init__(duration, stacks)

    def on_expire(self, player: 'Player', state: 'GameState') -> None:
        if player.is_alive:
            # Use the official model method to kill the player
            player.kill()
            logger.info(f"Player {player.user_id} died from Virus expiration.")
            
            # trigger the expansion hook to ensure Paranoia is updated.
            if hasattr(state, "expansion") and hasattr(state.expansion, "on_player_death"):
                state.expansion.on_player_death(state, player)
            
class CurseCondition(Condition):
    id_name = "curse"
    name = "Curse"
    is_negative = True
    stacking_type = "refresh"
    category = "Spiritual"

    ui_on_apply = "{mention} 👁️ Una maldición ha caído sobre ti. Sientes una opresión constante."
    ui_on_expire = "{mention} ✨ La pesada maldición se ha disipado."

    def __init__(self, duration: int = 2, stacks: int = 1):
        super().__init__(duration, stacks)

    def on_action_submitted(self, state: 'GameState', source_id: int, target_id: Optional[int], ability_tag: str) -> Dict[str, str]:
        """
        Intercepts the action submission to evaluate gimmick conditions like Curses.
        Returns a dictionary of secret notifications for the UI.
        """
        notifications = {}
        player = state.get_player(source_id)
        
        if not player:
            return notifications
            
        # Check if the player is cursed
        has_curse = any(cond.id_name == "curse" for cond in player.statuses)
        
        if has_curse:
            # 50% chance to trigger self-harm
            if random.random() <= 0.5:
                cm = ConditionManager(state)
                cm.apply_condition(source_id, WoundedCondition())
                notifications["curse_effect"] = "🩸 [MALDICIÓN] Tu acción ha resonado con la oscuridad. Te has infligido una herida."
                logger.info(f"Curse triggered WoundedCondition on player {source_id}.")
            else:
                notifications["curse_effect"] = "✨ [MALDICIÓN] Has logrado forzar tu acción sin que la maldición te consuma... esta vez."
                
        return notifications
    
class HallucinationCondition(Condition):
    id_name = "hallucination"
    name = "Hallucination"
    is_negative = True
    stacking_type = "refresh"
    category = "Spiritual"

    ui_on_apply = "{mention} 🌀 Las sombras susurran. Ya no puedes confiar en tus propios sentidos."
    ui_on_expire = "{mention} 👁️ Tu mente vuelve a estar clara."
    ui_on_try_act = "Las alucinaciones guían tus manos... pierdes el control."
    ui_on_tails = "Tus acciones fueron dirigidas por la locura hacia otro objetivo."

    def __init__(self, duration: int = 2, stacks: int = 1):
        super().__init__(duration, stacks)

    def get_redirection(self, original_target: Optional[int], valid_targets: List[int]) -> Optional[int]:
        if not valid_targets:
            return None
        return random.choice(valid_targets)
    
class PossessionCondition(Condition):
    id_name = "possession"
    name = "Possession"
    is_negative = True
    stacking_type = "refresh"
    category = "Spiritual"

    ui_on_apply = "{mention} 👻 Tu cuerpo ya no te pertenece. Un ente extraño ha tomado el control."
    ui_on_expire = "{mention} 💨 Vuelves a respirar. El ente ha abandonado tu cuerpo."

    def __init__(self, duration: int = 2, stacks: int = 1):
        super().__init__(duration, stacks)


# --------------------------------------------------------------------------
#  GIMMICKS
# --------------------------------------------------------------------------

class ExpansionGimmick(BaseExpansion):
    """
    Gimmick controller for the Lovecraft Expansion (Sanity vs Paranoia).
    """
    name: str = "lovecraft"
    
    def __init__(self):
        register_condition(IncapacitatedCondition)
        register_condition(VirusCondition)
        register_condition(CurseCondition)
        register_condition(HallucinationCondition)
        register_condition(PossessionCondition)

    def on_player_death(self, state: 'GameState', player: 'Player') -> None:
        """Automatically adjusts paranoia based on alignment and phase."""
        current_paranoia = state.expansion_data.get("paranoia", 0)
        
        # Zero assumptions: safely get alignment
        alignment = getattr(player.role, "alignment", "Pueblo").lower()
        
        if alignment == "mafia":
            shift = -10
            reason = "Linchamiento/Muerte de un Mafioso"
        else:
            # Assuming Phase.DAY implies a lynch resolution, and NIGHT implies night kills
            if state.phase == Phase.DAY:
                shift = 4
                reason = "Muerte de un Pueblo (Linchamiento)"
            else:
                shift = 3
                reason = "Muerte de un Pueblo (Asesinato Nocturno)"
                
        # Apply the shift, ensuring paranoia doesn't drop below 0
        new_paranoia = max(0, current_paranoia + shift)
        state.expansion_data["paranoia"] = new_paranoia
        logger.info(f"Player {player.user_id} died. Paranoia shifted by {shift} ({reason}). New total: {new_paranoia}")

    def on_phase_change(self, state: 'GameState') -> Optional[str]:
        """Evaluates Sanity mechanics and provides GM reminders at Dawn."""
        if state.phase == Phase.DAY:
            sanity = state.expansion_data.get("sanity", 10)
            paranoia = state.expansion_data.get("paranoia", 0)
            
            # --- 1. GM Assistant: Calculate Balance ---
            # Minimum paranoia thresholds based on current sanity level
            thresholds = {10: 5, 9: 7, 8: 10, 7: 12, 6: 15, 5: 18, 4: 15, 3: 12, 2: 10, 1: 8}
            min_par = thresholds.get(sanity, 99)
            
            advice = ""
            if paranoia >= (min_par * 2): 
                advice = "⚠️ CRISIS: Paranoia is double the minimum. YOU MUST DECREASE SANITY."
            elif paranoia >= min_par and paranoia >= sanity: 
                advice = "⚠️ BREAKPOINT: Paranoia surpassed minimum and Sanity. YOU MUST DECREASE SANITY."
            else: 
                advice = "✅ STABLE: Sanity held through the night."
                
            state.gm_reminders.append(f"[Lovecraft Balance] Sanity: {sanity} | Paranoia: {paranoia} -> {advice}")

            # --- 2. Public Narrative Announcement ---
            if sanity <= 4:
                return "«El cielo ha amanecido con un tono enfermizo. Algo indescriptible nos observa desde las sombras...»"
            elif sanity <= 7:
                return "«Un nuevo día. Las miradas se cruzan con recelo, la desconfianza es palpable en el aire.»"
            else:
                return "«El sol se alza sobre el pueblo, trayendo una frágil y falsa sensación de seguridad.»"
                
        return None

    def get_status_info(self, state: 'GameState') -> Optional[str]:
        """Provides vague, creepy status info based on current Sanity."""
        sanity = state.expansion_data.get("sanity", 10)
        
        if sanity >= 8:
            return "🟢 **Atmósfera:** El pueblo mantiene la calma... por ahora."
        elif sanity >= 5:
            return "🟡 **Atmósfera:** La paranoia empieza a fracturar las mentes de los habitantes."
        else:
            return "🔴 **Atmósfera:** La locura es absoluta. Nadie está a salvo."
        
    def get_ability_impact(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the exact paranoia modifier and description for a specific expansion event.
        Must be requested dynamically since many conditions (like 'lying') are contextual.
        """
        return ABILITY_SANITY_IMPACTS.get(event_id)