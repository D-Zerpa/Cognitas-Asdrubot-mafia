import logging
from typing import Optional, Dict, TYPE_CHECKING
from cognitas.expansions.base import BaseExpansion
from cognitas.core.time import Phase
from cognitas.conditions.factory import register_condition
from cognitas.conditions.engine import Condition

if TYPE_CHECKING:
    from cognitas.core.state import GameState
    from cognitas.core.models import Player

logger = logging.getLogger("cognitas.expansions.expedition33")


class BurnedCondition(Condition):
    id_name = "burned"
    name = "Burned"
    is_negative = True
    stacking_type = "sum"

    ui_on_apply = "{mention} 🔥 Te han infligido una Quemadura. Tu concentración flaquea."
    ui_on_expire = "{mention} 💧 Tus quemaduras han sanado por completo."

    def on_stack(self, player: 'Player', state: 'GameState') -> None:
        # El motor hace max() por defecto, así que forzamos la suma de la duración
        self.duration += 1
        logger.info(f"Quemadura acumulada en el jugador {player.user_id}. Nueva duración: {self.duration} días.")

    def get_action_prefix(self, roll: int) -> str:
        if roll <= 50:
            return "[🔥 QUEMADURA: Superada] "
        elif roll <= 80:
            return "[🔥 QUEMADURA: Acción Fallida] "
        else:
            return "[🔥 QUEMADURA: Acción Fallida + Herida] "

class ExpansionGimmick(BaseExpansion):
    """
    Gimmick y controlador de eventos para la expansión "Expedition 33".
    """
    name: str = "expedition33"

    def __init__(self):
        register_condition(BurnedCondition)

    def get_status_info(self, state: 'GameState') -> Optional[str]:
        """Aparece cuando alguien usa el comando /status."""
        if state.phase == Phase.DAY:
            return "☀️ **El Sol Asciende:** La Expedición avanza un día más hacia el Monolito."
        elif state.phase == Phase.NIGHT:
            return "🌙 **El Ocaso:** Las sombras del Pincel acechan en la oscuridad."
        return "⏳ Preparando la Expedición..."

    def on_phase_change(self, state: 'GameState') -> Optional[str]:
        """Aparece como anuncio global cuando el GM usa /next_phase."""
        if state.phase == Phase.DAY:
            return "«Tomorrow Comes. Pero no todos llegaron a verlo...»"
        elif state.phase == Phase.NIGHT:
            return "«El mundo es un lienzo, y la noche es el momento de pintar...»"
        return None

    def on_player_death(self, state: 'GameState', player: 'Player') -> None:
        """Puede usarse para mecánicas secretas al morir, en esta beta lo mantenemos silencioso."""
        pass

    def on_action_submitted(self, state: 'GameState', source_id: int, target_id: Optional[int], ability_tag: str) -> Dict[int, str]:
        """
        No se usa en roles de resolución manual, ya que el reporte se lee al final.
        """
        return {}