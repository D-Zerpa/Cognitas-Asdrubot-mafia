# bot.py
import os, asyncio, signal, sys
from dotenv import load_dotenv
import discord
from discord.ext import commands

from cognitas.config import INTENTS_KWARGS
from cognitas.core.state import game
from cognitas.core.roles import load_roles
from cognitas.core.storage import load_state, save_state
from cognitas.core.timer import resume_day_timer, resume_night_timer

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in .env")

intents = discord.Intents.default()
for k, v in INTENTS_KWARGS.items():
    setattr(intents, k, v)
    
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- graceful shutdown helpers ----------
_shutdown_once = asyncio.Lock()

async def graceful_shutdown(reason: str = "signal"):
    """Cancel timers, save state, and close the bot (idempotent)."""
    async with _shutdown_once:
        # cancel running timers (day/night)
        try:
            if game.day_timer_task and not game.day_timer_task.done():
                game.day_timer_task.cancel()
                game.day_timer_task = None
            if game.night_timer_task and not game.night_timer_task.done():
                game.night_timer_task.cancel()
                game.night_timer_task = None
        except Exception:
            pass
        # clear no-longer-valid deadlines (optional)
        # (you may keep them if you want resume-after-reboot behavior;
        # here we keep them so resume still works)
        # save state atomically
        try:
            save_state("state.json")
        except Exception as e:
            print("save_state failed during shutdown:", e, file=sys.stderr)
        # close discord connection
        try:
            await bot.close()
        except Exception:
            pass

def install_signal_handlers(loop: asyncio.AbstractEventLoop):
    """Install Ctrl-C / SIGTERM hooks. Windows has limited signal support."""
    def _make_handler(name):
        def _handler():
            print(f"\nReceived {name}; shutting down gracefully…")
            loop.create_task(graceful_shutdown(reason=name))
        return _handler

    # POSIX (Linux/macOS): SIGINT & SIGTERM via add_signal_handler
    if hasattr(signal, "SIGINT"):
        try:
            loop.add_signal_handler(signal.SIGINT, _make_handler("SIGINT"))
        except NotImplementedError:
            pass
    if hasattr(signal, "SIGTERM"):
        try:
            loop.add_signal_handler(signal.SIGTERM, _make_handler("SIGTERM"))
        except NotImplementedError:
            pass

    # Windows fallback: hook KeyboardInterrupt through a background task
    # (add_signal_handler may be unavailable on ProactorEventLoop)
    async def _win_keyboard_watcher():
        # just keep the task alive; KeyboardInterrupt will bubble to main()
        while True:
            await asyncio.sleep(3600)
    if sys.platform.startswith("win"):
        loop.create_task(_win_keyboard_watcher())

# ---------- cogs & startup ----------
async def setup_cogs():
    await bot.add_cog(__import__("cognitas.cogs.admin", fromlist=["AdminCog"]).AdminCog(bot))
    await bot.add_cog(__import__("cognitas.cogs.voting", fromlist=["VotingCog"]).VotingCog(bot))
    await bot.add_cog(__import__("cognitas.cogs.actions", fromlist=["ActionsCog"]).ActionsCog(bot))
    await bot.add_cog(__import__("cognitas.cogs.players", fromlist=["Players"]).Players(bot))
    
@bot.event
async def on_ready():
    print(f"Connected as {bot.user} (id: {bot.user.id})")
    print(f"Loaded roles: {len(game.roles)}")
    if not game.game_over:
        await resume_day_timer(bot)    # uses config checkpoints
        await resume_night_timer(bot)  # uses config checkpoints

@bot.command()
async def ping(ctx):
    await ctx.reply("pong 🏓")

@bot.command()
@commands.is_owner()
async def shutdown(ctx):
    await ctx.send("👋 Shutting down…")
    await graceful_shutdown(reason="command")

async def main():
    # load config/state BEFORE starting
    game.roles = load_roles("roles.json")
    load_state("state.json")

    loop = asyncio.get_running_loop()
    install_signal_handlers(loop)

    try:
        async with bot:
            await setup_cogs()
            await bot.start(TOKEN)
    except KeyboardInterrupt:
        # e.g., Ctrl-C on Windows where add_signal_handler may not fire
        await graceful_shutdown(reason="KeyboardInterrupt")

if __name__ == "__main__":
    asyncio.run(main())
