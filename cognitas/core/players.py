# cognitas/core/players.py
import re
import discord
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
