import os
import discord
from .state import game       # tu GameState existente
from .roles import load_roles
from .storage import save_state
from .logs import log_event
import unicodedata


def _norm_key(s: str) -> str:
    """Normaliza la clave para lookup case-insensitive y sin acentos."""
    if not isinstance(s, str):
        return ""
    # quita espacios extremos y normaliza acentos
    s = unicodedata.normalize("NFKD", s.strip())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.upper()

def _extract_role_defaults(role_def: dict) -> dict:
    """
    Obtiene defaults robusto según el profile:
    - SMT:        role_def["flags"]
    - Otros:      role_def["defaults"] | role_def["base_flags"] | role_def["abilities"]["defaults"]
    """
    if not isinstance(role_def, dict):
        return {}
    # SMT
    if isinstance(role_def.get("flags"), dict):
        return role_def["flags"]
    # Otros
    if isinstance(role_def.get("defaults"), dict):
        return role_def["defaults"]
    if isinstance(role_def.get("base_flags"), dict):
        return role_def["base_flags"]
    abilities = role_def.get("abilities")
    if isinstance(abilities, dict) and isinstance(abilities.get("defaults"), dict):
        return abilities["defaults"]
    return {}

def _build_roles_index(roles_def) -> dict:
    """
    Devuelve un índice robusto: KEY normalizada -> role_def
    Acepta 'code' | 'id' | 'name' + 'aliases' en cualquier combinación.
    """
    roles_list = []
    if isinstance(roles_def, dict):
        roles_list = list(roles_def.get("roles") or [])
    elif isinstance(roles_def, list):
        roles_list = roles_def

    idx = {}
    for r in roles_list:
        if not isinstance(r, dict):
            continue
        keys = []
        for k in (r.get("code"), r.get("id"), r.get("name")):
            if isinstance(k, str) and k.strip():
                keys.append(_norm_key(k))
        for a in (r.get("aliases") or []):
            if isinstance(a, str) and a.strip():
                keys.append(_norm_key(a))
        # registra todas las variantes hacia el mismo role_def
        for key in keys:
            if key:
                idx[key] = r
    return idx

def _lookup_role(role_name: str, roles_index: dict, roles_def) -> dict | None:
    """Busca primero en el índice (rápido) y cae a escaneo del JSON si hiciera falta."""
    key = _norm_key(role_name or "")
    role_def = roles_index.get(key)
    if role_def:
        return role_def

    # Fallback defensivo (por si el índice aún no estaba construido)
    roles_list = []
    if isinstance(roles_def, dict):
        roles_list = list(roles_def.get("roles") or [])
    elif isinstance(roles_def, list):
        roles_list = roles_def

    for r in roles_list:
        if not isinstance(r, dict):
            continue
        main_key = _norm_key(r.get("code") or r.get("id") or r.get("name") or "")
        alias_hit = any(_norm_key(a) == key for a in (r.get("aliases") or []) if isinstance(a, str))
        if main_key == key or alias_hit:
            return r
    return None


async def set_channels(*, day: discord.TextChannel | None = None, admin: discord.TextChannel | None = None):
    if day is not None:
        game.day_channel_id = day.id
    if admin is not None:
        game.admin_channel_id = admin.id
    await save_state("state.json")

async def start(ctx, *, profile: str = "default", day_channel: discord.TextChannel | None = None, admin_channel: discord.TextChannel | None = None):
    """
    Inicia una partida con un profile de roles (default, smt, ...).
    - Carga roles_{profile}.json (o fallback default)
    - Resetea contadores básicos
    - Setea canales de día/admin si se pasan
    """
    
    game.profile = profile.lower()
    game.roles_def = load_roles(game.profile)
    game.roles = _build_roles_index(game.roles_def)
    game.expansion = _load_expansion_for(game.profile)  # <-- NUEVO


    # (Reseteos mínimos no destructivos de jugadores)
    game.votes = {}
    game.end_day_votes = set()
    game.game_over = False
    game.current_day_number = 0
    game.phase = "day"
    game.day_deadline_epoch = None
    game.night_deadline_epoch = None

    set_channels(day=day_channel or ctx.channel, admin=admin_channel)
    await save_state("state.json")

    chan = ctx.guild.get_channel(game.day_channel_id)
    await ctx.reply(
        f"🟢 **Game started** with profile **{game.profile}**.\n"
        f"Day channel: {chan.mention if chan else '#?'} | Roles file loaded."
    )
    await log_event(ctx.bot, ctx.guild.id, "GAME_START", profile=game.profile, day_channel_id=game.day_channel_id)


async def hard_reset(ctx_or_interaction):
    """
    Full reset que funciona con:
    - commands.Context (ctx)  -> usa ctx.reply(...)
    - discord.Interaction     -> usa interaction.response / followup
    """
    # 1) limpiar memoria
    game.players = {}
    game.votes = {}
    game.day_channel_id = None
    game.admin_channel_id = None
    game.default_day_channel_id = None
    game.current_day_number = 0
    game.day_deadline_epoch = None
    game.night_deadline_epoch = None
    game.profile = "default"
    game.roles_def = {}
    game.roles = {}
    game.night_actions = {}
    game.game_over = False
    # TODO: cancelar timers si existen

    # 2) borrar archivos
    for path in ("state.json", "state.json.bak", "status.json", "status.json.bak"):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except Exception:
            pass

    # 3) persistir estado vacío
    await save_state("state.json")

    # 4) responder al usuario (ctx o interaction)
    try:
        if isinstance(ctx_or_interaction, discord.Interaction):
            interaction = ctx_or_interaction
            if not interaction.response.is_done():
                await interaction.response.send_message("🧹 Game state fully reset.", ephemeral=True)
            else:
                await interaction.followup.send("🧹 Game state fully reset.", ephemeral=True)
        else:
            # commands.Context
            await ctx_or_interaction.reply("🧹 Game state fully reset.")
    except Exception:
        pass

    # 5) log al canal de logs (funciona con ambos)
    try:
        if isinstance(ctx_or_interaction, discord.Interaction):
            await log_event(ctx_or_interaction.client, ctx_or_interaction.guild.id, "GAME_RESET")
        else:
            await log_event(ctx_or_interaction.bot, ctx_or_interaction.guild.id, "GAME_RESET")
    except Exception:
        pass
 

async def finish(ctx, *, reason: str | None = None):
    game.game_over = True
    await save_state("state.json")
    await ctx.reply(f"🏁 **Game finished.** {('Reason: ' + reason) if reason else ''}".strip())
    await log_event(ctx.bot, ctx.guild.id, "GAME_FINISH", reason=reason or "-")


async def who(ctx, member: discord.Member | None = None):
    """
    Muestra info del jugador (rol si procede) o listado básico.
    """
    if member:
        uid = str(member.id)
        pdata = game.players.get(uid)
        if not pdata:
            return await ctx.reply("Jugador no registrado.")
        role = pdata.get("role") or "—"
        alive = "✅" if pdata.get("alive", True) else "☠️"
        return await ctx.reply(f"<@{uid}> — **{pdata.get('name','?')}** | Role: **{role}** | {alive}")
    # listado rápido si no se pasa miembro
    vivos = [u for u, p in game.players.items() if p.get("alive", True)]
    await ctx.reply(f"Jugadores vivos: {', '.join(f'<@{u}>' for u in vivos) if vivos else '—'}")

async def assign_role(ctx, member: discord.Member, role_name: str):
    """
    Asigna un rol a un jugador y aplica defaults (SMT: 'flags').
    """
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.")

    role_def = _lookup_role(role_name, getattr(game, "roles", {}) or {}, getattr(game, "roles_def", {}))
    if not role_def:
        return await ctx.reply(f"Unknown role: `{role_name}`")

    game.players[uid]["role"] = role_name

    # Merge defaults/flags sin sobreescribir lo existente
    defaults = _extract_role_defaults(role_def)
    if defaults:
        flags = game.players[uid].setdefault("flags", {})
        for k, v in defaults.items():
            flags.setdefault(k, v)

    await save_state("state.json")
    await ctx.reply(f"🎭 Role **{role_name}** assigned to <@{uid}>.")
    await log_event(ctx.bot, ctx.guild.id, "ASSIGN", user_id=str(member.id), role=role_name)




def _load_expansion_for(profile: str):
    if profile == "smt":
        from ..expansions.smt import SMTExpansion
        return SMTExpansion()
    return None

