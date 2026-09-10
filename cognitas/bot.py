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

        from cognitas.core.storage import StorageManager
        self.storage = StorageManager()
        self.role_registry = {}
        self.temp_registry = {}
        self.active_gimmick = None
        self.active_expansion_cog: str | None = None

    async def setup_hook(self):
        
        """Loads all base modules (Cogs), restores state, and syncs slash commands."""
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
                logger.info(f"Loaded base extension: {cog}")
            except Exception as e:
                logger.error(f"Failed to load base extension {cog}: {e}")

        # --- MEMORY RESTORATION ---
        loaded_state = self.storage.load_state()
        if loaded_state:
            self.game_state = loaded_state
            logger.info("Previous GameState successfully restored from disk.")
            
            # Auto-reconnect the active expansion if one was loaded
            expansion_name = self.game_state.discord_setup.get("expansion")
            if expansion_name:
                logger.info(f"Reconnecting expansion: {expansion_name}...")
                import importlib
                from cognitas.data.loaders import RoleLoader
                
                # 1. Restore Roles & Flags
                loader = RoleLoader()
                expansion_data = loader.load_expansion_data(f"roles_{expansion_name}.json")
                if expansion_data and expansion_data.get("roles"):
                    self.role_registry = expansion_data["roles"]
                    self.temp_registry = expansion_data.get("temp_abilities", {})
                    self.recommended_flags = expansion_data.get("recommended_flags", {})
                
                # 2. Restore Python Gimmick (Logic)
                try:
                    gimmick_module = importlib.import_module(f"cognitas.expansions.{expansion_name}")
                    GimmickClass = getattr(gimmick_module, "ExpansionGimmick")
                    self.active_gimmick = GimmickClass()
                except (ImportError, AttributeError) as e:
                    logger.warning(f"No specific gimmick found for {expansion_name}. Using BaseExpansion. Error: {e}")
                    from cognitas.expansions.base import BaseExpansion
                    self.active_gimmick = BaseExpansion()
                    
                # 3. Restore Expansion Commands (Cog)
                expected_cog_path = f"cognitas.expansions.{expansion_name}_commands"
                
                try:
                    await self.load_extension(expected_cog_path)
                    self.active_expansion_cog = expected_cog_path
                    logger.info(f"Restored expansion cog: {expected_cog_path}")
                except commands.ExtensionNotFound:
                    # It is perfectly normal for base/vanilla expansions to lack this file
                    logger.info(f"No custom commands loaded for {expansion_name} (Not found).")
                except Exception as e:
                    # If the file exists but fails to load (SyntaxError, ImportError, etc.)
                    logger.error(f"CRITICAL: Failed to load existing commands for {expansion_name}. Error: {e}")
        else:
            logger.info("No previous state found. Starting with a blank GameState.")
                
        # Command Sync
        logger.info("Syncing slash commands...")
        guild_id = os.getenv("GUILD_ID")
        
        if guild_id:
            try:
                target_guild = discord.Object(id=int(guild_id))
                
                # 1. Copy the loaded commands to the local guild FIRST while they are in memory
                self.tree.copy_global_to(guild=target_guild)
                
                # 2. Clear the global commands from the internal tree
                self.tree.clear_commands(guild=None)
                
                # 3. Sync the populated local guild to Discord (Instantly available)
                await self.tree.sync(guild=target_guild)
                
                # 4. Sync the empty global tree to Discord to wipe any ghost duplicates
                await self.tree.sync(guild=None)
                
                logger.info(f"Slash commands synced instantly to Guild ID: {guild_id}. Globals purged.")
            except ValueError:
                logger.error("GUILD_ID in .env is not a valid integer. Defaulting to global sync.")
                await self.tree.sync()
        else:
            logger.warning("No GUILD_ID found in .env. Global sync may take up to an hour to appear in Discord.")
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