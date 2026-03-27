import time
import logging
import discord
from discord.ext import commands, tasks
from discord import app_commands

from cognitas.core.state import GameState

logger = logging.getLogger("cognitas.cogs.timer")

class TimerCog(commands.Cog):
    """
    Handles automatic phase countdowns and channel locking.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Start the background watcher loop
        self.timer_check.start()

    def cog_unload(self):
        # Stop the loop cleanly if the cog is reloaded
        self.timer_check.cancel()

    @tasks.loop(seconds=5.0)
    async def timer_check(self):
        """Background task checking if the current time exceeded the phase_end_time."""
        if not hasattr(self.bot, "game_state"):
            return

        state: GameState = self.bot.game_state
        end_time = state.discord_setup.get("phase_end_time")

        # If a timer exists and the current time has passed it
        if end_time and int(time.time()) >= end_time:
            # 1. Clear the timer so this doesn't trigger again
            state.discord_setup["phase_end_time"] = None 
            logger.info("Phase timer expired. Locking channels.")

            game_channel_id = state.discord_setup.get("game_channel_id")
            if not game_channel_id:
                return

            channel = self.bot.get_channel(game_channel_id)
            if not channel:
                return

            try:
                # 2. Lock the channel automatically
                await channel.set_permissions(channel.guild.default_role, send_messages=False)
                await channel.send(
                    "⏰ **¡EL TIEMPO SE HA AGOTADO!**\n"
                    "🔒 *El canal ha sido silenciado. A la espera del Game Master.*"
                )
                
                # 3. Ping the GM in the private logs
                log_channel_id = state.discord_setup.get("log_channel_id")
                if log_channel_id:
                    log_channel = self.bot.get_channel(log_channel_id)
                    if log_channel:
                        await log_channel.send("⚠️ **SISTEMA:** El temporizador ha expirado. El canal de juego ha sido bloqueado.")
            except discord.Forbidden:
                logger.error("Missing permissions to lock the channel on timer expire.")

    @timer_check.before_loop
    async def before_timer_check(self):
        """Wait until the bot is fully logged in before starting the clock."""
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TimerCog(bot))
    logger.info("TimerCog loaded.")