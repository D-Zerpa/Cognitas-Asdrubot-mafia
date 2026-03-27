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
        self.storage = StorageManager()
        
        self._boot_sequence()
        self.auto_save.start()

    def _boot_sequence(self):
        """Attempts to load a previous save state and re-link expansions to survive restarts."""
        state = self.storage.load_state()
        if state and state.discord_setup.get("expansion"):
            self.bot.game_state = state
            logger.info(f"💾 Guardado detectado. Recuperando partida en: {state.phase.name} {state.cycle}")
            
            expansion_name = state.discord_setup.get("expansion")
            logger.info(f"🔄 Restaurando expansión: {expansion_name.upper()}")
            
            loader = RoleLoader()
            filename = f"roles_{expansion_name}.json"
            expansion_data = loader.load_expansion_data(filename)
            
            if expansion_data["roles"]:
                self.bot.role_registry = expansion_data["roles"]
                self.bot.temp_registry = expansion_data["temp_abilities"]
                self.bot.recommended_flags = expansion_data.get("recommended_flags", {})
                logger.info(f"✅ Memoria restaurada: {len(self.bot.role_registry)} roles listos.")
                
                import copy
                for player in state.players.values():
                    if player.role:
                        match_key = next((k for k, r in self.bot.role_registry.items() if r.name == player.role.name), None)
                        if match_key:
                            saved_flags = player.role.flags
                            player.role = copy.deepcopy(self.bot.role_registry[match_key])
                            player.role.flags.update(saved_flags)
                logger.info("💉 Roles de los jugadores rehidratados con sus habilidades.")
                # ------------------------------
            else:
                logger.error("⚠️ Error crítico: No se pudo recargar el JSON de la expansión guardada.")
            
            # 2. Cargar las Mecánicas Python (Gimmick)
            import importlib
            try:
                gimmick_module = importlib.import_module(f"cognitas.expansions.{expansion_name}")
                GimmickClass = getattr(gimmick_module, "ExpansionGimmick")
                self.bot.active_gimmick = GimmickClass()
                logger.info("✅ Mecánicas Python de la expansión conectadas.")
            except (ImportError, AttributeError):
                from cognitas.expansions.base import BaseExpansion
                self.bot.active_gimmick = BaseExpansion()
                logger.warning("⚠️ No se encontró gimmick específico. Usando BaseExpansion.")
        else:
            from cognitas.core.state import GameState
            self.bot.game_state = GameState()
            logger.info("📄 No se encontró guardado previo válido. Iniciando lienzo en blanco.")

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

    @app_commands.command(name="load_game", description="GM: Carga la última partida guardada. (Sobrescribe la actual).")
    @app_commands.default_permissions(administrator=True)
    async def load_game(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        self._boot_sequence()
        state = getattr(self.bot, "game_state", None)
        
        if state and state.discord_setup.get("expansion"):
            await interaction.followup.send(f"📂 **Partida cargada manual.** Fase actual: **{state.phase.name} {state.cycle}**.")
        else:
            await interaction.followup.send("❌ No se encontró archivo de guardado válido.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SystemCog(bot))
    logger.info("SystemCog loaded.")