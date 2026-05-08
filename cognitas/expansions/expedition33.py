import logging
from typing import Optional, Dict, TYPE_CHECKING
from cognitas.expansions.base import BaseExpansion
from cognitas.core.time import Phase

if TYPE_CHECKING:
    from cognitas.core.state import GameState
    from cognitas.core.models import Player

logger = logging.getLogger("cognitas.expansions.expedition33")

class Expedition33Expansion(BaseExpansion):
    """
    Gimmick y controlador de eventos para la expansión "Expedition 33".
    """
    name: str = "expedition33"

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