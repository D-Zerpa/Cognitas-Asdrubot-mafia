# cognitas/cogs/players.py
from __future__ import annotations

from typing import List, Tuple, Dict
import unicodedata
import re

import discord
from discord.ext import commands

# Estado/almacenamiento de tu juego
from ..core.state import game
from ..core.storage import save_state


# =========================
# Helpers
# =========================
def _norm(s: str) -> str:
    """Normaliza: minúsculas + trim + sin acentos/diacríticos."""
    s = (s or "").strip().casefold()
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    return s


def _ensure_defaults(uid: str) -> Dict:
    """Garantiza campos mínimos en la ficha del jugador."""
    pdata = game.players.setdefault(uid, {})
    pdata.setdefault("name", uid)
    pdata.setdefault("aliases", [])
    pdata.setdefault("alive", True)
    return pdata


def _build_index() -> Tuple[dict, dict]:
    """
    Devuelve:
      - index: dict[norm_key] = (display_name, uid)
      - names_by_uid: dict[uid] = display_name
    """
    index, names_by_uid = {}, {}
    for uid, pdata in game.players.items():
        uid = str(uid)
        pdata = _ensure_defaults(uid)
        display = pdata.get("name") or uid
        names_by_uid[uid] = display
        keys = [display, *(pdata.get("aliases") or [])]
        for k in keys:
            nk = _norm(k)
            if nk:
                index[nk] = (display, uid)
    return index, names_by_uid


def _resolve_name_to_uid(name_or_alias: str) -> Tuple[str | None, str | None, List[str]]:
    """Resuelve nombre/alias → (display, uid, suggestions)."""
    index, _ = _build_index()
    key = _norm(name_or_alias)
    if key in index:
        return index[key][0], index[key][1], []

    # Sugerencias básicas (prefijo > contiene)
    sugg_pool = []
    for nk, (disp, uid) in index.items():
        score = 0
        if key and nk.startswith(key):
            score += 2
        if key and key in nk:
            score += 1
        if score > 0:
            sugg_pool.append((score, disp))
    sugg_pool.sort(key=lambda x: (-x[0], x[1]))
    suggestions = [d for _, d in sugg_pool[:5]]
    return None, None, suggestions


def _chunk_text(text: str, limit: int = 1900) -> List[str]:
    """Parte un texto largo en trozos seguros para Discord."""
    buf, chunks = [], []
    for line in text.splitlines():
        if sum(len(x) + 1 for x in buf) + len(line) + 1 > limit:
            chunks.append("\n".join(buf))
            buf = []
        buf.append(line)
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def _uid_from_input(text: str) -> str | None:
    """
    Acepta: <@123>, <@!123>, '123' (ID), o un nombre/alias ya existente.
    Devuelve UID (str) o None.
    """
    if not text:
        return None
    text = text.strip()

    m = re.fullmatch(r"<@!?(\d+)>", text)
    if m:
        return m.group(1)

    if text.isdigit():
        return text

    # nombre/alias ya registrado
    disp, uid, _ = _resolve_name_to_uid(text)
    return uid


# =========================
# Cog
# =========================
class Players(commands.Cog):
    """Gestión de jugadores: listados, alias y registro."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- LIST ----------
    @commands.command(
        name="list",
        help="Lista jugadores. Uso: !list [all] [aliases] [filter <texto>]"
    )
    async def list_players(self, ctx: commands.Context, *args: str):
        """
        Muestra nombres válidos para !act.
        - !list -> solo vivos
        - !list all -> incluye muertos
        - !list aliases -> incluye alias
        - !list all aliases
        - !list filter <texto> -> filtra por contiene (en nombre/alias)
        """
        show_all = any(a.lower() == "all" for a in args)
        show_aliases = any(a.lower() == "aliases" for a in args)

        # filtro opcional
        filter_txt = ""
        if "filter" in [a.lower() for a in args]:
            try:
                idx = [a.lower() for a in args].index("filter")
                filter_txt = " ".join(args[idx + 1:]).strip()
            except Exception:
                filter_txt = ""

        rows = []
        fkey = _norm(filter_txt) if filter_txt else ""
        # Ordenar por nombre para salida consistente
        items = sorted(game.players.items(), key=lambda kv: _ensure_defaults(str(kv[0]))["name"].casefold())
        for uid, pdata in items:
            pdata = _ensure_defaults(str(uid))
            name = pdata["name"]
            alive = pdata.get("alive", True)
            if not show_all and not alive:
                continue

            aliases = pdata.get("aliases") or []
            # aplicar filtro si corresponde
            if fkey:
                hay = _norm(name)
                alns = [_norm(a) for a in aliases]
                if fkey not in hay and all(fkey not in a for a in alns):
                    continue

            alias_txt = f" — aliases: {', '.join(aliases)}" if (show_aliases and aliases) else ""
            status = "" if alive else " (dead)"
            rows.append(f"- {name}{status}{alias_txt}")

        if not rows:
            return await ctx.reply("No hay jugadores que mostrar con esos filtros.")

        header = "**Jugadores**"
        header += " (todos)" if show_all else " (vivos)"
        if show_aliases:
            header += " + aliases"
        if filter_txt:
            header += f" — filtro: `{filter_txt}`"
        header += ":\n"

        text = header + "\n".join(rows)
        for part in _chunk_text(text):
            await ctx.reply(part)

    # ---------- ALIAS GROUP ----------
    @commands.group(
        name="alias",
        invoke_without_command=True,
        help="Gestión de alias. Usa: !alias show [Nombre] | !alias add <@mención|id|Nombre> <alias> | !alias del <@mención|id|Nombre> <alias>"
    )
    async def alias_group(self, ctx: commands.Context):
        await ctx.reply("Uso: `!alias show [Nombre]`, `!alias add <@mención|id|Nombre> <alias>`, `!alias del <@mención|id|Nombre> <alias>`")

    @alias_group.command(name="show", help="Muestra alias de un jugador o de todos.")
    async def alias_show(self, ctx: commands.Context, *, name: str = ""):
        if not name.strip():
            # todos con alias
            rows = []
            # ordenar por nombre
            items = sorted(game.players.items(), key=lambda kv: _ensure_defaults(str(kv[0]))["name"].casefold())
            for uid, pdata in items:
                pdata = _ensure_defaults(str(uid))
                if pdata.get("aliases"):
                    rows.append(f"- **{pdata['name']}**: {', '.join(pdata['aliases'])}")
            if not rows:
                return await ctx.reply("Nadie tiene alias configurados.")
            text = "**Alias configurados:**\n" + "\n".join(rows)
            for part in _chunk_text(text):
                await ctx.reply(part)
            return

        disp, uid, sugg = _resolve_name_to_uid(name)
        if not uid:
            if sugg:
                return await ctx.reply(f"No encuentro a **{name}**. ¿Quisiste decir: {', '.join(sugg)} ?")
            return await ctx.reply(f"No encuentro a **{name}**.")
        pdata = _ensure_defaults(uid)
        aliases = pdata.get("aliases") or []
        if not aliases:
            return await ctx.reply(f"**{pdata['name']}** no tiene alias.")
        await ctx.reply(f"**{pdata['name']}** → {', '.join(aliases)}")

    @alias_group.command(name="add", help="Añade un alias a un jugador. Uso: !alias add <@mención|id|Nombre> <alias>")
    @commands.has_permissions(administrator=True)
    async def alias_add(self, ctx: commands.Context, who: str, *, new_alias: str):
        uid = _uid_from_input(who)
        if not uid:
            return await ctx.reply(f"No puedo resolver a **{who}**.")

        pdata = _ensure_defaults(uid)
        aliases = pdata.get("aliases") or []

        n_new = _norm(new_alias)
        if not n_new:
            return await ctx.reply("Alias inválido.")
        for a in aliases:
            if _norm(a) == n_new:
                return await ctx.reply(f"El alias **{new_alias}** ya existe para **{pdata['name']}**.")

        aliases.append(new_alias.strip())
        pdata["aliases"] = aliases
        save_state("state.json")
        await ctx.reply(f"✅ Alias añadido: **{pdata['name']}** → {', '.join(aliases)}")

    @alias_group.command(name="del", help="Elimina un alias de un jugador. Uso: !alias del <@mención|id|Nombre> <alias>")
    @commands.has_permissions(administrator=True)
    async def alias_del(self, ctx: commands.Context, who: str, *, alias_to_remove: str):
        uid = _uid_from_input(who)
        if not uid:
            return await ctx.reply(f"No puedo resolver a **{who}**.")

        pdata = _ensure_defaults(uid)
        aliases = pdata.get("aliases") or []
        if not aliases:
            return await ctx.reply(f"**{pdata['name']}** no tiene alias configurados.")

        n_del = _norm(alias_to_remove)
        new_aliases = [a for a in aliases if _norm(a) != n_del]
        if len(new_aliases) == len(aliases):
            return await ctx.reply(f"No encontré el alias **{alias_to_remove}** en **{pdata['name']}**.")

        pdata["aliases"] = new_aliases
        save_state("state.json")
        await ctx.reply(f"🗑️ Alias eliminado. **{pdata['name']}** → {', '.join(new_aliases) if new_aliases else '(sin alias)'}")

    # ---------- REGISTER / UNREGISTER ----------
    @commands.command(name="register", help="(Admin) Registra/actualiza un jugador. Uso: !register <@mención|id|Nombre> <NombreVisible>")
    @commands.has_permissions(administrator=True)
    async def register_player(self, ctx: commands.Context, who: str, *, display_name: str):
        uid = _uid_from_input(who)
        if not uid:
            return await ctx.reply(f"No puedo resolver a **{who}**. Usa @mención, ID numérico o un nombre ya existente.")

        pdata = _ensure_defaults(uid)
        old_name = pdata.get("name")
        pdata["name"] = display_name.strip()
        pdata.setdefault("aliases", [])
        pdata.setdefault("alive", True)

        save_state("state.json")
        if old_name and old_name != pdata["name"]:
            await ctx.reply(f"✅ Actualizado: <@{uid}> — **{old_name}** → **{pdata['name']}**")
        else:
            await ctx.reply(f"✅ Registrado: <@{uid}> como **{pdata['name']}**")

    @commands.command(name="unregister", help="(Admin) Elimina a un jugador. Uso: !unregister <@mención|id|Nombre>")
    @commands.has_permissions(administrator=True)
    async def unregister_player(self, ctx: commands.Context, who: str):
        uid = _uid_from_input(who)
        if not uid:
            return await ctx.reply(f"No puedo resolver a **{who}**.")
        if uid not in game.players:
            return await ctx.reply("Ese jugador no estaba registrado.")
        name = game.players[uid].get("name", uid)
        del game.players[uid]
        save_state("state.json")
        await ctx.reply(f"🗑️ Eliminado del registro: **{name}** (<@{uid}>)")

    # ---------- RENAME ----------
    @commands.command(name="rename", help="(Admin) Renombra a un jugador. Uso: !rename <NombreActual|@mención|id> <NombreNuevo>")
    @commands.has_permissions(administrator=True)
    async def rename_player(self, ctx: commands.Context, who: str, *, new_name: str):
        uid = _uid_from_input(who)
        if not uid:
            # Intento por nombre/alias (para mantener compatibilidad)
            disp, uid2, sugg = _resolve_name_to_uid(who)
            uid = uid2
            if not uid:
                if sugg:
                    return await ctx.reply(f"No encuentro a **{who}**. ¿Quisiste decir: {', '.join(sugg)} ?")
                return await ctx.reply(f"No encuentro a **{who}**.")

        pdata = _ensure_defaults(uid)
        old = pdata.get("name")
        pdata["name"] = new_name.strip()
        save_state("state.json")
        await ctx.reply(f"✏️ Renombrado: **{old}** → **{pdata['name']}**")


async def setup(bot: commands.Bot):
    await bot.add_cog(Players(bot))
