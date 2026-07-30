import logging
import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, List, Dict, Union, Any

from cognitas.core.storage import StorageManager
from cognitas.data.loaders import RoleLoader 

logger = logging.getLogger("cognitas.cogs.system")

class SystemCog(commands.Cog):
    """
    Handles background system tasks like Auto-Save and disaster recovery.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.storage = bot.storage
        self.auto_save.start()

    def cog_unload(self):
        self.auto_save.cancel()

    @tasks.loop(minutes=5.0)
    async def auto_save(self):
        """Silently saves the game state every 5 minutes."""
        if hasattr(self.bot, "game_state") and self.bot.game_state:
            self.storage.save_state(self.bot.game_state)
            logger.info("Auto-Save completado en segundo plano.")

    @auto_save.before_loop
    async def before_auto_save(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="save_game", description="GM: Guarda la partida manualmente en el disco duro.")
    @app_commands.default_permissions(administrator=True)
    async def save_game(self, interaction: discord.Interaction):
        if not hasattr(self.bot, "game_state"):
            await interaction.response.send_message("❌ No hay partida activa para guardar.", ephemeral=True)
            return
            
        success = self.storage.save_state(self.bot.game_state)
        if success:
            await interaction.response.send_message("💾 **Partida guardada exitosamente.**", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Error crítico al guardar. Revisa la consola del bot.", ephemeral=True)

    @app_commands.command(name="load_game", description="GM: Manually loads the last saved game (Overwrites current state).")
    @app_commands.default_permissions(administrator=True)
    async def load_game(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        state = self.storage.load_state()
        if not state:
            await interaction.followup.send("❌ No valid save file found on disk.")
            return
            
        self.bot.game_state = state
        expansion_name = state.discord_setup.get("expansion")
        
        if expansion_name:
            import importlib
            from cognitas.data.loaders import RoleLoader
            import copy
            
            # 1. Restore Roles & Flags
            loader = RoleLoader()
            expansion_data = loader.load_expansion_data(f"roles_{expansion_name}.json")
            if expansion_data and expansion_data.get("roles"):
                self.bot.role_registry = expansion_data["roles"]
                self.bot.temp_registry = expansion_data.get("temp_abilities", {})
                self.bot.recommended_flags = expansion_data.get("recommended_flags", {})
                
                # Rehydrate players
                for player in state.players.values():
                    if player.role:
                        match_key = next((k for k, r in self.bot.role_registry.items() if r.name == player.role.name), None)
                        if match_key:
                            saved_flags = player.role.flags
                            player.role = copy.deepcopy(self.bot.role_registry[match_key])
                            player.role.flags.update(saved_flags)
            
            # 2. Restore Python Gimmick (Logic)
            try:
                gimmick_module = importlib.import_module(f"cognitas.expansions.{expansion_name}")
                GimmickClass = getattr(gimmick_module, "ExpansionGimmick")
                self.bot.active_gimmick = GimmickClass()
            except (ImportError, AttributeError):
                from cognitas.expansions.base import BaseExpansion
                self.bot.active_gimmick = BaseExpansion()
                
            # 3. Restore Expansion Commands (Cog) & Sync Tree
            expected_cog_path = f"cognitas.expansions.{expansion_name}_commands"
            if getattr(self.bot, "active_expansion_cog", None) and self.bot.active_expansion_cog in self.bot.extensions:
                await self.bot.unload_extension(self.bot.active_expansion_cog)
                
            try:
                await self.bot.load_extension(expected_cog_path)
                self.bot.active_expansion_cog = expected_cog_path
            except Exception as e:
                logger.warning(f"No specific expansion commands loaded for {expansion_name}: {e}")
                self.bot.active_expansion_cog = None
                
            await self.bot.tree.sync()
            
        await interaction.followup.send(f"📂 **Manual load successful.** Current phase: **{state.phase.name} {state.cycle}**.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SystemCog(bot))
    logger.info("SystemCog loaded.")