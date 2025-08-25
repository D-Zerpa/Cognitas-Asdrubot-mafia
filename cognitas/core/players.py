# cognitas/core/players.py
import re
import discord
from typing import Any
from enum import Enum
from .state import game
from .storage import save_state

NAME_RX = re.compile(r"\s+")

def _norm(name: str) -> str:
    return NAME_RX.sub(" ", name.strip()).lower()

def _ensure_player(uid: str, display_name: str | None = None):
    if uid not in game.players:
        game.players[uid] = {
            "uid": uid,
            "name": display_name or f"User-{uid}",
            "alive": True,
            "aliases": [],
            "flags": {},
            "effects": [],
        }

def _is_admin(ctx: discord.ext.commands.Context) -> bool:
    # Si ya tienes un sistema de mods/roles, reemplázalo aquí.
    return ctx.author.guild_permissions.administrator


def get_player_snapshot(user_id: str) -> dict:
    """
    Return a readonly snapshot of the player's state for display.
    Keys: uid, name, alive, role, voting_boost, vote_weight_field, hidden_vote,
          aliases, effects, flags, vote_weight_computed (if available).
    """
    p = game.players.get(user_id)
    if not p:
        return {}

    # Stored fields (safe defaults)
    name = p.get("name", f"User-{user_id}")
    alive = bool(p.get("alive", True))
    role = p.get("role")
    voting_boost = p.get("voting_boost")
    vote_weight_field = p.get("vote_weight")
    hidden_vote = bool(p.get("hidden_vote", False))
    aliases = list(p.get("aliases", []))
    effects = list(p.get("effects", []))
    flags = dict(p.get("flags", {}))

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
    }

async def list_players(ctx):
    if not game.players:
        return await ctx.reply("No hay jugadores registrados.")
    vivos = [p for p in game.players.values() if p.get("alive", True)]
    muertos = [p for p in game.players.values() if not p.get("alive", True)]
    def fmt(pl):
        return ", ".join(f"<@{p['uid']}> ({p['name']})" for p in pl) if pl else "—"
    await ctx.reply(
        f"**Vivos**: {fmt(vivos)}\n"
        f"**Muertos**: {fmt(muertos)}\n"
        f"**Total**: {len(game.players)}"
    )

async def register(ctx, member: discord.Member | None = None, *, name: str | None = None):
    if not _is_admin(ctx):
        return await ctx.reply("Solo admin puede registrar jugadores.")
    target = member or ctx.author
    uid = str(target.id)
    display = name or target.display_name
    _ensure_player(uid, display)
    game.players[uid]["name"] = display
    game.players[uid]["alive"] = True
    save_state("state.json")
    await ctx.reply(f"✅ Registrado: <@{uid}> como **{display}** (vivo).")

async def unregister(ctx, member: discord.Member):
    if not _is_admin(ctx):
        return await ctx.reply("Solo admin puede dar de baja.")
    uid = str(member.id)
    if uid in game.players:
        del game.players[uid]
        save_state("state.json")
        return await ctx.reply(f"🗑️ Eliminado del registro: <@{uid}>.")
    await ctx.reply("Ese jugador no estaba registrado.")

async def rename(ctx, member: discord.Member, *, new_name: str):
    if not _is_admin(ctx):
        return await ctx.reply("Solo admin puede renombrar.")
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Jugador no registrado.")
    game.players[uid]["name"] = new_name.strip()
    save_state("state.json")
    await ctx.reply(f"✏️ <@{uid}> ahora es **{new_name}**.")

# -------- alias --------

async def alias_show(ctx, member: discord.Member):
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Jugador no registrado.")
    aliases = game.players[uid].get("aliases", [])
    if not aliases:
        return await ctx.reply(f"<@{uid}> no tiene alias.")
    await ctx.reply(f"Alias de <@{uid}>: {', '.join('`'+a+'`' for a in aliases)}")

async def alias_add(ctx, member: discord.Member, *, alias: str):
    if not _is_admin(ctx):
        return await ctx.reply("Solo admin puede gestionar alias.")
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Jugador no registrado.")
    alias_n = _norm(alias)
    arr = game.players[uid].setdefault("aliases", [])
    if alias_n in arr:
        return await ctx.reply("Ese alias ya existe.")
    arr.append(alias_n)
    save_state("state.json")
    await ctx.reply(f"➕ Alias añadido a <@{uid}>: `{alias_n}`")

async def alias_del(ctx, member: discord.Member, *, alias: str):
    if not _is_admin(ctx):
        return await ctx.reply("Solo admin puede gestionar alias.")
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Jugador no registrado.")
    alias_n = _norm(alias)
    arr = game.players[uid].get("aliases", [])
    if alias_n not in arr:
        return await ctx.reply("Ese alias no existe.")
    arr.remove(alias_n)
    save_state("state.json")
    await ctx.reply(f"➖ Alias eliminado de <@{uid}>: `{alias_n}`")

class PlayerField(str, Enum):
    alive = "alive"
    name = "name"
    role = "role"
    voting_boost = "voting_boost"   # float/int
    vote_weight = "vote_weight"     # float/int
    hidden_vote = "hidden_vote"     # bool (for SMT / YHVH like effects)

ALLOWED_EDIT_FIELDS: dict[str, type] = {
    "alive": bool,
    "name": str,
    "role": str,
    "voting_boost": float,
    "vote_weight": float,
    "hidden_vote": bool,
}

def _parse_bool(s: str) -> bool:
    s = s.strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    raise ValueError("Expected boolean (true/false).")

def _coerce(value: str, to_type: type) -> Any:
    if to_type is bool:
        return _parse_bool(value)
    if to_type is float:
        return float(value)
    if to_type is int:
        return int(value)
    return str(value)

async def set_player_field(ctx, member: discord.Member, field: str, value: str):
    """Generic setter for whitelisted fields on player record."""
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.")
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.")
    field = field.strip().lower()
    if field not in ALLOWED_EDIT_FIELDS:
        return await ctx.reply(f"Unsupported field '{field}'. Allowed: {', '.join(ALLOWED_EDIT_FIELDS.keys())}")
    try:
        coerced = _coerce(value, ALLOWED_EDIT_FIELDS[field])
    except Exception as e:
        return await ctx.reply(f"Invalid value for '{field}': {e}")
    game.players[uid][field] = coerced
    save_state("state.json")
    await ctx.reply(f"✅ Set `{field}` = `{coerced}` for <@{uid}>.")

async def set_flag(ctx, member: discord.Member, key: str, value: str):
    """Set or update a flag key on a player (auto type-coerce)."""
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.")
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.")
    key = key.strip()
    # try to guess type: bool -> int -> float -> str
    try:
        coerced: Any
        try:
            coerced = _parse_bool(value)
        except Exception:
            try:
                coerced = int(value)
            except Exception:
                try:
                    coerced = float(value)
                except Exception:
                    coerced = value
        game.players[uid].setdefault("flags", {})[key] = coerced
        save_state("state.json")
        await ctx.reply(f"✅ Flag `{key}` set to `{coerced}` for <@{uid}>.")
    except Exception as e:
        await ctx.reply(f"Error setting flag: {e}")

async def del_flag(ctx, member: discord.Member, key: str):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.")
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.")
    flags = game.players[uid].get("flags", {})
    if key not in flags:
        return await ctx.reply("Flag not found.")
    del flags[key]
    save_state("state.json")
    await ctx.reply(f"🗑️ Flag `{key}` removed for <@{uid}>.")

async def add_effect(ctx, member: discord.Member, effect: str):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.")
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.")
    arr = game.players[uid].setdefault("effects", [])
    if effect in arr:
        return await ctx.reply("Effect already present.")
    arr.append(effect)
    save_state("state.json")
    await ctx.reply(f"✨ Effect `{effect}` added to <@{uid}>.")

async def remove_effect(ctx, member: discord.Member, effect: str):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.")
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.")
    arr = game.players[uid].get("effects", [])
    if effect not in arr:
        return await ctx.reply("Effect not found.")
    arr.remove(effect)
    save_state("state.json")
    await ctx.reply(f"🧹 Effect `{effect}` removed from <@{uid}>.")

async def set_alive(ctx, member: discord.Member, alive: bool):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.")
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.")
    game.players[uid]["alive"] = bool(alive)
    save_state("state.json")
    emoji = "☠️" if not alive else "💚"
    await ctx.reply(f"{emoji} Set `alive` = `{alive}` for <@{uid}>.")

async def kill(ctx, member: discord.Member):
    await set_alive(ctx, member, False)

async def revive(ctx, member: discord.Member):
    await set_alive(ctx, member, True)