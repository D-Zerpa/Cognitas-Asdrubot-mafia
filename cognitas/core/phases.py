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

# -------------------------
# Checkpoints normalization
# -------------------------

def _minutes_checkpoints_from_config(config_list, *, duration_seconds: int | None = None, minutes_left: int | None = None) -> list[int]:
    """
    Convert REMINDER_CHECKPOINTS into integer minutes.
    - Supports literal integers expressed in seconds (e.g., 4*3600, 15*60) or minutes.
    - Supports the string "half" meaning half the duration (if duration_seconds provided)
      or half the remaining time (if minutes_left provided and duration_seconds is None).
    Only returns values <= minutes_left when minutes_left is provided.
    """
    mins = []
    # Determine a sensible cap to filter by remaining time
    cap = None
    if minutes_left is not None:
        try:
            cap = int(max(0, minutes_left))
        except Exception:
            cap = None

    for item in (config_list or []):
        val_min = None
        if isinstance(item, str) and item.lower() == "half":
            if duration_seconds is not None:
                val_min = max(1, int(round(duration_seconds / 120)))  # half duration in minutes
            elif minutes_left is not None:
                val_min = max(1, int(round(minutes_left / 2)))
        elif isinstance(item, (int, float)):
            # Treat as seconds if >= 60, otherwise as minutes
            if item >= 60:
                val_min = int((int(item) + 59) // 60)  # ceil to minutes
            else:
                val_min = int(item)
        # ignore unsupported types silently

        if val_min is not None:
            if cap is None or val_min <= cap:
                mins.append(val_min)

    # Always include 1-minute if within cap and not present
    if cap is not None and cap >= 1 and 1 not in mins:
        mins.append(1)

    # Deduplicate and sort descending (worker checks equality against minutes_left)
    mins = sorted(set(int(m) for m in mins if m > 0), reverse=True)
    return mins


def _get_channel_or_none(guild: discord.Guild, chan_id: int | None) -> discord.abc.GuildChannel | discord.Thread | None:
    if not chan_id:
        return None
    try:
        ch = guild.get_channel_or_thread(chan_id)
    except AttributeError:
        ch = guild.get_channel(chan_id)
    return ch if isinstance(ch, (discord.abc.GuildChannel, discord.Thread)) else None


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

    guild: discord.Guild = ctx.guild

    # Resolve the target channel
    ch = target_channel or _get_channel_or_none(guild, getattr(game, "day_channel_id", None)) or ctx.channel
    if not isinstance(ch, (discord.TextChannel, discord.Thread)):
        return await ctx.reply("Day channel must be a text channel or a thread.")

    # Parse duration
    seconds = parse_duration_to_seconds(duration_str or "24h") or 24 * 3600

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
    target: discord.abc.Messageable = ch
    game.day_channel_id = ch.id
    game.phase = "day"

    # Compute and store deadline
    now = int(time.time())
    game.day_deadline_epoch = now + seconds

    # Open channel for @everyone
    try:
        everyone = ch.guild.default_role
        ow = ch.overwrites_for(everyone)
        ow.send_messages = True
        await ch.set_permissions(everyone, overwrite=ow)
    except Exception:
        pass

    # Announce
    abs_ts = f"<t:{game.day_deadline_epoch}:F>"
    rel_ts = f"<t:{game.day_deadline_epoch}:R>"
    try:
        await ch.send(f"🌞 **Day started.** Deadline: {rel_ts} ({abs_ts}).")
    except Exception:
        pass

    # Persist state
    await save_state()

    # Launch Day reminders (normalized checkpoints)
    total_minutes = max(1, seconds // 60)
    cp = _minutes_checkpoints_from_config(cfg.REMINDER_CHECKPOINTS, minutes_left=total_minutes)
    await start_day_timer(ctx.bot, ctx.guild.id, target.id, checkpoints=cp)
    asyncio.create_task(_autoclose_after(ctx.bot, ctx.guild.id, "day", game.day_deadline_epoch))

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
    Close the Day phase:
    - Close channel for @everyone messages
    - Announce result (with or without lynch)
    - Clear deadline and cancel timer
    """
    guild: discord.Guild = ctx.guild
    ch = _get_channel_or_none(guild, getattr(game, "day_channel_id", None))
    if not ch:
        return await ctx.reply("No Day channel configured.")

    # Announce end
    if lynch_target_id:
        try:
            await ch.send(f"⚖️ **Day has ended.** Lynched: <@{lynch_target_id}>.")
        except Exception:
            pass
        # Mark player as dead if tracked
        try:
            uid = str(lynch_target_id)
            if hasattr(game, "players") and uid in game.players:
                game.players[uid]["alive"] = False
        except Exception:
            pass
    elif closed_by_threshold:
        try:
            await ch.send("⛔ **Day has ended** due to /vote end_day threshold.")
        except Exception:
            pass
    else:
        try:
            await ch.send("🌇 **Day has ended.**")
        except Exception:
            pass

    # Close messages for @everyone
    try:
        everyone = ch.guild.default_role
        ow = ch.overwrites_for(everyone)
        ow.send_messages = False
        await ch.set_permissions(everyone, overwrite=ow)
    except Exception:
        pass

    # Cancel timer
    try:
        if getattr(game, "day_timer_task", None) and not game.day_timer_task.done():
            game.day_timer_task.cancel()
    except Exception:
        pass
    game.day_timer_task = None
    game.day_deadline_epoch = None

    await save_state()
    await log_event(ctx.bot, ctx.guild.id, "PHASE_END", phase="Day")

    try:
        await ctx.reply("Day closed.")
    except Exception:
        pass


async def start_night(
    ctx,
    *,
    duration_str: str = "12h",
    target_channel: Optional[discord.TextChannel] = None,
    force: bool = False,
):
    """
    Start the Night phase:
    - Resolve Night channel (explicit > configured default) and validate it
    - Compute & store deadline
    - (Optionally) close channel to @everyone if you want a silent Night
    - Launch configured reminders
    """
    guild: discord.Guild = ctx.guild

    # Resolve channel
    ch = target_channel or _get_channel_or_none(guild, getattr(game, "night_channel_id", None)) or ctx.channel
    game.night_channel_id = ch.id
    if not isinstance(ch, (discord.TextChannel, discord.Thread)):
        return await ctx.reply("Night channel must be a text channel or a thread.")

    # Parse duration
    seconds = parse_duration_to_seconds(duration_str or "12h") or 12 * 3600

    # Prevent overlapping Nights unless forced
    if hasattr(game, "night_deadline_epoch") and game.night_deadline_epoch and not force:
        chan = ctx.guild.get_channel(getattr(game, "night_channel_id", None))
        when = f"<t:{game.night_deadline_epoch}:R>"
        return await ctx.reply(
            f"There is already an active Night in {chan.mention if chan else '#?'} (ends {when}). "
            f"Use `force` to restart it."
        )

    # If forcing, cancel previous Night timer
    if force and getattr(game, "night_timer_task", None) and not game.night_timer_task.done():
        game.night_timer_task.cancel()
        game.night_timer_task = None

    # Store channel & phase
    game.night_channel_id = ch.id
    game.phase = "night"

    # Compute and store deadline
    now = int(time.time())
    game.night_deadline_epoch = now + seconds

    # Optionally close @everyone for a silent night
    try:
        everyone = ch.guild.default_role
        ow = ch.overwrites_for(everyone)
        ow.send_messages = False
        await ch.set_permissions(everyone, overwrite=ow)
    except Exception:
        pass

    # Announce
    abs_ts = f"<t:{game.night_deadline_epoch}:F>"
    rel_ts = f"<t:{game.night_deadline_epoch}:R>"
    try:
        await ch.send(f"🌙 **Night started.** Deadline: {rel_ts} ({abs_ts}).")
    except Exception:
        pass

    await save_state()

    # Launch Night reminders (normalized checkpoints)
    total_minutes = max(1, seconds // 60)
    cp = _minutes_checkpoints_from_config(cfg.REMINDER_CHECKPOINTS, minutes_left=total_minutes)
    await start_night_timer(ctx.bot, ctx.guild.id, ch.id, checkpoints=cp)
    asyncio.create_task(_autoclose_after(ctx.bot, ctx.guild.id, "night", game.night_deadline_epoch))

    await log_event(ctx.bot, ctx.guild.id, "PHASE_START", phase="Night", deadline=game.night_deadline_epoch)

    try:
        if getattr(ctx, "message", None):
            await ctx.message.delete(delay=2)
    except Exception:
        pass


async def end_night(ctx):
    """
    Close the Night phase:
    - Announce end
    - Clear deadline and cancel timer
    """
    guild: discord.Guild = ctx.guild
    ch = _get_channel_or_none(guild, getattr(game, "night_channel_id", None))
    if not ch:
        return await ctx.reply("No Night channel configured.")

    try:
        await ch.send("🌅 **Night has ended.**")
    except Exception:
        pass

    # Cancel timer
    try:
        if getattr(game, "night_timer_task", None) and not game.night_timer_task.done():
            game.night_timer_task.cancel()
    except Exception:
        pass
    game.night_timer_task = None
    game.night_deadline_epoch = None

    await save_state()
    await log_event(ctx.bot, ctx.guild.id, "PHASE_END", phase="Night")

    try:
        await ctx.reply("Night closed.")
    except Exception:
        pass


async def _autoclose_after(bot: discord.Client, guild_id: int, phase: str, unix_deadline: int):
    """Wait until deadline and then automatically announce and close the phase if it is still active."""
    try:
        now = int(time.time())
        delay = max(0, unix_deadline - now)
        await asyncio.sleep(delay)
        guild = bot.get_guild(guild_id)
        if not guild:
            return
        # If the phase changed, abort
        if getattr(game, "phase", None) != phase:
            return

        # Resolve channel by phase
        chan_id = getattr(game, f"{phase}_channel_id", None)
        channel = guild.get_channel(chan_id) if chan_id else None

        # Send timeout message
        if channel:
            try:
                when_abs = f"<t:{unix_deadline}:F>"
                await channel.send(f"⏳ **{phase.capitalize()}** has ended by time ({when_abs}).")
            except Exception:
                pass

        # Auto close by invoking the corresponding end function
        try:
            if phase == "day":
                from .phases import end_day
                class _Ctx:
                    def __init__(self, guild): self.guild = guild
                    async def reply(self, *a, **k): pass
                await end_day(_Ctx(guild), closed_by_threshold=False, lynch_target_id=None)
            elif phase == "night":
                from .phases import end_night
                class _Ctx:
                    def __init__(self, guild): self.guild = guild
                    async def reply(self, *a, **k): pass
                await end_night(_Ctx(guild))
        except Exception as e:
            print(f"[phases] autoclose error for {phase}: {e!r}")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[phases] autoclose crash for {phase}: {e!r}")


async def rehydrate_timers(bot: discord.Client, guild: discord.Guild):
    """
    Restore ongoing Day/Night awareness from stored deadlines.
    - If the deadline is in the future → announce remaining time, relaunch reminders based on remaining time, and arm autoclose.
    - If the deadline has passed → announce and immediately autoclose.
    """
    try:
        phase = getattr(game, "phase", None)
        if phase not in ("day", "night"):
            return

        deadline = getattr(game, f"{phase}_deadline_epoch", None)
        if not deadline:
            return

        # Resolve channel for this phase
        chan_id = getattr(game, f"{phase}_channel_id", None)
        if not chan_id:
            # If Night has no dedicated channel id, fallback to Day channel id
            chan_id = getattr(game, "day_channel_id", None)
        try:
            ch = guild.get_channel_or_thread(chan_id) if chan_id else None
        except AttributeError:
            ch = guild.get_channel(chan_id) if chan_id else None
        if not ch:
            return

        now = int(time.time())
        ts = int(deadline)
        if ts > now:
            # Announce restore
            await ch.send(f"🔄 Restored **{phase}**. Deadline <t:{ts}:R>.")
            # Relaunch reminders using remaining time
            minutes_left = max(0, (ts - now + 59) // 60)
            cp = _minutes_checkpoints_from_config(cfg.REMINDER_CHECKPOINTS, minutes_left=minutes_left)
            if phase == "day":
                await start_day_timer(bot, guild.id, chan_id, checkpoints=cp)
            else:
                await start_night_timer(bot, guild.id, checkpoints=cp)
            # Arm autoclose
            asyncio.create_task(_autoclose_after(bot, guild.id, phase, ts))
        else:
            # Deadline already passed — announce and close
            await ch.send(f"⏰ Stored deadline for **{phase}** has already passed (<t:{ts}:R>). Closing automatically.")
            try:
                if phase == "day":
                    from .phases import end_day
                    class _Ctx:
                        def __init__(self, guild): self.guild = guild
                        async def reply(self, *a, **k): pass
                    await end_day(_Ctx(guild), closed_by_threshold=False, lynch_target_id=None)
                else:
                    from .phases import end_night
                    class _Ctx:
                        def __init__(self, guild): self.guild = guild
                        async def reply(self, *a, **k): pass
                    await end_night(_Ctx(guild))
            except Exception as e:
                print(f"[phases] rehydrate autoclose error for {phase}: {e!r}")
    except Exception as e:
        print(f"[phases] rehydrate_timers error: {e!r}")
