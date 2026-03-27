import discord
from discord.ext import commands
import logging
import os
from dotenv import load_dotenv

load_dotenv()

# Logging config
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("cognitas.main")

# Core managers
from cognitas.core.state import GameState
from cognitas.core.actions import ActionManager
from cognitas.core.voting import VotingManager

class CognitasBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        
        super().__init__(command_prefix="!", intents=intents)
        
        # ---------------------------------------------------------
        # "BRAIN" INICIALIZATION
        # ---------------------------------------------------------
        self.game_state = GameState()
        self.action_manager = ActionManager()
        self.voting_manager = VotingManager()
        
        self.role_registry = {}
        self.temp_registry = {}
        self.active_gimmick = None

    async def setup_hook(self):
        """Carga todos los módulos (Cogs) y sincroniza los comandos de barra."""
        cogs = [
            "cognitas.cogs.host",
            "cognitas.cogs.gameplay",
            "cognitas.cogs.misc",
            "cognitas.cogs.system",
            "cognitas.cogs.timer",
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded extension: {cog}")
            except Exception as e:
                logger.error(f"Failed to load extension {cog}: {e}")
                
        # Command Sync
        logger.info("Syncing slash commands...")
        await self.tree.sync()
        logger.info("Slash commands synced.")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user.name} (ID: {self.user.id})")
        logger.info("Cognitas Engine is online and ready.")

if __name__ == "__main__":
    
    os.makedirs("data", exist_ok=True)
    TOKEN = os.getenv("DISCORD_TOKEN")
    
    bot = CognitasBot()
    bot.run(TOKEN)