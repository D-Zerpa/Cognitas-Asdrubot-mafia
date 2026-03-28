import logging
import discord

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
        logger.warning(f"User {player.user_id} not in guild {guild.id}. Skipping role updates.")

    setup = state.discord_setup

    # 3. Role Swapping (Remove Alive, Add Dead)
    if member:
        roles_to_add = []
        roles_to_remove = []
        
        if setup.get("dead_role_id"):
            dead_role = guild.get_role(setup["dead_role_id"])
            # Only add if the member doesn't already have it
            if dead_role and dead_role not in member.roles: 
                roles_to_add.append(dead_role)
                
        if setup.get("alive_role_id"):
            alive_role = guild.get_role(setup["alive_role_id"])
            # Only remove if the member actually has it
            if alive_role and alive_role in member.roles: 
                roles_to_remove.append(alive_role)

        try:
            if roles_to_add: await member.add_roles(*roles_to_add, reason="Player death sync")
            if roles_to_remove: await member.remove_roles(*roles_to_remove, reason="Player death sync")
        except discord.Forbidden:
            logger.error(f"Missing permissions to swap roles for {member.display_name}.")

    # 4. Welcome to the Graveyard
    mention_str = member.mention if member else f"<@{player.user_id}>"
    
    if setup.get("graveyard_channel_id"):
        gy_channel = guild.get_channel(setup["graveyard_channel_id"])
        if gy_channel:
            await gy_channel.send(
                f"👻 {mention_str} ha cruzado al otro lado. Bienvenido/a al cementerio.\n"
                f"*(Causa de muerte: {reason})*"
            )

    # 5. Audit Log for the Game Master
    if setup.get("log_channel_id"):
        log_channel = guild.get_channel(setup["log_channel_id"])
        if log_channel:
            role_name = player.role.name if getattr(player, "role", None) else "Rol Desconocido"
            await log_channel.send(f"💀 **AUDITORÍA DE MUERTE:** {mention_str} (**{role_name}**) ha muerto. Razón: {reason}")