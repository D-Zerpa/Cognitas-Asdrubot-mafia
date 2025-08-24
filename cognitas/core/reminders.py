# cognitas/core/reminders.py
import re, time, asyncio, math
import discord
from .state import game

DURATION_RX = re.compile(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?", re.I)

def parse_duration_to_seconds(s: str) -> int:
    if not s:
        return 0
    s = s.strip().lower().replace(" ", "")
    # soporta "90m" o "1h30m"
    if s.endswith("m") and s[:-1].isdigit():
        return int(s[:-1]) * 60
    if s.endswith("h") and s[:-1].isdigit():
        return int(s[:-1]) * 3600
    m = DURATION_RX.fullmatch(s.replace("min","m").replace("hr","h"))
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mnt = int(m.group(2) or 0)
    return h*3600 + mnt*60

async def _send_checkpoint(bot, guild_id: int, channel_id: int, phase: str, deadline_epoch: int, minutes_left: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    chan = guild.get_channel(channel_id)
    if not chan:
        return
    # Mensaje con timestamp relativo y absoluto
    when_rel = f"<t:{deadline_epoch}:R>"
    when_abs = f"<t:{deadline_epoch}:F>"
    await chan.send(f"⏰ **Faltan {minutes_left} minutos** para terminar la **{phase}** ({when_rel} | {when_abs}).")

async def _timer_worker(bot, guild_id: int, channel_id: int, checkpoints_minutes: list[int], deadline_epoch: int, phase: str):
    # se despierta en cada minuto y emite when match
    emitted = set()
    try:
        while True:
            now = int(time.time())
            remaining = max(0, deadline_epoch - now)
            minutes_left = math.ceil(remaining/60) if remaining > 0 else 0
            for m in checkpoints_minutes:
                if minutes_left == m and m not in emitted:
                    emitted.add(m)
                    await _send_checkpoint(bot, guild_id, channel_id, phase, deadline_epoch, m)
            if remaining <= 0:
                break
            await asyncio.sleep(15)  # granularidad
    except asyncio.CancelledError:
        pass

async def start_day_timer(bot, guild_id: int, channel_id: int, checkpoints: list[int]):
    # cancela el anterior si existe
    if getattr(game, "day_timer_task", None) and not game.day_timer_task.done():
        game.day_timer_task.cancel()
    if not game.day_deadline_epoch:
        return
    game.day_timer_task = bot.loop.create_task(
        _timer_worker(bot, guild_id, channel_id, checkpoints, game.day_deadline_epoch, phase="Día")
    )

async def start_night_timer(bot, guild_id: int, checkpoints: list[int]):
    if getattr(game, "night_timer_task", None) and not game.night_timer_task.done():
        game.night_timer_task.cancel()
    if not game.night_deadline_epoch or not getattr(game, "night_channel_id", None):
        return
    game.night_timer_task = bot.loop.create_task(
        _timer_worker(bot, guild_id, game.night_channel_id, checkpoints, game.night_deadline_epoch, phase="Noche")
    )