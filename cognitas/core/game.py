import discord
from .state import game       # tu GameState existente
from .roles import load_roles
from .storage import save_state
from .logs import log_event

def _extract_role_defaults(role_def: dict) -> dict:
    """
    Extract default flags for a role, robust across profile schemas:
    - 'defaults' (preferred)
    - 'base_flags'
    - 'abilities': {'defaults': {...}}
    """
    if not isinstance(role_def, dict):
        return {}
    if isinstance(role_def.get("defaults"), dict):
        return role_def["defaults"]
    if isinstance(role_def.get("base_flags"), dict):
        return role_def["base_flags"]
    abilities = role_def.get("abilities")
    if isinstance(abilities, dict) and isinstance(abilities.get("defaults"), dict):
        return abilities["defaults"]
    return {}

def set_channels(*, day: discord.TextChannel | None = None, admin: discord.TextChannel | None = None):
    if day is not None:
        game.day_channel_id = day.id
    if admin is not None:
        game.admin_channel_id = admin.id
    save_state("state.json")

async def start(ctx, *, profile: str = "default", day_channel: discord.TextChannel | None = None, admin_channel: discord.TextChannel | None = None):
    """
    Inicia una partida con un profile de roles (default, smt, ...).
    - Carga roles_{profile}.json (o fallback default)
    - Resetea contadores básicos
    - Setea canales de día/admin si se pasan
    """
    
    game.profile = profile.lower()
    game.roles_def = load_roles(game.profile)
    roles_list = []
    if isinstance(game.roles_def, dict):
        roles_list = list(game.roles_def.get("roles") or [])
    elif isinstance(game.roles_def, list):
        roles_list = game.roles_def

    idx = {}
    for r in roles_list:
        if not isinstance(r, dict):
            continue
        keys = []
        for k in (r.get("code"), r.get("id"), r.get("name")):
            if isinstance(k, str) and k.strip():
                keys.append(k.strip().upper())
        for a in (r.get("aliases") or []):
            if isinstance(a, str) and a.strip():
                keys.append(a.strip().upper())
        for key in keys:
            idx[key] = r
    game.roles = idx  # dict: KEY -> role_def
    game.expansion = _load_expansion_for(game.profile)  # <-- NUEVO


    # (Reseteos mínimos no destructivos de jugadores)
    game.votes = {}
    game.end_day_votes = set()
    game.game_over = False
    game.current_day_number = 1
    game.day_deadline_epoch = None
    game.night_deadline_epoch = None

    set_channels(day=day_channel or ctx.channel, admin=admin_channel)
    save_state("state.json")

    chan = ctx.guild.get_channel(game.day_channel_id)
    await ctx.reply(
        f"🟢 **Game started** with profile **{game.profile}**.\n"
        f"Day channel: {chan.mention if chan else '#?'} | Roles file loaded."
    )
    await log_event(ctx.bot, ctx.guild.id, "GAME_START", profile=game.profile, day_channel_id=game.day_channel_id)


def reset():
    """
    Resetea por completo el estado de la partida (mantiene jugadores registrados).
    """
    game.votes = {}
    game.end_day_votes = set()
    game.game_over = False
    game.current_day_number = 1
    game.day_deadline_epoch = None
    game.night_deadline_epoch = None
    save_state("state.json")

async def finish(ctx, *, reason: str | None = None):
    game.game_over = True
    save_state("state.json")
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
    Assign a role to a player and merge default flags (if defined in the role).
    """
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.")

    key = (role_name or "").strip().upper()
    role_def = None
    try:
        role_def = getattr(game, "roles", {}).get(key)
    except Exception:
        role_def = None

    # Defensive fallback: scan roles_def if index was not built
    if not role_def:
        rd = getattr(game, "roles_def", {})
        roles_list = []
        if isinstance(rd, dict):
            roles_list = list(rd.get("roles") or [])
        elif isinstance(rd, list):
            roles_list = rd
        for r in roles_list:
            if not isinstance(r, dict):
                continue
            main_key = (r.get("code") or r.get("id") or r.get("name") or "").strip().upper()
            alias_hit = any(isinstance(a, str) and a.strip().upper() == key for a in (r.get("aliases") or []))
            if main_key == key or alias_hit:
                role_def = r
                break

    if not role_def:
        return await ctx.reply(f"Unknown role: `{role_name}`")

    game.players[uid]["role"] = role_name

    # Merge defaults without overwriting existing flags
    defaults = _extract_role_defaults(role_def)
    if isinstance(defaults, dict) and defaults:
        flags = game.players[uid].setdefault("flags", {})
        for k, v in defaults.items():
            flags.setdefault(k, v)

    save_state("state.json")
    await ctx.reply(f"🎭 Role **{role_name}** assigned to <@{uid}>.")
    await log_event(ctx.bot, ctx.guild.id, "ASSIGN", user_id=str(member.id), role=role_name)

    
    
# al final de core/game.py (o dentro de start())
def _load_expansion_for(profile: str):
    if profile == "smt":
        from ..expansions.smt import SMTExpansion
        return SMTExpansion()
    return None

