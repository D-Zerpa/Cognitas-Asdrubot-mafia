# cognitas/core/logs.py
from __future__ import annotations
import discord
from .state import game
from .storage import save_state

def set_log_channel(channel: discord.TextChannel | None):
    """Guardar/eliminar el canal de logs en el estado."""
    game.log_channel_id = channel.id if channel else None
    save_state("state.json")

async def log_event(bot: discord.Client, guild_id: int, kind: str, **data):
    """
    Envía un embed al canal de logs configurado (si existe).
    kind: 'PHASE_START', 'PHASE_END', 'VOTE_CAST', 'VOTE_CLEAR', 'VOTES_CLEARED',
          'END_DAY_REQUEST', 'LYNCH', 'GAME_START', 'GAME_RESET', 'GAME_FINISH', 'ASSIGN'
    """
    chan_id = getattr(game, "log_channel_id", None)
    if not chan_id:
        return  # logs desactivados
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    chan = guild.get_channel(chan_id)
    if not chan:
        return

    color_map = {
        "PHASE_START": 0x2ecc71,
        "PHASE_END": 0xe67e22,
        "VOTE_CAST": 0x3498db,
        "VOTE_CLEAR": 0x95a5a6,
        "VOTES_CLEARED": 0x95a5a6,
        "END_DAY_REQUEST": 0xf1c40f,
        "LYNCH": 0xc0392b,
        "GAME_START": 0x1abc9c,
        "GAME_RESET": 0x9b59b6,
        "GAME_FINISH": 0x7f8c8d,
        "ASSIGN": 0x8e44ad,
    }
    title_map = {
        "PHASE_START": "Phase started",
        "PHASE_END": "Phase ended",
        "VOTE_CAST": "Vote cast",
        "VOTE_CLEAR": "Vote cleared",
        "VOTES_CLEARED": "All votes cleared",
        "END_DAY_REQUEST": "End-day request (2/3)",
        "LYNCH": "Lynch",
        "GAME_START": "Game started",
        "GAME_RESET": "Game reset",
        "GAME_FINISH": "Game finished",
        "ASSIGN": "Role assigned",
    }

    embed = discord.Embed(
        title=title_map.get(kind, kind),
        color=color_map.get(kind, 0x34495e),
    )

    # Campos comunes útiles
    day_no = getattr(game, "current_day_number", None)
    if day_no:
        embed.add_field(name="Day", value=str(day_no), inline=True)

    # Poner pares clave/valor del payload
    for k, v in data.items():
        # Renderizar user ids como mentions si parecen IDs
        if isinstance(v, str) and v.isdigit() and k.lower().endswith(("id", "uid", "user", "target")):
            v = f"<@{v}>"
        embed.add_field(name=k, value=str(v), inline=True)

    await chan.send(embed=embed)
