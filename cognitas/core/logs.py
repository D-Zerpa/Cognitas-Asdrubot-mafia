# cognitas/core/logs.py
from __future__ import annotations
import discord
from .state import game
from .storage import save_state
from .infra import get_infra


# En cognitas/core/logs.py

async def set_log_channel(channel: discord.TextChannel | None):
    """
    Sets the log channel, syncing Legacy variables AND Infra.
    """
    # 1. Legacy
    game.admin_log_channel_id = channel.id if channel else None
    
    # 2. Infra (The Fix)
    # We need to fetch the guild ID. Since this func might not have context,
    # we assume the channel belongs to the active guild if provided.
    if channel:
        guild_id = channel.guild.id
        from .infra import get_infra, set_infra # local import to avoid circular dep
        
        infra = get_infra(guild_id)
        if "channels" not in infra: infra["channels"] = {}
        
        infra["channels"]["logs"] = channel.id
        set_infra(guild_id, infra)

    await save_state()

def _resolve_logs_channel(bot: discord.Client, guild_id: int) -> discord.abc.Messageable | None:
    guild = bot.get_guild(guild_id)
    if not guild:
        return None

    # Prefer infra channel
    try:
        infra = get_infra(guild_id)
        logs_id = (infra.get("channels", {}) or {}).get("logs")
        if logs_id:
            ch = guild.get_channel(logs_id) or guild.get_thread(logs_id)
            if ch:
                return ch
    except Exception:
        pass

    # Fallback: legacy game.admin_log_channel_id
    chan_id = getattr(game, "admin_log_channel_id", None)
    if chan_id:
        return guild.get_channel(chan_id) or guild.get_thread(chan_id)

    return None


async def log_event(bot: discord.Client, guild_id: int, kind: str, **data):
    """
    Send an embed to the configured log channel (if available).
    kind: 'PHASE_START', 'PHASE_END', 'VOTE_CAST', 'VOTE_CLEAR', 'VOTES_CLEARED',
          'END_DAY_REQUEST', 'LYNCH', 'GAME_START', 'GAME_RESET', 'GAME_FINISH', 'ASSIGN'
    """
    chan_id = getattr(game, "admin_log_channel_id", None)
    if not chan_id:
        return  # logging disabled
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    chan = _resolve_logs_channel(bot, guild_id)
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

    # Useful common fields
    day_no = getattr(game, "current_day_number", None)
    if day_no:
        embed.add_field(name="Day", value=str(day_no), inline=True)

    # Add payload key/value pairs
    for k, v in data.items():
        # Render user IDs as mentions if they look like IDs
        if isinstance(v, str) and v.isdigit() and k.lower().endswith(("id", "uid", "user", "target")):
            v = f"<@{v}>"
        embed.add_field(name=k, value=str(v), inline=True)

    await chan.send(embed=embed)
