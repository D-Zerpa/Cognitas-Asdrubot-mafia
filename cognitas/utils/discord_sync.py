import logging
import discord
from typing import Optional, List, Dict, Union, Any

from cognitas.core.models import Player
from cognitas.core.state import GameState

logger = logging.getLogger("cognitas.sync")

async def process_player_death(bot, guild: discord.Guild, player: Player, reason: str = "Causa desconocida") -> None:
    """
    Synchronizes a logical player death with Discord UI (Roles, Graveyard, Logs).
    """
    state: GameState = getattr(bot, "game_state", None)
    if not state:
        return

    # 1. Ensure logical death in the engine
    if player.is_alive:
        player.kill()
        logger.info(f"Player {player.user_id} logically killed. Reason: {reason}")

    # 2. Fetch the Discord Member object
    member = guild.get_member(player.user_id)
    if not member:
        logger.warning(f"Cannot sync death: User {player.user_id} not found in guild {guild.id}.")
        return

    setup = state.discord_setup

    # 3. Role Swapping (Remove Alive, Add Dead)
    roles_to_add = []
    roles_to_remove = []
    
    if setup.get("dead_role_id"):
        dead_role = guild.get_role(setup["dead_role_id"])
        if dead_role: roles_to_add.append(dead_role)
        
    if setup.get("alive_role_id"):
        alive_role = guild.get_role(setup["alive_role_id"])
        if alive_role: roles_to_remove.append(alive_role)

    try:
        if roles_to_add: await member.add_roles(*roles_to_add)
        if roles_to_remove: await member.remove_roles(*roles_to_remove)
    except discord.Forbidden:
        logger.error(f"Missing permissions to swap roles for {member.display_name}.")

    # 4. Welcome to the Graveyard
    if setup.get("graveyard_channel_id"):
        gy_channel = guild.get_channel(setup["graveyard_channel_id"])
        if gy_channel:
            await gy_channel.send(
                f"👻 {member.mention} ha cruzado al otro lado. Bienvenido/a al cementerio.\n"
                f"*(Causa de muerte: {reason})*"
            )

    # 5. Audit Log for the Game Master
    if setup.get("log_channel_id"):
        log_channel = guild.get_channel(setup["log_channel_id"])
        if log_channel:
            role_name = player.role.name if player.role else "Rol Desconocido"
            await log_channel.send(f"💀 **AUDITORÍA DE MUERTE:** {member.mention} (**{role_name}**) ha muerto. Razón: {reason}")