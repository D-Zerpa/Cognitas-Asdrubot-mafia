from __future__ import annotations

import time
import asyncio
import discord
from typing import Optional

from ..config import REMINDER_CHECKPOINTS
from .state import game
from .storage import save_state
from .reminders import (
    parse_duration_to_seconds,
    start_day_timer,
    start_night_timer,
)


async def start_day(
    ctx,
    *,
    duration_str: str = "24h",
    target_channel: Optional[discord.TextChannel] = None,
    force: bool = False,
):
    """
    Inicia la fase de Día:
    - Define canal de Día (mención > default > canal actual)
    - Calcula y guarda deadline
    - Abre el canal para mensajes (@everyone)
    - Lanza recordatorios configurados
    - Resetea contador de /vote end_day (2/3)
    """
    if getattr(game, "game_over", False):
        return await ctx.reply("La partida ya terminó. Inicia una nueva antes de comenzar un Día.")

    seconds = parse_duration_to_seconds(duration_str)
    if seconds <= 0:
        return await ctx.reply("Duración inválida. Ejemplos válidos: `24h`, `90m`, `1h30m`.")

    # Si hay un Día activo y no forzamos, avisa y sal
    if hasattr(game, "day_deadline_epoch") and game.day_deadline_epoch and not force:
        chan = ctx.guild.get_channel(getattr(game, "day_channel_id", None))
        when = f"<t:{game.day_deadline_epoch}:R>"
        return await ctx.reply(
            f"Ya hay un Día activo en {chan.mention if chan else '#?'} (termina {when}). "
            f"Usa `force` para reiniciarlo."
        )

    # Si forzamos, cancela timer anterior de Día
    if force and getattr(game, "day_timer_task", None) and not game.day_timer_task.done():
        game.day_timer_task.cancel()
        game.day_timer_task = None

    # Elegir canal de Día
    target = (
        target_channel
        or ctx.guild.get_channel(getattr(game, "day_channel_id", 0))
        or ctx.channel
    )

    # Inicializar / incrementar número de Día
    if not hasattr(game, "current_day_number") or game.current_day_number is None:
        game.current_day_number = 1
    else:
        game.current_day_number = max(1, int(game.current_day_number))

    # Guardar estado de Día
    game.day_channel_id = target.id
    game.day_deadline_epoch = int(time.time()) + seconds

    # Reset de votos y solicitudes de cierre anticipado (opcional según tu flow)
    # Si prefieres conservar votos entre reinicios de Día forzados, comenta la siguiente línea:
    game.end_day_votes = set()

    save_state("state.json")

    # Abrir canal a @everyone para enviar
    overw = target.overwrites_for(ctx.guild.default_role)
    overw.send_messages = True
    await target.set_permissions(ctx.guild.default_role, overwrite=overw)

    await target.send(
        f"🌞 **Día {game.current_day_number} iniciado.**\n"
        f"Finaliza: <t:{game.day_deadline_epoch}:F> (**<t:{game.day_deadline_epoch}:R>**)\n"
        f"Usa `!vote @jugador` para votar o `!vote_end_day` para solicitar cerrar el día sin linchamiento."
    )

    # Disparar hook de expansión (p.ej., fases lunares SMT)
    exp = getattr(game, "expansion", None)
    if exp:
        try:
            exp.on_phase_change(game, "day")
        except Exception:
            pass

    # Lanza recordatorios del Día
    await start_day_timer(ctx.bot, ctx.guild.id, target.id, checkpoints=REMINDER_CHECKPOINTS)

    # Limpia el comando del chat
    try:
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
    - NO inicia la Noche automáticamente (eso lo controla el mod)
    """
    chan = ctx.guild.get_channel(getattr(game, "day_channel_id", None))
    if not chan:
        return await ctx.reply("No hay canal de Día activo configurado.")

    # Cerrar canal para enviar
    overw = chan.overwrites_for(ctx.guild.default_role)
    overw.send_messages = False
    await chan.set_permissions(ctx.guild.default_role, overwrite=overw)

    if lynch_target_id:
        await chan.send(f"⚖️ **Termina el Día.** Linchado: <@{lynch_target_id}>.")
        # Marca muerte en estado si corresponde
        uid = str(lynch_target_id)
        if uid in game.players:
            game.players[uid]["alive"] = False
    else:
        reason = "2/3 de solicitudes" if closed_by_threshold else "sin mayoría"
        await chan.send(f"⚖️ **Termina el Día sin linchamiento** ({reason}).")

    # Limpiar estado del Día
    game.votes = {}
    game.end_day_votes = set()
    game.day_deadline_epoch = None

    # Cancela timer de Día si sigue vivo
    if getattr(game, "day_timer_task", None) and not game.day_timer_task.done():
        game.day_timer_task.cancel()
    game.day_timer_task = None

    save_state("state.json")

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
    Inicia la fase de Noche:
    - Define canal de Noche (por defecto, canal actual)
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
        f"🌙 **Noche {game.current_day_number} iniciada.**\n"
        f"Finaliza: <t:{game.night_deadline_epoch}:F> (**<t:{game.night_deadline_epoch}:R>**)\n"
        f"Usa `!act` para registrar tu acción nocturna (si procede)."
    )

    # Hook de expansión (p.ej., fases lunares SMT)
    exp = getattr(game, "expansion", None)
    if exp:
        try:
            exp.on_phase_change(game, "night")
        except Exception:
            pass

    await start_night_timer(ctx.bot, ctx.guild.id, checkpoints=REMINDER_CHECKPOINTS)

    try:
        await ctx.message.delete(delay=2)
    except Exception:
        pass


async def end_night(ctx):
    """
    Cierra la Noche:
    - Anuncia amanecer
    - Incrementa contador de Día
    - Resetea deadline/timer de Noche
    - (Opcional) abre canal del próximo Día si está configurado
    """
    nchan = ctx.guild.get_channel(getattr(game, "night_channel_id", None)) or ctx.channel
    await nchan.send("🌅 **Termina la Noche.** Preparando el siguiente Día…")

    # Incrementar número del Día
    game.current_day_number = max(1, int(getattr(game, "current_day_number", 1))) + 1

    # Limpiar deadline y timer de Noche
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

    try:
        await ctx.message.delete(delay=2)
    except Exception:
        pass
