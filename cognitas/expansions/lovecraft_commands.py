import discord
from discord.ext import commands
from discord import app_commands
import copy
import logging

from cognitas.core.state import GameState

logger = logging.getLogger("cognitas.expansions.lovecraft_commands")

class ParanoiaSelect(discord.ui.Select):
    def __init__(self, view: 'ExpansionUI'):
        self.parent_view = view
        options = []
        # Generate options from -10 to 10, skipping 0
        for i in range(-10, 11):
            if i == 0: 
                continue
            sign = "+" if i > 0 else ""
            options.append(discord.SelectOption(label=f"{sign}{i} Paranoia", value=str(i)))
            
        super().__init__(
            placeholder="Manual Paranoia Adjustment...", 
            min_values=1, 
            max_values=1, 
            options=options, 
            row=2
        )

    async def callback(self, interaction: discord.Interaction):
        val = int(self.values[0])
        expansion_data = self.parent_view.state.expansion_data
        current = expansion_data.get("paranoia", 0) if isinstance(expansion_data, dict) else 0
        self.parent_view.state.expansion_data["paranoia"] = max(0, current + val)
        await self.parent_view.refresh_panel(interaction)


class EventSelect(discord.ui.Select):
    def __init__(self, view: 'ExpansionUI'):
        self.parent_view = view
        # Hardcoded event list mapping to the keys in ABILITY_SANITY_IMPACTS
        options = [
            discord.SelectOption(label="Ejecución errónea (Juez)", value="summary_judgment_error"),
            discord.SelectOption(label="Ejecución errónea (Gangster)", value="unconventional_methods_error"),
            discord.SelectOption(label="Incumplir Orden (Acólito)", value="voices_from_the_deep_break"),
            discord.SelectOption(label="Rotura Ética (Psicólogo)", value="jungian_integration_ethics"),
            discord.SelectOption(label="Corrupción (Sacerdote)", value="sale_of_indulgences"),
            discord.SelectOption(label="Efecto Negativo (Doctor)", value="compulsive_surgery_error"),
            discord.SelectOption(label="Transfusión (Ocultista)", value="ethereal_transfusion_error"),
            discord.SelectOption(label="Mentir en debate (Político)", value="public_tribune_lie"),
            discord.SelectOption(label="Propagar Virus", value="virus_spread"),
            discord.SelectOption(label="Anular magia (Cultista R.)", value="veil_affinity_success"),
            discord.SelectOption(label="Himno Esperanza (Virtuoso)", value="hymn_of_hope"),
            discord.SelectOption(label="Mensaje Legendario (Autor)", value="magnum_opus_success"),
            discord.SelectOption(label="Fervor Exitoso (Sacerdote)", value="collective_fervor_success"),
            discord.SelectOption(label="Cura Espiritual (Monja)", value="gods_vestal"),
            discord.SelectOption(label="Cura Espiritual (Estudiante)", value="student_heal_spirit"),
            discord.SelectOption(label="Cura Mental (Estudiante)", value="student_heal_mental"),
            discord.SelectOption(label="Cura Mental (Psicólogo)", value="jungian_integration_success"),
            discord.SelectOption(label="Cura Física (Doctor)", value="healing_hands"),
            discord.SelectOption(label="Esquiva y revela (A. Marcial)", value="rashin_dodge"),
            discord.SelectOption(label="Uso Certeza/Absolución", value="certainty_absolution_used")
        ]
        super().__init__(
            placeholder="Apply Sanity Event...", 
            min_values=1, 
            max_values=1, 
            options=options, 
            row=3
        )

    async def callback(self, interaction: discord.Interaction):
        event_key = self.values[0]
        state = self.parent_view.state
        bot = self.parent_view.bot
        
        # Retrieve the logic controller from the bot, not the state
        active_gimmick = getattr(bot, "active_gimmick", None)
        
        # Zero assumptions: verify the expansion method exists safely
        if not active_gimmick or not hasattr(active_gimmick, "get_ability_impact"):
            await interaction.response.send_message("❌ Expansion method not found.", ephemeral=True)
            return

        impact = active_gimmick.get_ability_impact(event_key)
        if not impact:
            await interaction.response.send_message(f"❌ Event '{event_key}' not found.", ephemeral=True)
            return

        # Safely manipulate the state expansion data
        expansion_data = state.expansion_data if isinstance(state.expansion_data, dict) else {}
        current = expansion_data.get("paranoia", 0)
        shift = impact.get("paranoia", 0)
        state.expansion_data["paranoia"] = max(0, current + shift)
        
        await self.parent_view.refresh_panel(interaction)
        
        sign = "+" if shift > 0 else ""
        await interaction.followup.send(
            f"✅ **Event Applied:** {impact.get('desc', 'Unknown')} ({sign}{shift} Paranoia)", 
            ephemeral=True
        )

class ExpansionUI(discord.ui.View):
    """
    UI View for managing global expansion data like Sanity, Paranoia, and Ancestral Shields.
    Runs persistently for the GM.
    """
    def __init__(self, bot: commands.Bot, state: GameState):
        super().__init__(timeout=None)
        self.bot = bot
        self.state = state

        # Initialize default values if they don't exist in the expansion_data dict
        if "sanity" not in self.state.expansion_data:
            self.state.expansion_data["sanity"] = 10
        if "paranoia" not in self.state.expansion_data:
            self.state.expansion_data["paranoia"] = 0
        if "ancestral_shields" not in self.state.expansion_data:
            self.state.expansion_data["ancestral_shields"] = 0
            
        self.add_item(ParanoiaSelect(self))
        self.add_item(EventSelect(self))

    def build_embed(self) -> discord.Embed:
        """Constructs the visual dashboard for the GM safely."""
        exp_data = self.state.expansion_data if isinstance(self.state.expansion_data, dict) else {}
        sanity = exp_data.get("sanity", 10)
        paranoia = exp_data.get("paranoia", 0)
        shields = exp_data.get("ancestral_shields", 0)
        
        embed = discord.Embed(title="🐙 Tablero del Director (Lovecraft)", color=discord.Color.dark_teal())
        embed.add_field(name="🧠 Cordura Global", value=f"**{sanity} / 10**", inline=True)
        embed.add_field(name="👁️‍🗨️ Paranoia Acumulada", value=f"**{paranoia}**", inline=True)
        embed.add_field(name="🛡️ Escudos Ancestrales", value=f"**{shields} / 3**", inline=True)
        embed.set_footer(text="Ajusta los valores manualmente según los recordatorios del sistema.")
        return embed

    async def refresh_panel(self, interaction: discord.Interaction):
        """Saves the state and updates the UI."""
        self.bot.storage.save_state(self.state)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    # --- MODIFICATION BUTTONS ---

    @discord.ui.button(label="+ Cordura", style=discord.ButtonStyle.success, row=0)
    async def btn_san_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.state.expansion_data["sanity"] = min(10, self.state.expansion_data["sanity"] + 1)
        await self.refresh_panel(interaction)

    @discord.ui.button(label="- Cordura", style=discord.ButtonStyle.danger, row=0)
    async def btn_san_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.state.expansion_data["sanity"] = max(0, self.state.expansion_data["sanity"] - 1)
        await self.refresh_panel(interaction)

    @discord.ui.button(label="+ Paranoia", style=discord.ButtonStyle.secondary, row=1)
    async def btn_par_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.state.expansion_data["paranoia"] += 1
        await self.refresh_panel(interaction)

    @discord.ui.button(label="- Paranoia", style=discord.ButtonStyle.secondary, row=1)
    async def btn_par_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.state.expansion_data["paranoia"] = max(0, self.state.expansion_data["paranoia"] - 1)
        await self.refresh_panel(interaction)

    @discord.ui.button(label="🔄 Reset Paranoia (0)", style=discord.ButtonStyle.primary, row=1)
    async def btn_par_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.state.expansion_data["paranoia"] = 0
        await self.refresh_panel(interaction)


class LovecraftExpansionCog(commands.Cog):
    """
    Commands exclusive to the Lovecraft Expansion (Sanity/Paranoia/Late Mafia).
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="expansion_panel", description="GM: Abre el tablero de Cordura y Paranoia (Lovecraft).")
    @app_commands.default_permissions(administrator=True)
    async def show_panel(self, interaction: discord.Interaction):
        state = getattr(self.bot, "game_state", None)
        if not state:
            await interaction.response.send_message("❌ Motor no inicializado.", ephemeral=True)
            return

        view = ExpansionUI(self.bot, state)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    @app_commands.command(name="convert_mafia", description="GM: Convierte a un jugador en Cultista (Mafia Tardía) y suma un escudo.")
    @app_commands.describe(role_key="El ID del rol en el JSON (ej: acolyte, sorcerer)")
    @app_commands.default_permissions(administrator=True)
    async def convert_mafia(self, interaction: discord.Interaction, target: discord.Member, role_key: str):
        state = getattr(self.bot, "game_state", None)
        if not state:
            await interaction.response.send_message("❌ Motor no inicializado.", ephemeral=True)
            return
        
        player = state.get_player(target.id)
        if not player or not player.is_alive:
            await interaction.response.send_message("❌ Jugador inválido o muerto.", ephemeral=True)
            return

        # Ensure the role exists in the loaded memory registry
        if not hasattr(self.bot, "role_registry") or role_key not in self.bot.role_registry:
            await interaction.response.send_message(f"❌ El rol `{role_key}` no existe en memoria. ¿Cargaste la expansión correcta?", ephemeral=True)
            return
            
        # Safely assign the new role via deepcopy
        player.role = copy.deepcopy(self.bot.role_registry[role_key])
        
        # Inject the ancestral shield into the global pool (Max 3)
        current_shields = state.expansion_data.get("ancestral_shields", 0)
        state.expansion_data["ancestral_shields"] = min(3, current_shields + 1)
        
        self.bot.storage.save_state(state)
        
        await interaction.response.send_message(
            f"🐙 **{target.mention}** ha escuchado la llamada del vacío. Ahora es **{player.role.name}**.\n"
            f"🛡️ *Escudos ancestrales globales aumentados a {state.expansion_data['ancestral_shields']}/3.*", 
            ephemeral=True
        )
        logger.info(f"Player {target.id} converted to {role_key}. Shields: {state.expansion_data['ancestral_shields']}")

async def setup(bot: commands.Bot) -> None:
    """Entry point dynamically called by load_extension in host.py"""
    await bot.add_cog(LovecraftExpansionCog(bot))
    logger.info("Lovecraft Expansion Commands Cog dynamically loaded.")