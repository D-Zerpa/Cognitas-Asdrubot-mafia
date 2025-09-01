# cognitas/core/reminders.py
from __future__ import annotations

import re
import time
import asyncio
from typing import List, Optional

import discord

from .state import game

_DURATION_RX = re.compile(r"^\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*$", re.I)

def parse_duration_to_seconds(s: str) -> int:
    if not s:
        return 0
    s = s.strip().lower().replace(" ", "")
    if not s:
        return 0
    if s.endswith("m") and s[:-1].isdigit():
        return int(s[:-1]) * 60
    if s.endswith("h") and s[:-1].isdigit():
        return int(s[:-1]) * 3600
    m = _DURATION_RX.match(s)
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mm = int(m.group(2) or 0)
    return h * 3600 + mm * 60

async def _safe_send(chan: discord.abc.Messageable, content: str):
    try:
        await chan.send(content)
    except Exception as e:
        print(f"[reminders] send error in #{getattr(chan, 'id', '?')}: {e!r}")

def _cancel_task_safe(task: Optional[asyncio.Task]):
    try:
        if task and not task.done():
            task.cancel()
    except Exception:
        pass

async def _timer_worker(
    bot: discord.Client,
    *,
    guild_id: int,
    channel_id: int,
    checkpoints_minutes_desc: List[int],
    deadline_epoch: int,
    phase_label: str,  # "Day" or "Night"
):
    try:
        cps = sorted({int(m) for m in checkpoints_minutes_desc if int(m) > 0}, reverse=True)
        sent = set()

        while True:
            now = int(time.time())
            secs_left = deadline_epoch - now
            if secs_left <= 0:
                break

            minutes_left = secs_left // 60
            for m in list(cps):
                if minutes_left <= m and m not in sent:
                    try:
                        guild = bot.get_guild(guild_id)
                        if not guild:
                            break
                        try:
                            chan = guild.get_channel_or_thread(channel_id)
                        except AttributeError:
                            chan = guild.get_channel(channel_id)
                        if not chan:
                            break
                        abs_ts = f"<t:{deadline_epoch}:F>"
                        rel_ts = f"<t:{deadline_epoch}:R>"
                        await _safe_send(
                            chan,
                            f"⏰ **{phase_label}** — **{m} min** remaining (ends {rel_ts}, {abs_ts})."
                        )
                        sent.add(m)
                    except Exception as e:
                        print(f"[reminders] checkpoint error {m}m ({phase_label}): {e!r}")

            sleep_for = min(20, max(5, secs_left / 6))
            await asyncio.sleep(sleep_for)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[reminders] worker crash ({phase_label}): {e!r}")

async def start_day_timer(
    bot: discord.Client,
    guild_id: int,
    channel_id: int,
    *,
    checkpoints: List[int],
):
    try:
        _cancel_task_safe(getattr(game, "day_timer_task", None))
        deadline = getattr(game, "day_deadline_epoch", None)
        if not deadline:
            return
        task = bot.loop.create_task(
            _timer_worker(
                bot,
                guild_id=guild_id,
                channel_id=channel_id,
                checkpoints_minutes_desc=checkpoints,
                deadline_epoch=deadline,
                phase_label="Day",
            )
        )
        game.day_timer_task = task
        print(f"[reminders] Day timer started (guild={guild_id}, channel={channel_id}, deadline={deadline}).")
    except Exception as e:
        print(f"[reminders] start_day_timer error: {e!r}")

async def start_night_timer(
    bot: discord.Client,
    guild_id: int,
    channel_id: int,
    *,
    checkpoints: List[int],
):
    """
    Night timer now receives channel_id explicitly (works fine for a single shared channel).
    """
    try:
        _cancel_task_safe(getattr(game, "night_timer_task", None))
        deadline = getattr(game, "night_deadline_epoch", None)
        if not deadline:
            return
        task = bot.loop.create_task(
            _timer_worker(
                bot,
                guild_id=guild_id,
                channel_id=channel_id,
                checkpoints_minutes_desc=checkpoints,
                deadline_epoch=deadline,
                phase_label="Night",
            )
        )
        game.night_timer_task = task
        print(f"[reminders] Night timer started (guild={guild_id}, channel={channel_id}, deadline={deadline}).")
    except Exception as e:
        print(f"[reminders] start_night_timer error: {e!r}")

def cancel_all_timers():
    _cancel_task_safe(getattr(game, "day_timer_task", None))
    _cancel_task_safe(getattr(game, "night_timer_task", None))
    game.day_timer_task = None
    game.night_timer_task = None


