import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import List
from cognitas.core.state import GameState
from cognitas.utils.discord_sync import process_player_death

logger = logging.getLogger("cognitas.expansions.dnd_commands")


class DnDPlayerDropdown(discord.ui.Select):
    """Dropdown to select a player for HP management."""
    def __init__(self, state: GameState, guild: discord.Guild):
        options = []
        for player in state.players.values():
            member = guild.get_member(player.user_id)
            name = member.display_name if member else f"ID: {player.user_id}"
            emoji = "🟢" if player.is_alive else "💀"
            options.append(discord.SelectOption(label=name, value=str(player.user_id), emoji=emoji))
        
        super().__init__(placeholder="👤 Select a player to manage HP...", min_values=1, max_values=1, options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        self.view.target_id = int(self.values[0])
        await self.view.refresh_interface(interaction)


class DnDModifyHpModal(discord.ui.Modal):
    """A generic modal to input exact numbers for Damage, Heal, or Temp HP."""
    amount_input = discord.ui.TextInput(
        label="Amount", 
        placeholder="Enter a positive integer (e.g., 15)", 
        required=True
    )

    def __init__(self, parent_view: 'DnDHpManagerUI', action_type: str):
        # action_type can be: 'damage', 'heal', 'temp_hp'
        titles = {
            "damage": "Deal Damage",
            "heal": "Heal HP",
            "temp_hp": "Add Temporary HP"
        }
        super().__init__(title=titles.get(action_type, "Modify HP"))
        self.parent_view = parent_view
        self.action_type = action_type

    async def on_submit(self, interaction: discord.Interaction):
        # 1. UI Validation (Dumb UI only checks format)
        try:
            amount = int(self.amount_input.value.strip())
            if amount < 0:
                raise ValueError("Negative values not allowed here.")
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid positive number.", ephemeral=True)
            return

        player = self.parent_view.state.get_player(self.parent_view.target_id)
        active_gimmick = getattr(self.parent_view.bot, "active_gimmick", None)

        if not player or not active_gimmick or not hasattr(active_gimmick, "modify_player_hp"):
            await interaction.response.send_message("❌ Player data missing or DnD expansion module not loaded.", ephemeral=True)
            return

        # 2. Delegate Business Logic to the Engine
        result = active_gimmick.modify_player_hp(player, amount, self.action_type)
        
        if result.get("error"):
            await interaction.response.send_message(f"❌ {result['error']}", ephemeral=True)
            return

        # 3. Save engine state and visually refresh UI
        self.parent_view.bot.storage.save_state(self.parent_view.state)
        await self.parent_view.refresh_interface(interaction)

        # 4. Handle Discord-specific side effects (Death event)
        if result.get("died"):
            from cognitas.utils.discord_sync import process_player_death
            await process_player_death(self.parent_view.bot, interaction.guild, player, reason="HP dropped to 0.")
            await interaction.channel.send(f"💀 **<@{player.user_id}>** has succumbed to their wounds in battle.")

class DnDHpManagerUI(discord.ui.View):
    """The main Dashboard for the GM to manage player health."""
    def __init__(self, bot: commands.Bot, state: GameState, guild: discord.Guild):
        super().__init__(timeout=900) # 15 minutes timeout
        self.bot = bot
        self.state = state
        self.guild = guild
        self.target_id = None
        
        self.add_item(DnDPlayerDropdown(state, guild))

    def build_embed(self) -> discord.Embed:
        if not self.target_id:
            return discord.Embed(
                title="🛡️ DnD Health Manager", 
                description="Select a player from the dropdown to manage their HP.", 
                color=discord.Color.greyple()
            )
        
        player = self.state.get_player(self.target_id)
        member = self.guild.get_member(self.target_id)
        name = member.display_name if member else f"ID: {self.target_id}"
        
        embed = discord.Embed(title=f"❤️ Health Profile: {name}", color=discord.Color.red())
        
        if not player.role:
            embed.description = "⚠️ This player does not have a role assigned."
            return embed

        flags = player.role.flags
        current_hp = int(flags.get("hp", 0))
        max_hp = int(flags.get("max_hp", 0))
        temp_hp = int(flags.get("temp_hp", 0))
        level = int(flags.get("level", 1))

        embed.add_field(name="Status", value="🟢 ALIVE" if player.is_alive else "💀 DEAD", inline=False)
        embed.add_field(name="Level", value=f"**{level}**", inline=True)
        embed.add_field(name="Current HP", value=f"**{current_hp} / {max_hp}**", inline=True)
        embed.add_field(name="Temporary HP", value=f"**{temp_hp}**", inline=True)
        
        if temp_hp > 0:
            embed.set_footer(text="Note: Damage will deplete Temporary HP before reducing Current HP.")
            
        return embed

    async def refresh_interface(self, interaction: discord.Interaction):
        # 1. Clear old buttons, keeping only the dropdown
        for item in self.children[:]:
            if not isinstance(item, DnDPlayerDropdown):
                self.remove_item(item)
        
        # 2. Add action buttons if a valid player is selected
        if self.target_id:
            player = self.state.get_player(self.target_id)
            if player and player.role:
                btn_dmg = discord.ui.Button(label="Deal Damage", style=discord.ButtonStyle.danger, custom_id="btn_dmg", row=1)
                btn_dmg.callback = self.action_damage
                self.add_item(btn_dmg)
                
                btn_heal = discord.ui.Button(label="Heal HP", style=discord.ButtonStyle.success, custom_id="btn_heal", row=1)
                btn_heal.callback = self.action_heal
                self.add_item(btn_heal)

                btn_temp = discord.ui.Button(label="Add Temp HP", style=discord.ButtonStyle.secondary, custom_id="btn_temp", row=1)
                btn_temp.callback = self.action_temp
                self.add_item(btn_temp)

        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    # --- Button Callbacks (They spawn the unified Modal) ---
    async def action_damage(self, interaction: discord.Interaction):
        await interaction.response.send_modal(DnDModifyHpModal(self, "damage"))

    async def action_heal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(DnDModifyHpModal(self, "heal"))

    async def action_temp(self, interaction: discord.Interaction):
        await interaction.response.send_modal(DnDModifyHpModal(self, "temp_hp"))

class DnDExpansionCog(commands.Cog):
    """
    Commands exclusive to the Mafia x DnD Expansion.
    Manages manual HP adjustments and leveling.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        from cognitas.data.loaders import ItemLoader
        loader = ItemLoader()
        self.bot.item_registry = loader.load_items("items_dnd.json")
    
    dnd_group = app_commands.Group(name="dnd", description="GM: Tools for the DnD Expansion.", default_permissions=discord.Permissions(administrator=True))

    @dnd_group.command(name="hp_panel", description="GM: Opens the interactive HP Management Dashboard.")
    async def open_hp_panel(self, interaction: discord.Interaction):
        state: GameState = getattr(self.bot, "game_state", None)
        if not state:
            await interaction.response.send_message("❌ Engine not initialized.", ephemeral=True)
            return

        view = DnDHpManagerUI(self.bot, state, interaction.guild)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    @dnd_group.command(name="mass_level_up", description="GM: Increases level for all alive players and grants HP bonuses.")
    async def mass_level_up(self, interaction: discord.Interaction):
        state: GameState = getattr(self.bot, "game_state", None)
        if not state:
            await interaction.response.send_message("❌ Engine not initialized.", ephemeral=True)
            return

        # Defer response since iterating and saving might take a moment
        await interaction.response.defer(ephemeral=False)
        
        alive_players = state.get_alive_players()
        if not alive_players:
            await interaction.followup.send("💀 No alive players to level up.")
            return

        leveled_up_count = 0
        
        for player in alive_players:
            if player.role:
                # 1. Retrieve current stats
                flags = player.role.flags
                current_level = int(flags.get("level", 1))
                current_hp = int(flags.get("hp", 30))
                max_hp = int(flags.get("max_hp", 30))
                
                # 2. Level Up logic
                new_level = current_level + 1
                flags["level"] = new_level
                
                # 3. HP Bonus every 2 levels (Even numbers)
                if new_level % 2 == 0:
                    flags["max_hp"] = max_hp + 5
                    flags["hp"] = current_hp + 5
                    
                leveled_up_count += 1

        # 4. Atomic save to persist the new levels and HP
        self.bot.storage.save_state(state)
        
        # 5. Public Announcement and GM Reminder
        embed = discord.Embed(
            title="🆙 Party Level Up!", 
            description=f"**{leveled_up_count}** surviving players have reached the next level.",
            color=discord.Color.gold()
        )
        embed.set_footer(text="Reminder: Players reaching Level 3 should choose a subclass. Use /set_flag to assign it.")
        
        await interaction.followup.send(embed=embed)
        
        
async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DnDExpansionCog(bot))
    logger.info("DnD Expansion Commands Cog dynamically loaded.")