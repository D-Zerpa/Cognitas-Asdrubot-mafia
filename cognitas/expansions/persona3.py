from __future__ import annotations
import discord
import random
import os
from typing import List, Optional, TYPE_CHECKING
from cognitas.expansions.base import BaseExpansion

if TYPE_CHECKING:
    from cognitas.core.state import GameState
    from cognitas.core.models import Player

class ExpansionGimmick(BaseExpansion):
    """
    Persona 3 expansion featuring the Nyx Apocalypse countdown, 
    Nyx global phase triggers, and Fuuka's Oracle radar.
    """
    name = "p3"
    
    # Narrative timeline based on remaining active Arcana players
    NYX_TIMELINE = {
        13: "El cielo está tranquilo. La vida cotidiana continúa ignorante del destino.",
        12: "La primera campana ha sonado. Una sombra se proyecta sobre la ciudad.",
        11: "La luna comienza a teñirse de un verde enfermizo.",
        10: "Susurros en la oscuridad... La gente empieza a olvidar sus sueños.",
        9:  "La apatía se extiende como una plaga silenciosa.",
        8:  "Las sombras se alargan. El Sello se debilita visiblemente.",
        7:  "Mitad del camino. La balanza se inclina hacia la noche eterna.",
        6:  "El aire se vuelve pesado. Respirar cuesta cada vez más.",
        5:  "El cielo se desgarra. Figuras ominosas observan desde las alturas.",
        4:  "La cordura de la humanidad pende de un hilo.",
        3:  "Tres pilares restantes. El rugido de Nyx es ensordecedor.",
        2:  "La desesperación es absoluta. Solo queda rezar... o luchar.",
        1:  "El último sello. La Muerte está llamando a la puerta.",
        0:  "LA HORA OSCURA ETERNA HA COMENZADO. NYX HA DESCENDIDO."
    }

    def __init__(self):
        super().__init__()
        self._daily_nyx_msg: str = ""
        # Cache to store who acted during the night
        self._night_actors_cache: set[int] = set()

    # --------------------------------------------------------------------------
    #  EXPANSION INTERFACE HOOKS
    # --------------------------------------------------------------------------

    def get_status_info(self, state: 'GameState') -> Optional[str]:
        """Provides the current Apocalypse countdown status for the /status command."""
        count = self._count_arcanas(state, alive_only=True)
        flavor = self.NYX_TIMELINE.get(count, "El fin se acerca inexorablemente...")
        return f"**Conteo hasta el Apocalipsis:** {count} horas restantes\n> *\"{flavor}\"*"

    def on_phase_change(self, state: 'GameState') -> Optional[str]:
        """Triggered when the phase advances. Handles Nyx notifications and effects."""
        # Note: Phase change handles cycle announcements. 
        count = self._count_arcanas(state, alive_only=True)
        flavor = self.NYX_TIMELINE.get(count, "El fin se acerca inexorablemente...")
        
        announcement = (
            f"🌑 **El Apocalipsis se aproxima...**\n"
            f"# ⏳ Faltan **{count}** horas.\n\n"
            f"> *\"{flavor}\"*"
        )
        
        if self._daily_nyx_msg:
            announcement += f"\n\n{self._daily_nyx_msg}"
            self._daily_nyx_msg = ""
            
        return announcement

    def on_player_death(self, state: 'GameState', player: 'Player') -> None:
        """Triggered automatically when a player dies. Can update tracking if needed."""
        pass
    
    def on_action_submitted(self, state: 'GameState', source_id: int, target_id: Optional[int], ability_tag: str) -> dict[int, str]:
        """Intercepts actions for Fuuka's Radar and caches night actors for the Morning Report."""
        notifications = {}
        
        # 1. Cache for Night Report
        if ability_tag == "night_act":
            self._night_actors_cache.add(source_id)
            
        if not target_id:
            return notifications

        # 2. Immediate Radar Logic
        target = state.players.get(target_id)
        if not target or not target.role or not target.role.flags.get("sees", False):
            return notifications

        oracles = self._get_active_oracles(state, exclude_uid=source_id)
        target_name = target.role.name
        msg = f"📡 **[ORACLE]** Anomalía detectada: Habilidad usada contra **{target_name}**."

        for oracle_id in oracles:
            notifications[oracle_id] = msg

        return notifications
    
    async def on_phase_start(self, bot, guild: discord.Guild, state: 'GameState') -> None:
        """Delivers Fuuka's Tactical Report at Dawn and clears the cache."""
        if state.phase.value == "day":
            oracles = self._get_active_oracles(state)
            if oracles:
                prev_night_num = max(1, state.cycle - 1)
                
                if not self._night_actors_cache:
                    msg = f"📡 **[ORACLE] Registro Táctico — Noche {prev_night_num}**\n*No se detectó actividad anoche.*"
                else:
                    names = []
                    for uid in self._night_actors_cache:
                        member = guild.get_member(uid)
                        name = member.display_name if member else f"ID:{uid}"
                        names.append(name)
                    
                    list_str = ", ".join(names)
                    msg = (
                        f"📡 **[ORACLE] Registro Táctico — Noche {prev_night_num}**\n"
                        f"Se detectaron firmas energéticas de los siguientes agentes:\n"
                        f"`{list_str}`"
                    )
                
                # Send private messages to all oracles via their private channels
                for oracle_uid in oracles:
                    oracle_player = state.get_player(oracle_uid)
                    if oracle_player and oracle_player.private_channel_id:
                        priv_channel = guild.get_channel(oracle_player.private_channel_id)
                        if priv_channel:
                            await priv_channel.send(msg)
                            
            # Always wipe the cache clean for the next night
            self._night_actors_cache.clear()

    # --------------------------------------------------------------------------
    #  INTERNAL LOGIC & HELPERS
    # --------------------------------------------------------------------------

    def _count_arcanas(self, state: 'GameState', alive_only: bool = True) -> int:
        """Counts how many players have the 'arcana' flag enabled in their role."""
        count = 0
        for player in state.players.values():
            if player.role and player.role.flags.get("arcana", False):
                if alive_only and not player.is_alive:
                    continue
                count += 1
        return count

    def _get_active_oracles(self, state: 'GameState', exclude_uid: Optional[int] = None) -> List[int]:
        """Returns user IDs of alive players with the 'oracle' flag."""
        oracles = []
        for player in state.players.values():
            if player.user_id == exclude_uid:
                continue
            if player.is_alive and player.role and player.role.flags.get("oracle", False):
                oracles.append(player.user_id)
        return oracles