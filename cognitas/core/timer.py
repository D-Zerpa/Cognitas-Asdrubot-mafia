import asyncio, time
from .state import game
from ..config import MENTION_EVERYONE, MENTION_ROLE_ID

def mention_prefix():
    if MENTION_ROLE_ID:
        return f"<@&{MENTION_ROLE_ID}> "
    return "@everyone " if MENTION_EVERYONE else ""

def parse_duration_to_seconds(text: str) -> int:
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

async def day_timer_worker(bot, guild_id: int, channel_id: int):
    try:
        if game.day_deadline_epoch is None:
            return
        guild = bot.get_guild(guild_id)
        if not guild: return
        channel = guild.get_channel(channel_id)
        if not channel: return

        now = int(time.time())
        remaining = max(0, game.day_deadline_epoch - now)

        schedule = []
        def schedule_if_left(seconds_left: int, label: str):
            fire_at = game.day_deadline_epoch - seconds_left
            if fire_at > now:
                schedule.append((fire_at, label))

        if remaining >= 2 * 3600:
            schedule.append((now + remaining // 2, "⏳ Halfway through the Day."))
        schedule_if_left(4*3600, "🌗 4 hours left.")
        schedule_if_left(3600,   "🕐 1 hour left.")
        schedule_if_left(15*60,  "⌛ 15 minutes left.")
        schedule_if_left(5*60,   "⌛ 5 minutes left.")
        schedule_if_left(60,     "⌛ 1 minute left.")
        schedule.sort(key=lambda x: x[0])

        await channel.send(f"🕒 Day ends at <t:{game.day_deadline_epoch}:F> (<t:{game.day_deadline_epoch}:R>).")

        for fire_at, label in schedule:
            delay = fire_at - int(time.time())
            if delay > 0:
                await asyncio.sleep(delay)
            if game.day_deadline_epoch is None or channel_id != game.day_channel_id:
                return
            await channel.send(f"{mention_prefix()}{label}")

        final_delay = max(0, game.day_deadline_epoch - int(time.time()))
        if final_delay > 0:
            await asyncio.sleep(final_delay)

        if channel_id == game.day_channel_id and game.day_deadline_epoch is not None:
            overw = channel.overwrites_for(guild.default_role)
            overw.send_messages = False
            await channel.set_permissions(guild.default_role, overwrite=overw)
            await channel.send(f"{mention_prefix()}⏰ Time is up. **Day is over; channel closed.**")

        game.day_deadline_epoch = None

    finally:
        game.day_timer_task = None

async def resume_day_timer(bot):
    """Recreate the day timer task on reboot if deadline is in the future."""
    if not game.day_channel_id or not game.day_deadline_epoch:
        return
    if game.day_deadline_epoch <= int(time.time()):
        return
    # find the guild that has this channel id
    for g in bot.guilds:
        if g.get_channel(game.day_channel_id):
            if game.day_timer_task and not game.day_timer_task.done():
                game.day_timer_task.cancel()
            game.day_timer_task = asyncio.create_task(day_timer_worker(bot, g.id, game.day_channel_id))
            break
