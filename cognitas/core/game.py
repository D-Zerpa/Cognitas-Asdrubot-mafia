import discord
from .state import game       # tu GameState existente
from .roles import load_roles
from .storage import save_state
from .logs import log_event

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
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Jugador no registrado.")
    # validar que existe en roles_def si quieres
    game.players[uid]["role"] = role_name
    save_state("state.json")
    await ctx.reply(f"🎭 Rol **{role_name}** asignado a <@{uid}>.")
    await log_event(ctx.bot, ctx.guild.id, "ASSIGN", user_id=str(member.id), role=role_name)
    
    
# al final de core/game.py (o dentro de start())
def _load_expansion_for(profile: str):
    if profile == "smt":
        from ..expansions.smt import SMTExpansion
        return SMTExpansion()
    return None

