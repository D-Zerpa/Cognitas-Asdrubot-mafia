import asyncio, time
from typing import List, Union
from .state import game
from ..config import MENTION_EVERYONE, MENTION_ROLE_ID, REMINDER_CHECKPOINTS

# ------------------------
# Helpers
# ------------------------

def mention_prefix() -> str:
    if MENTION_ROLE_ID:
        return f"<@&{MENTION_ROLE_ID}> "
    return "@everyone " if MENTION_EVERYONE else ""

def parse_duration_to_seconds(text: str) -> int:
    """
    Parse '1d12h30m', '24h', '90m', '3600s' (or just '24' => hours) into seconds.
    """
    text = (text or "").strip().lower()
    if not text:
        return 0
    if text.isdigit():
        return int(text) * 3600
    total, num = 0, ""
    for ch in text:
        if ch.isdigit():
            num += ch
        else:
            if not num:
                continue
            val = int(num)
            if ch == 'd': total += val * 86400
            elif ch == 'h': total += val * 3600
            elif ch == 'm': total += val * 60
            elif ch == 's': total += val
            num = ""
    if num:
        total += int(num) * 3600
    return total

def _build_schedule(now: int, deadline: int, checkpoints: List[Union[int, str]]) -> List[int]:
    """
    Return list of epoch timestamps when reminders should fire.
    checkpoints: values in seconds-left (e.g., 14400, 3600, 300) or the string 'half'.
    """
    total = max(0, deadline - now)
    times = []
    for cp in checkpoints:
        if cp == "half":
            if total >= 2:  # any duration > 2s
                times.append(now + total // 2)
        else:
            fire_at = deadline - int(cp)
            if fire_at > now:
                times.append(fire_at)
    times.sort()
    return times

# ------------------------
# Timer workers
# ------------------------

async def _day_timer_worker(bot, guild_id: int, channel_id: int, checkpoints: List[Union[int, str]]):
    """
    Posts reminders to the Day channel and auto-closes it at deadline.
    Uses game.day_deadline_epoch / game.day_channel_id to stay in sync.
    """
    try:
        if game.day_deadline_epoch is None:
            return
        guild = bot.get_guild(guild_id)
        if not guild:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return

        now = int(time.time())
        schedule = _build_schedule(now, game.day_deadline_epoch, checkpoints)

        # announce deadline
        await channel.send(f"🕒 Day ends at <t:{game.day_deadline_epoch}:F> (<t:{game.day_deadline_epoch}:R>).")

        for fire_at in schedule:
            delay = fire_at - int(time.time())
            if delay > 0:
                await asyncio.sleep(delay)
            # abort if day changed/cancelled
            if game.day_deadline_epoch is None or channel_id != game.day_channel_id:
                return
            await channel.send(f"{mention_prefix()}⏳ Time update.")

        # sleep to deadline if needed
        final_delay = max(0, game.day_deadline_epoch - int(time.time()))
        if final_delay > 0:
            await asyncio.sleep(final_delay)

        # close channel if still active
        if channel_id == game.day_channel_id and game.day_deadline_epoch is not None:
            overw = channel.overwrites_for(guild.default_role)
            overw.send_messages = False
            await channel.set_permissions(guild.default_role, overwrite=overw)
            await channel.send(f"{mention_prefix()}⏰ Time is up. **Day is over; channel closed.**")

        game.day_deadline_epoch = None

    finally:
        game.day_timer_task = None

async def _night_timer_worker(bot, guild_id: int, checkpoints: List[Union[int, str]]):
    """
    Posts Night reminders (in night channel if set, else in next day channel)
    and opens the Day channel at dawn.
    Uses game.night_deadline_epoch / game.next_day_channel_id.
    """
    try:
        if game.night_deadline_epoch is None or game.next_day_channel_id is None:
            return
        guild = bot.get_guild(guild_id)
        if not guild:
            return

        remind_channel = guild.get_channel(game.night_channel_id) or guild.get_channel(game.next_day_channel_id)
        if not remind_channel:
            return

        now = int(time.time())
        schedule = _build_schedule(now, game.night_deadline_epoch, checkpoints)

        await remind_channel.send(f"🌙 Night ends at <t:{game.night_deadline_epoch}:F> (<t:{game.night_deadline_epoch}:R>).")

        for fire_at in schedule:
            delay = fire_at - int(time.time())
            if delay > 0:
                await asyncio.sleep(delay)
            if game.night_deadline_epoch is None:
                return
            await remind_channel.send(f"{mention_prefix()}🌘 Time update.")

        final_delay = max(0, game.night_deadline_epoch - int(time.time()))
        if final_delay > 0:
            await asyncio.sleep(final_delay)

        # Open Day/general channel
        day_chan = guild.get_channel(game.next_day_channel_id)
        if day_chan:
            overw = day_chan.overwrites_for(guild.default_role)
            overw.send_messages = True
            await day_chan.set_permissions(guild.default_role, overwrite=overw)
            await day_chan.send(f"{mention_prefix()}🌞 **Dawn breaks. Day is open.**")

        game.night_deadline_epoch = None

    finally:
        game.night_timer_task = None

# ------------------------
# Public API used by cogs
# ------------------------

async def start_day_timer(bot, guild_id: int, channel_id: int, *, checkpoints: List[Union[int, str]] = None):
    """
    (Re)start Day timer; reads game.day_deadline_epoch. Provide guild+channel of the Day.
    """
    if game.day_timer_task and not game.day_timer_task.done():
        game.day_timer_task.cancel()
    cps = checkpoints if checkpoints is not None else REMINDER_CHECKPOINTS
    game.day_timer_task = asyncio.create_task(_day_timer_worker(bot, guild_id, channel_id, cps))

async def start_night_timer(bot, guild_id: int, *, checkpoints: List[Union[int, str]] = None):
    """
    (Re)start Night timer; reads game.night_deadline_epoch and game.next_day_channel_id.
    """
    if game.night_timer_task and not game.night_timer_task.done():
        game.night_timer_task.cancel()
    cps = checkpoints if checkpoints is not None else REMINDER_CHECKPOINTS
    game.night_timer_task = asyncio.create_task(_night_timer_worker(bot, guild_id, cps))

async def resume_day_timer(bot, *, checkpoints: List[Union[int, str]] = None):
    """
    Recreate the Day timer after reboot if deadline is in the future.
    """
    if not game.day_channel_id or not game.day_deadline_epoch:
        return
    if game.day_deadline_epoch <= int(time.time()):
        return
    cps = checkpoints if checkpoints is not None else REMINDER_CHECKPOINTS
    for g in bot.guilds:
        if g.get_channel(game.day_channel_id):
            await start_day_timer(bot, g.id, game.day_channel_id, checkpoints=cps)
            break

async def resume_night_timer(bot, *, checkpoints: List[Union[int, str]] = None):
    """
    Recreate the Night timer after reboot if deadline is in the future.
    """
    if not game.night_deadline_epoch or game.night_deadline_epoch <= int(time.time()):
        return
    cps = checkpoints if checkpoints is not None else REMINDER_CHECKPOINTS
    for g in bot.guilds:
        await start_night_timer(bot, g.id, checkpoints=cps)
        break
