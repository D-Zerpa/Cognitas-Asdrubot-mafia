from __future__ import annotations

import re
import discord
from discord.ext import commands
from typing import Any, Dict
from enum import Enum

from .state import game
from .storage import save_state
from ..status import engine as SE
from ..core.infra import get_role_ids

NAME_RX = re.compile(r"\s+")


def _norm(name: str) -> str:
    return NAME_RX.sub(" ", (name or "").strip())


def _slug(name: str) -> str:
    s = _norm(name).lower()
    return re.sub(r"[^a-z0-9\-]+", "-", s.replace(" ", "-")).strip("-") or "player"


def _ensure_player(uid: str, display_name: str | None = None):
    game.players.setdefault(uid, {
        "uid": uid,
        "name": display_name or f"User-{uid}",
        "alive": True,
        "aliases": [],
        "flags": {},
        "effects": [],
    })


def _is_admin(ctx: commands.Context | Any) -> bool:
    try:
        # Also works with our InteractionCtx adapter
        author = getattr(ctx, "author", None) or getattr(ctx, "user", None)
        return bool(getattr(getattr(author, "guild_permissions", None), "administrator", False))
    except Exception:
        return False


async def sanitize_votes_for_uid(uid: str):
    """
    Remove the player's active vote and end-day request when they die.
    Best-effort; ignores errors.
    """
    try:
        # Remove active vote
        if isinstance(getattr(game, "votes", None), dict) and uid in game.votes:
            del game.votes[uid]
        # Remove end-day request (supports legacy list/tuple)
        end_set = getattr(game, "end_day_votes", None)
        if isinstance(end_set, set) and uid in end_set:
            end_set.remove(uid)
        elif isinstance(end_set, (list, tuple)) and uid in end_set:
            s = set(end_set)
            s.discard(uid)
            game.end_day_votes = s
        await save_state()
    except Exception:
        # keep going; this is best-effort hygiene
        pass


def get_player_snapshot(user_id: str) -> dict:
    """
    Return a readonly snapshot of the player's state for display.
    Keys: uid, name, alive, role, voting_boost, vote_weight_field, hidden_vote,
          aliases, effects, flags, vote_weight_computed (if available).
    """
    p = (getattr(game, "players", {}) or {}).get(user_id)
    if not p:
        return {}

    # Stored fields (safe defaults)
    name = p.get("name", f"User-{user_id}")
    alive = bool(p.get("alive", True))
    role = p.get("role")
    voting_boost = p.get("voting_boost")
    vote_weight_field = p.get("vote_weight")
    hidden_vote = bool(flags.get("hidden_vote", False))
    aliases = list(p.get("aliases", []))
    effects = list(p.get("effects", []))
    flags = dict(p.get("flags", {}))

    #Role private channel id
    role_channel_id = p.get("role_channel_id")

    # Computed vote weight (if GameState exposes a helper)
    vote_weight_computed = None
    try:
        vote_weight_computed = game.vote_weight(user_id)  # may not exist in all builds
    except Exception:
        pass

    return {
        "uid": user_id,
        "name": name,
        "alive": alive,
        "role": role,
        "voting_boost": voting_boost,
        "vote_weight_field": vote_weight_field,
        "hidden_vote": hidden_vote,
        "aliases": aliases,
        "effects": effects,
        "flags": flags,
        "vote_weight_computed": vote_weight_computed,
        "role_channel_id": role_channel_id,
    }


# ----------------------------
# List & basic registration
# ----------------------------

async def list_players(ctx):
    players = getattr(game, "players", {}) or {}
    if not players:
        return await ctx.reply("No players registered.")
    alive = [p for p in players.values() if p.get("alive", True)]
    dead = [p for p in players.values() if not p.get("alive", True)]

    def fmt(pl):
        return ", ".join(f"<@{p['uid']}> ({p.get('name','?')})" for p in pl) if pl else "—"

    await ctx.reply(
        f"**Alive**: {fmt(alive)}\n"
        f"**Dead**: {fmt(dead)}\n"
        f"**Total**: {len(players)}"
    )


async def register(ctx, member: discord.Member | None = None, *, name: str | None = None):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    guild = getattr(ctx, "guild", None)
    if not guild:
        return await ctx.reply("Guild context required.", ephemeral=True)

    target = member or getattr(ctx, "author", None) or getattr(ctx, "user", None)
    if not target:
        return await ctx.reply("No target user provided.", ephemeral=True)

    uid = str(target.id)
    display = (name or getattr(target, "display_name", None) or f"User-{uid}").strip()

    _ensure_player(uid, display)
    game.players[uid]["name"] = display
    game.players[uid]["alive"] = True

    # Assign "Alive" role.

    ids = get_role_ids(guild.id)
    r_alive = guild.get_role(ids.get("alive")) if ids.get("alive") else None
    r_dead  = guild.get_role(ids.get("dead"))  if ids.get("dead")  else None

    try:
        if r_dead and r_dead in member.roles:
            await member.remove_roles(r_dead, reason="Asdrubot: registration -> Alive")
        if r_alive and r_alive not in member.roles:
            await member.add_roles(r_alive, reason="Asdrubot: registration -> Alive")
    except Exception:
        pass

    # --- Create or reuse player's private role channel ---
    game.players[uid]["role_channel_id"] = None

    await save_state()

    # Friendly confirmation (ephemeral)
    ch_mention = ""
    try:
        rcid = game.players[uid].get("role_channel_id")
        rch = guild.get_channel(rcid) if rcid else None
        if rch:
            ch_mention = f" — channel: {rch.mention}"
    except Exception:
        pass

    await ctx.reply(f"✅ Registered: <@{uid}> as **{display}** (alive).", ephemeral=True)

    # Optional: greet in private role channel
    try:
        rcid = game.players[uid].get("role_channel_id")
        rch = guild.get_channel(rcid) if rcid else None
        if rch:
            await rch.send(f"Welcome, <@{uid}>! This is your private role channel. Use `/act` here to perform your actions.")
    except Exception:
        pass



async def unregister(ctx, member: discord.Member):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid in game.players:
        p_data = game.players[uid]
        chan_id = p_data.get("role_channel_id")
        if chan_id:
            guild = ctx.guild
            channel = guild.get_channel(chan_id)
            if channel:
                try:
                    await channel.set_permissions(member, overwrite=None, reason="Unregister player")
                except Exception:
                    pass

        del game.players[uid]
        await save_state()
        return await ctx.reply(f"🗑️ Unregistered <@{uid}> and removed channel access.", ephemeral=True)
        
    await ctx.reply("Player was not registered.", ephemeral=True)


async def rename(ctx, member: discord.Member, *, new_name: str):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    game.players[uid]["name"] = _norm(new_name)
    await save_state()
    await ctx.reply(f"✏️ <@{uid}> is now **{new_name}**.", ephemeral=True)


# ----------------------------
# Aliases
# ----------------------------

async def alias_show(ctx, member: discord.Member):
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    aliases = game.players[uid].get("aliases", [])
    if not aliases:
        return await ctx.reply(f"<@{uid}> has no aliases.", ephemeral=True)
    await ctx.reply(f"Aliases for <@{uid}>: {', '.join('`'+a+'`' for a in aliases)}", ephemeral=True)


async def alias_add(ctx, member: discord.Member, *, alias: str):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    alias_n = _norm(alias)
    arr = game.players[uid].setdefault("aliases", [])
    if alias_n in arr:
        return await ctx.reply("Alias already exists.", ephemeral=True)
    arr.append(alias_n)
    await save_state()
    await ctx.reply(f"➕ Added alias to <@{uid}>: `{alias_n}`", ephemeral=True)


async def alias_del(ctx, member: discord.Member, *, alias: str):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    alias_n = _norm(alias)
    arr = game.players[uid].get("aliases", [])
    if alias_n not in arr:
        return await ctx.reply("Alias not found.", ephemeral=True)
    arr.remove(alias_n)
    await save_state()
    await ctx.reply(f"➖ Removed alias from <@{uid}>: `{alias_n}`", ephemeral=True)


# ----------------------------
# Edit API (replaces set_player_field)
# ----------------------------

class PlayerField(str, Enum):
    alive = "alive"
    name = "name"
    role = "role"
    # Left here for compatibility in snapshots; editing them must go via flags:
    voting_boost = "voting_boost"
    vote_weight = "vote_weight"
    hidden_vote = "hidden_vote"


# Fields that /player edit may suggest (safe), but we still accept custom ones.
SAFE_EDIT_FIELDS: Dict[str, type] = {
    "alive": bool,
    "name": str,
    "role": str,
    "effects": list,   # CSV → list[str]
    "notes": str,
    "alias": str,      # single alias field if you use it
}

# Fields that MUST be managed via flags (set_flag), not via edit.
PROTECTED_VOTE_FIELDS = {
    "hidden_vote", "voting_boost", "vote_weight", "no_vote", "silenced",
    "lynch_plus", "lynch_resistance", "needs_extra_votes",
}


def _parse_bool(s: str) -> bool:
    s = (s or "").strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    raise ValueError("Expected boolean (true/false).")


def _coerce_basic(value: str) -> Any:
    s = (value or "").strip()
    # boolean literals
    if re.fullmatch(r"(?i)(true|on|yes|y|1)", s):
        return True
    if re.fullmatch(r"(?i)(false|off|no|n|0)", s):
        return False
    # integer
    if re.fullmatch(r"[-+]?\d+", s):
        try:
            return int(s)
        except Exception:
            pass
    # default str
    return value


async def edit_player(ctx, member: discord.Member, field: str, value: str):
    """
    Safe, typed edit:
      - Redirects voting/lynch-specific fields to /player set_flag.
      - Coerces bool/int where reasonable; special cases for common fields.
    """
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    players = getattr(game, "players", {}) or {}
    if uid not in players:
        return await ctx.reply("Player not registered.", ephemeral=True)

    f = (field or "").strip()
    if not f:
        return await ctx.reply("Field name is required.", ephemeral=True)
    f_l = f.lower()

    # Guard rails: enforce flags path for voting/lynch
    if f_l in PROTECTED_VOTE_FIELDS:
        return await ctx.reply("Use **/player set_flag** for voting/lynch related fields.", ephemeral=True)

    p = players[uid]
    # Friendly typed edits
    if f_l in ("name", "display_name"):
        p["name"] = _norm(value)
    elif f_l == "alias":
        # if you use a single alias field
        p["alias"] = _norm(value)
    elif f_l == "role":
        p["role"] = _norm(value)
    elif f_l == "alive":
        try:
            alive_val = _parse_bool(value)
        except Exception as e:
            return await ctx.reply(f"Invalid boolean for `alive`: {e}", ephemeral=True)
        p["alive"] = bool(alive_val)
        if not alive_val:
            await _sanitize_votes_for_uid(uid)
    elif f_l == "effects":
        arr = [seg.strip() for seg in str(value).split(",") if seg.strip()]
        p["effects"] = arr
    elif f_l in ("notes", "note"):
        p["notes"] = str(value)
    else:
        # Generic best-effort coercion
        p[f] = _coerce_basic(value)

    await save_state()
    return await ctx.reply(f"✅ Set `{f}` = `{p.get(f_l, p.get(f, value))}` for <@{uid}>.", ephemeral=True)


# ----------------------------
# Flags API
# ----------------------------

async def set_flag(ctx, member: discord.Member, key: str, value: Any):
    """
    Set or update a flag key on a player (value already parsed/typed by the cog).
    """
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    key = (key or "").strip()
    if not key:
        return await ctx.reply("Flag key is required.", ephemeral=True)

    flags = game.players[uid].setdefault("flags", {})
    flags[key] = value
    await save_state()
    await ctx.reply(f"✅ Flag `{key}` set to `{value}` for <@{uid}>.", ephemeral=True)


async def del_flag(ctx, member: discord.Member, key: str):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    flags = game.players[uid].get("flags", {})
    if key not in flags:
        return await ctx.reply("Flag not found.", ephemeral=True)
    del flags[key]
    await save_state()
    await ctx.reply(f"🗑️ Flag `{key}` removed for <@{uid}>.", ephemeral=True)


# ----------------------------
# Effects
# ----------------------------

async def add_effect(ctx, member: discord.Member, effect: str):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    arr = game.players[uid].setdefault("effects", [])
    if effect in arr:
        return await ctx.reply("Effect already present.", ephemeral=True)
    arr.append(effect)
    await save_state()
    await ctx.reply(f"✨ Effect `{effect}` added to <@{uid}>.", ephemeral=True)


async def remove_effect(ctx, member: discord.Member, effect: str):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    arr = game.players[uid].get("effects", [])
    if effect not in arr:
        return await ctx.reply("Effect not found.", ephemeral=True)
    arr.remove(effect)
    await save_state()
    await ctx.reply(f"🧹 Effect `{effect}` removed from <@{uid}>.", ephemeral=True)


# ----------------------------
# Alive / Kill / Revive
# ----------------------------

async def set_alive(ctx, member: discord.Member, alive: bool):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)

    if not alive:
        # Unified death path
        await process_death(ctx, member.id, reason="Admin /kill")
        emoji = "☠️"
    else:
        # Unified revive path
        game.players[uid]["alive"] = True
        # IMPORTANT: Cleanse old statuses when reviving to prevent bugs
        SE.heal(game, uid, all_=True)
        
        from ..core.infra import apply_alive_dead_role
        await apply_alive_dead_role(ctx.guild, member.id, alive=True)
        await save_state()
        emoji = "💚"

    await ctx.reply(f"{emoji} Set `alive` = `{alive}` for <@{uid}>.", ephemeral=True)


async def process_death(ctx_or_guild, member_id: int | str, reason: str = "Unknown"):
    """
    Handle all side-effects of a player dying:
    - Set alive=False
    - Clear active votes/requests
    - Heal all statuses (poison, silence, etc)
    - Update Discord roles (Alive -> Dead)
    """
    uid = str(member_id)
    if uid not in game.players:
        return

    # a) Update state
    game.players[uid]["alive"] = False
    game.players[uid]["death_reason"] = reason
    
    # b) Clean up game mechanics
    await sanitize_votes_for_uid(uid)  
    SE.heal(game, uid, all_=True)      
    
    # c) Discord Roles
    guild = getattr(ctx_or_guild, "guild", ctx_or_guild)
    if guild:
        await apply_alive_dead_role(guild, int(member_id), alive=False)
    
    await save_state()

async def kill(ctx, member: discord.Member):
    guild: discord.Guild = ctx.guild
    await set_alive(ctx, member, False)
    await apply_alive_dead_role(ctx.guild, int(member.id), alive=False)


async def revive(ctx, member: discord.Member):
    guild: discord.Guild = ctx.guild
    await set_alive(ctx, member, True)
    await apply_alive_dead_role(ctx.guild, int(member.id), alive=True)