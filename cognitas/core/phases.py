from __future__ import annotations

import time
import asyncio
import discord
from typing import Optional

from ..config import REMINDER_CHECKPOINTS
from .state import game
from .storage import save_state
from .logs import log_event
from .. import config as cfg
from .reminders import (
    parse_duration_to_seconds,
    start_day_timer,
    start_night_timer,
)

def _get_channel_or_none(guild: discord.Guild, chan_id: int | None) -> discord.TextChannel | None:
    if not chan_id:
        return None
    ch = guild.get_channel(chan_id)
    return ch if isinstance(ch, (discord.TextChannel, discord.Thread)) else None

def _ensure_day_channel(ctx) -> discord.TextChannel:
    """Ensure day channel is configured and exists; raise RuntimeError if not."""
    guild: discord.Guild = ctx.guild
    ch = _get_channel_or_none(guild, getattr(game, "day_channel_id", None))
    if not ch:
        raise RuntimeError("Day channel is not configured or no longer exists. Set it with `/set_day_channel`.")
    return ch


async def start_day(
    ctx,
    *,
    duration_str: str = "24h",
    target_channel: Optional[discord.TextChannel] = None,
    force: bool = False,
):
    """
    Start the Day phase:
    - Resolve Day channel (explicit > configured default) and validate it
    - Compute & store deadline
    - Open channel for @everyone messages
    - Launch configured reminders
    - Reset /vote end_day (2/3) requests
    """

    # Validate/resolve channel
    try:
        day_ch = target_channel or _ensure_day_channel(ctx)
    except RuntimeError as e:
        return await ctx.reply(str(e))

    # Game over guard
    if getattr(game, "game_over", False):
        return await ctx.reply("The game is already finished. Start a new one before starting a Day.")

    # Parse duration
    seconds = parse_duration_to_seconds(duration_str)
    if seconds <= 0:
        return await ctx.reply("Invalid duration. Valid examples: `24h`, `90m`, `1h30m`.")

    # If there's an active Day and not forcing, inform and exit
    if hasattr(game, "day_deadline_epoch") and game.day_deadline_epoch and not force:
        chan = ctx.guild.get_channel(getattr(game, "day_channel_id", None))
        when = f"<t:{game.day_deadline_epoch}:R>"
        return await ctx.reply(
            f"There is already an active Day in {chan.mention if chan else '#?'} (ends {when}). "
            f"Use `force` to restart it."
        )

    # If forcing, cancel previous Day timer (if any)
    if force and getattr(game, "day_timer_task", None) and not game.day_timer_task.done():
        game.day_timer_task.cancel()
        game.day_timer_task = None

    # Decide Day channel (explicit > configured > current)
    target = day_ch or ctx.guild.get_channel(getattr(game, "day_channel_id", 0)) or ctx.channel

    # Initialize / normalize Day number
    if not hasattr(game, "current_day_number") or game.current_day_number is None:
        game.current_day_number = int(getattr(cfg, "START_AT_DAY", 1)) or 1
    else:
        game.current_day_number = max(1, int(game.current_day_number))

    # Persist Day state
    game.phase = "day"
    game.day_channel_id = target.id
    game.day_deadline_epoch = int(time.time()) + seconds

    # Reset early end-day requests (2/3)
    game.end_day_votes = set()

    save_state("state.json")

    # Open channel to @everyone for sending
    try:
        overw = target.overwrites_for(ctx.guild.default_role)
        overw.send_messages = True
        await target.set_permissions(ctx.guild.default_role, overwrite=overw)
    except Exception:
        # Non-fatal: permissions might already be open
        pass

    # Announce Day start
    await target.send(
        f"🌞 **Day {game.current_day_number} has begun.**\n"
        f"Ends: <t:{game.day_deadline_epoch}:F> (**<t:{game.day_deadline_epoch}:R>**)\n"
        f"Use `/vote cast @player` to vote or `/vote end_day` to request ending the Day with no lynch."
    )

    # Expansion hook (e.g., SMT moon phases)
    exp = getattr(game, "expansion", None)
    if exp:
        try:
            exp.on_phase_change(game, "day")
        except Exception:
            pass

    # Launch Day reminders
    await start_day_timer(ctx.bot, ctx.guild.id, target.id, checkpoints=REMINDER_CHECKPOINTS)

    # Log event
    await log_event(ctx.bot, ctx.guild.id, "PHASE_START", phase="Day", deadline=game.day_deadline_epoch)

    # Clean up the invoking message (if any; slash interactions may not have a message)
    try:
        if getattr(ctx, "message", None):
            await ctx.message.delete(delay=2)
    except Exception:
        pass



async def end_day(
    ctx,
    *,
    closed_by_threshold: bool = False,
    lynch_target_id: Optional[int] = None,
):
    """
    Cierra la fase de Día:
    - Cierra canal para @everyone (send_messages=False)
    - Anuncia resultado (con o sin linchamiento)
    - Limpia votos y deadline
    - NO inicia la Night automáticamente (eso lo controla el mod)
    """
    chan = ctx.guild.get_channel(getattr(game, "day_channel_id", None))
    if not chan:
        return await ctx.reply("No hay canal de Día activo configurado.")

    # Cerrar canal para enviar
    if lynch_target_id:
        await chan.send(f"⚖️ **Termina el Día.** Linchado: <@{lynch_target_id}>.")
        # Marca muerte en estado si corresponde
        uid = str(lynch_target_id)
        if uid in game.players:
            game.players[uid]["alive"] = False
    else:
        reason = "2/3 de solicitudes" if closed_by_threshold else "sin mayoría"
        await chan.send(f"⚖️ **Termina el Día sin linchamiento** ({reason}).")

    # Lock after announcing
    overw = chan.overwrites_for(ctx.guild.default_role)
    overw.send_messages = False
    await chan.set_permissions(ctx.guild.default_role, overwrite=overw)

    # Limpiar estado del Día
    game.votes = {}
    game.end_day_votes = set()
    game.day_deadline_epoch = None

    # Cancela timer de Día si sigue vivo
    if getattr(game, "day_timer_task", None) and not game.day_timer_task.done():
        game.day_timer_task.cancel()
    game.day_timer_task = None

    save_state("state.json")

    # Se registra el linchamiento

    if lynch_target_id:
        await log_event(ctx.bot, ctx.guild.id, "LYNCH", target_id=str(lynch_target_id))
    await log_event(ctx.bot, ctx.guild.id, "PHASE_END", phase="Day")

    # Limpia el comando del chat
    try:
        await ctx.message.delete(delay=2)
    except Exception:
        pass


async def start_night(
    ctx,
    *,
    duration_str: str = "12h",
    night_channel: Optional[discord.TextChannel] = None,
    next_day_channel: Optional[discord.TextChannel] = None,
):
    """
    Inicia la fase de Night:
    - Define canal de Night (por defecto, canal actual)
    - Calcula y guarda deadline
    - (Opcional) define canal del próximo Día para abrirlo al amanecer
    - Lanza recordatorios configurados
    """
    seconds = parse_duration_to_seconds(duration_str)
    if seconds <= 0:
        return await ctx.reply("Duración inválida. Ejemplos válidos: `12h`, `8h`, `45m`.")

    nchan = night_channel or ctx.channel
    game.night_channel_id = nchan.id
    game.night_deadline_epoch = int(time.time()) + seconds

    if next_day_channel:
        game.next_day_channel_id = next_day_channel.id
    else:
        # Si ya había una configuración previa, la conservamos
        game.next_day_channel_id = getattr(game, "next_day_channel_id", None)

    save_state("state.json")

    await nchan.send(
        f"🌙 **Night {game.current_day_number} iniciada.**\n"
        f"Finaliza: <t:{game.night_deadline_epoch}:F> (**<t:{game.night_deadline_epoch}:R>**)\n"
        f"Use `/act` to register your night action (if applicable to your role)."
    )

    # Hook de expansión (p.ej., fases lunares SMT)
    exp = getattr(game, "expansion", None)
    if exp:
        try:
            exp.on_phase_change(game, "night")
        except Exception:
            pass

    await start_night_timer(ctx.bot, ctx.guild.id, checkpoints=REMINDER_CHECKPOINTS)
    await log_event(ctx.bot, ctx.guild.id, "PHASE_START", phase="Night", deadline=game.night_deadline_epoch)

    try:
        await ctx.message.delete(delay=2)
    except Exception:
        pass


async def end_night(ctx):
    """
    Cierra la Night:
    - Anuncia amanecer
    - Incrementa contador de Día
    - Resetea deadline/timer de Night
    - (Opcional) abre canal del próximo Día si está configurado
    """
    nchan = ctx.guild.get_channel(getattr(game, "night_channel_id", None)) or ctx.channel
    await nchan.send("🌅 **Termina la Night.** Preparando el siguiente Día…")

    # Incrementar número del Día
    game.current_day_number = max(1, int(getattr(game, "current_day_number", 1))) + 1

    # Limpiar deadline y timer de Night
    game.night_deadline_epoch = None
    if getattr(game, "night_timer_task", None) and not game.night_timer_task.done():
        game.night_timer_task.cancel()
    game.night_timer_task = None

    save_state("state.json")

    # Abrir canal del próximo Día si está configurado
    if getattr(game, "next_day_channel_id", None):
        dchan = ctx.guild.get_channel(game.next_day_channel_id)
        if dchan:
            overw = dchan.overwrites_for(ctx.guild.default_role)
            overw.send_messages = True
            await dchan.set_permissions(ctx.guild.default_role, overwrite=overw)
            await dchan.send(f"🌞 **Día {game.current_day_number} ha amanecido.**")

    await log_event(ctx.bot, ctx.guild.id, "PHASE_END", phase="Night")

    try:
        await ctx.message.delete(delay=2)
    except Exception:
        pass

async def _autoclose_after(bot: discord.Client, guild_id: int, phase: str, unix_deadline: int):
    """Wait until deadline and then notify to close if still in that phase."""
    now = int(time.time())
    delay = max(0, unix_deadline - now)
    await asyncio.sleep(delay)
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    current_phase = getattr(game, "phase", None)
    if current_phase != phase:
        return
    ch = _get_channel_or_none(guild, getattr(game, "day_channel_id", None))
    if ch:
        try:
            await ch.send(f"⏰ Deadline reached for **{phase}**. Please close the phase with `/end_{phase}`.")
        except Exception:
            pass

async def rehydrate_timers(bot: discord.Client, guild: discord.Guild):
    """
    Restore awareness of ongoing Day/Night based on stored deadlines.
    - If deadline is in the future → announce remaining time and arm a soft autoclose notice.
    - If deadline is past → prompt admins to close manually.
    """
    phase = getattr(game, "phase", None)
    if phase not in ("day", "night"):
        return

    dl = getattr(game, f"{phase}_deadline_epoch", None)
    if not dl:
        return

    ch = _get_channel_or_none(guild, getattr(game, "day_channel_id", None))
    if not ch:
        return

    try:
        ts = int(dl)
    except Exception:
        return

    now = int(time.time())
    if ts > now:
        await ch.send(f"🔄 Restored **{phase}**. Deadline <t:{ts}:R>.")
        asyncio.create_task(_autoclose_after(bot, guild.id, phase, ts))
    else:
        await ch.send(f"⚠️ Stored deadline for **{phase}** has passed (<t:{ts}:R>). Please close with `/end_{phase}`.")