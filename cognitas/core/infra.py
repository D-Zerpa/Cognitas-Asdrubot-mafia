# cognitas/core/infra.py
from __future__ import annotations
from typing import Optional, Dict, Any, Tuple, List
import discord

from .state import game

ASDRU_TAG = "[ASDRUBOT]"  # marker in channel.topic
INFRA_KEY = "infra"       # game.infra[guild_id] = {...}

def _guild_key(guild_id: int) -> str:
    return str(guild_id)

def get_infra(guild_id: int) -> Dict[str, Any]:
    """Return (and initialize) the infra mapping for a guild."""
    infra_all = getattr(game, INFRA_KEY, None)
    if not isinstance(infra_all, dict):
        infra_all = {}
        setattr(game, INFRA_KEY, infra_all)
    data = infra_all.get(_guild_key(guild_id))
    if not isinstance(data, dict):
        data = {}
        infra_all[_guild_key(guild_id)] = data
    # shape (ids may be None)
    data.setdefault("categories", {})
    data.setdefault("channels", {})
    data.setdefault("roles_category_id", None)
    data.setdefault("role_channels", {})  # role_name -> channel_id
    data.setdefault("expansion_profile", None)
    return data

def set_infra(guild_id: int, mapping: Dict[str, Any]) -> None:
    infra_all = getattr(game, INFRA_KEY, None)
    if not isinstance(infra_all, dict):
        infra_all = {}
        setattr(game, INFRA_KEY, infra_all)
    infra_all[_guild_key(guild_id)] = mapping

def mark_topic(original: str | None) -> str:
    base = (original or "").strip()
    return base if ASDRU_TAG in base else (f"{ASDRU_TAG} {base}".strip())

def is_asdrubot_channel(ch: discord.abc.GuildChannel) -> bool:
    try:
        topic = getattr(ch, "topic", None)  # TextChannel only
        return bool(topic and ASDRU_TAG in topic)
    except Exception:
        return False

def as_overwrites_for_private(bot_member: discord.Member, *extra_can_view: discord.abc.Snowflake) -> Dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
    """Deny @everyone, allow bot + optional extra viewers."""
    overwrites = {
        bot_member.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        bot_member: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True),
    }
    for who in extra_can_view:
        overwrites[who] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    return overwrites

async def ensure_category(guild: discord.Guild, name: str) -> discord.CategoryChannel:
    cat = discord.utils.get(guild.categories, name=name)
    if cat:
        return cat
    return await guild.create_category(name=name, reason="Asdrubot terraform")

async def ensure_text_channel(
    guild: discord.Guild,
    name: str,
    *,
    category: discord.CategoryChannel | None,
    overwrites: Optional[Dict[discord.abc.Snowflake, discord.PermissionOverwrite]] = None,
    topic: Optional[str] = None,
) -> discord.TextChannel:
    ch = discord.utils.get(guild.text_channels, name=name, category=category)
    if ch:
        # ensure tag in topic
        try:
            if topic is not None and (ch.topic or "").find(ASDRU_TAG) == -1:
                await ch.edit(topic=mark_topic(topic))
        except Exception:
            pass
        return ch
    ch = await guild.create_text_channel(
        name=name,
        category=category,
        overwrites=overwrites,
        topic=mark_topic(topic or ""),
        reason="Asdrubot terraform",
    )
    return ch

# ---------- Day channel helpers (single public channel) ----------

def _resolve_day_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    infra = get_infra(guild.id)
    ch_id = (infra.get("channels") or {}).get("day")
    ch = guild.get_channel(ch_id) if ch_id else None
    if isinstance(ch, discord.TextChannel):
        return ch
    # fallback: try by name
    ch = discord.utils.get(guild.text_channels, name="day-chat")
    return ch if isinstance(ch, discord.TextChannel) else None

async def ensure_day_channel(guild: discord.Guild, *, category: Optional[discord.CategoryChannel] = None) -> discord.TextChannel:
    infra = get_infra(guild.id)
    ch = _resolve_day_channel(guild)
    if ch:
        return ch
    # Create if missing
    ch = await ensure_text_channel(guild, "day-chat", category=category, topic="Main game channel. " + ASDRU_TAG)
    infra.setdefault("channels", {})["day"] = ch.id
    set_infra(guild.id, infra)
    return ch

def _phase_channel_name(phase: str, number: int) -> str:
    """Discord lowercases channel names; use hyphens."""
    p = (phase or "day").lower()
    n = max(1, int(number or 1))
    return f"{p}-{n}"

def _phase_channel_topic(phase: str, number: int) -> str:
    """Human-friendly topic line + marker."""
    title = f"{phase.title()} {max(1, int(number or 1))}"
    return mark_topic(title)

async def rename_day_channel(guild: discord.Guild, *, phase: str, number: int) -> None:
    ch = _resolve_day_channel(guild)
    if not ch:
        return
    try:
        await ch.edit(
            name=_phase_channel_name(phase, number),
            topic=_phase_channel_topic(phase, number),
            reason="Asdrubot phase rename",
        )
    except Exception:
        pass

async def set_day_channel_posting(guild: discord.Guild, *, allow: bool) -> None:
    """Toggle @everyone send_messages in the day channel."""
    ch = _resolve_day_channel(guild)
    if not ch:
        return
    try:
        ow = ch.overwrites_for(guild.default_role)
        ow.view_channel = True
        ow.send_messages = bool(allow)
        await ch.set_permissions(guild.default_role, overwrite=ow, reason="Asdrubot phase posting toggle")
    except Exception:
        pass

# ---- Alive/Dead roles infra ----

def get_role_ids(guild_id: int) -> Dict[str, int]:
    infra = get_infra(guild_id)
    roles = (infra.get("roles") or {})
    out = {}
    if "alive" in roles:
        out["alive"] = int(roles["alive"])
    if "dead" in roles:
        out["dead"] = int(roles["dead"])
    return out

def set_roles(guild_id: int, *, alive: Optional[int] = None, dead: Optional[int] = None) -> None:
    infra = get_infra(guild_id)
    roles = infra.setdefault("roles", {})
    if alive is not None:
        roles["alive"] = int(alive)
    if dead is not None:
        roles["dead"] = int(dead)

async def ensure_role(
    guild: discord.Guild,
    name: str,
    *,
    colour: Optional[discord.Colour] = None,
    mentionable: bool = False,
    hoist: bool = False) -> discord.Role:
    
    # Case-insensitive lookup by name
    for r in guild.roles:
        if r.name.lower() == name.lower():
            return r
    # Create if missing (requires Manage Roles)
    role = await guild.create_role(
        name=name,
        colour=colour or discord.Colour.default(),
        mentionable=mentionable,
        hoist=hoist,
        reason="Asdrubot: ensure role",
    )
    return role

async def apply_alive_dead_role(
    guild: discord.Guild,
    member_id: int,
    *,
    alive: bool) -> None:
    try:
        member = guild.get_member(member_id) or await guild.fetch_member(member_id)
    except Exception:
        return

    ids = get_role_ids(guild.id)
    r_alive = guild.get_role(ids.get("alive")) if ids.get("alive") else None
    r_dead  = guild.get_role(ids.get("dead"))  if ids.get("dead")  else None
    if not (r_alive or r_dead):
        return  # roles not configured yet

    try:
        if alive:
            add = [r_alive] if r_alive and r_alive not in member.roles else []
            rem = [r_dead]  if r_dead  and r_dead  in member.roles else []
        else:
            add = [r_dead]  if r_dead  and r_dead  not in member.roles else []
            rem = [r_alive] if r_alive and r_alive in member.roles else []

        if add:
            await member.add_roles(*add, reason="Asdrubot: alive/dead role swap")
        if rem:
            await member.remove_roles(*rem, reason="Asdrubot: alive/dead role swap")
    except Exception:
        pass
