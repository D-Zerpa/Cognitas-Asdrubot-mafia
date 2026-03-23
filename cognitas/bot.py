import os
import sys
import logging
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Strict, standard logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("cognitas")

# The new, condensed architecture for Cogs.
# Commented out temporarily until we actually create these files.
INITIAL_EXTENSIONS = [
    # "cogs.host",
    # "cogs.gameplay",
    # "cogs.misc"
]

class CognitasBot(commands.Bot):
    def __init__(self):
        # We explicitly declare the intents required for a Mafia game
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True          # Crucial for role assignments and DM handling
        intents.message_content = True  # Crucial for reading text commands
        
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
            help_command=None  # We will implement a custom slash-command help later
        )

    async def setup_hook(self) -> None:
        """
        Executed before the bot connects to the Discord gateway.
        This is the safest place to load extensions and initialize database/state connections.
        """
        logger.info("Initializing setup hook. Loading core modules...")
        
        # Strict loading: If a module is corrupted, we crash immediately. No silent failures.
        for extension in INITIAL_EXTENSIONS:
            await self.load_extension(extension)
            logger.info(f"Successfully loaded extension: {extension}")
            
        logger.info("Setup hook completed successfully.")

    async def on_ready(self) -> None:
        """
        Triggered when the bot establishes a connection with Discord.
        """
        logger.info(f"Connection established. Logged in as {self.user} (ID: {self.user.id})")


async def main() -> None:
    # Load environment variables (e.g., DISCORD_TOKEN)
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    
    if not token:
        logger.critical("DISCORD_TOKEN environment variable is missing. Halting.")
        sys.exit(1)

    bot = CognitasBot()
    
    # Use an async context manager to ensure safe cleanup of internal HTTP sessions
    async with bot:
        await bot.start(token)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown signal received from user. Terminating process.")