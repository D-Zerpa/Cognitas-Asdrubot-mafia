import time
import logging
import random
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List

from cognitas.core.state import GameState
from cognitas.core.time import Phase
from cognitas.core.actions import Ability, ActionTag, TargetType
from cognitas.utils.discord_sync import process_player_death

logger = logging.getLogger("cognitas.cogs.gameplay")

# ---------------------------------------------------------
# AUXILIARY FUNCTIONS
# ---------------------------------------------------------
def _glitch_name(length: int = 6) -> str:
    """Visual 'glitched' name for anonymous votes (no identity leak)."""
    base_chars = "█▓▒░▞▚▛▜▟#@$%&"
    zalgo_marks = ["̴","̵","̶","̷","̸","̹","̺","̻","̼","̽","͜","͝","͞","͟","͠","͢"]
    out = []
    for _ in range(length):
        c = random.choice(base_chars)
        if random.random() < 0.5:
            c += "".join(random.choice(zalgo_marks) for _ in range(random.randint(1, 3)))
        out.append(c)
    return "".join(out)

# ---------------------------------------------------------
# UI COMPONENTS (DROPDOWNS & BUTTONS)
# ---------------------------------------------------------

class VoteTargetDropdown(discord.ui.Select):
    def __init__(self, state: GameState, guild: discord.Guild):
        options = []
        for player in state.players.values():
            if player.is_alive:
                member = guild.get_member(player.user_id)
                name = member.display_name if member else f"ID: {player.user_id}"
                options.append(discord.SelectOption(label=name, value=str(player.user_id), emoji="🎯"))
        
        # Special option for NO LYNCH
        options.append(discord.SelectOption(label="NO LINCHAR", value="NO_LYNCH", emoji="🛑"))
        
        super().__init__(placeholder="🎯 Elige objetivo para linchar...", min_values=1, max_values=1, options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_target_id = self.values[0]
        # Silently defer to update the internal state without throwing an error to the user
        await interaction.response.defer()


class VotingUI(discord.ui.View):
    def __init__(self, state: GameState, bot: commands.Bot, guild: discord.Guild, user_id: int):
        super().__init__(timeout=None)
        self.state = state
        self.bot = bot
        self.guild = guild
        self.user_id = user_id
        self.selected_target_id: Optional[str] = None
        
        self.add_item(VoteTargetDropdown(state, guild))

    def generate_embed(self) -> discord.Embed:
        """Generates the dynamic visual summary for the user's dashboard."""
        voter = self.state.get_player(self.user_id)
        alive_count = len(self.state.get_alive_players())
        base_threshold = (alive_count // 2) + 1
        
        # Calculate Personal Vote Weight
        vote_weight = float(voter.role.flags.get("vote_weight", 1.0))
        for condition in voter.statuses:
            vote_weight *= condition.get_vote_multiplier()
            
        # Calculate Personal Defense (Lynch Weight)
        lynch_weight = float(voter.role.flags.get("lynch_weight", 0.0))
        my_lynch_threshold = base_threshold + lynch_weight

        # Check current vote
        current_vote = self.state.votes.get(self.user_id)
        if current_vote == "NO_LYNCH":
            current_vote_str = "🛑 NO LINCHAR"
        elif current_vote:
            target_member = self.guild.get_member(int(current_vote))
            current_vote_str = target_member.display_name if target_member else str(current_vote)
        else:
            current_vote_str = "Ninguno"

        embed = discord.Embed(title="🗳️ Panel de Votación", color=discord.Color.dark_red())
        embed.add_field(name="Tu Voto Actual", value=f"**{current_vote_str}**", inline=False)
        embed.add_field(name="Poder de Voto", value=f"**{vote_weight}**", inline=True)
        embed.add_field(name="Votos para lincharte", value=f"**{my_lynch_threshold}**", inline=True)
        embed.add_field(name="Mayoría Base", value=f"**{base_threshold}**", inline=True)
        
        return embed

    @discord.ui.button(label="Votar", style=discord.ButtonStyle.danger, custom_id="btn_cast_vote")
    async def btn_cast(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_target_id:
            await interaction.response.send_message("⚠️ Por favor, selecciona un objetivo en el menú desplegable primero.", ephemeral=True)
            return
            
        voter = self.state.get_player(self.user_id)
        if not voter.is_alive:
            await interaction.response.send_message("💀 Los muertos no pueden votar.", ephemeral=True)
            return

        vote_weight = float(voter.role.flags.get("vote_weight", 1.0))
        for condition in voter.statuses:
            vote_weight *= condition.get_vote_multiplier()

        if vote_weight <= 0:
            await interaction.response.send_message("❌ Tu derecho a voto ha sido revocado.", ephemeral=True)
            return

        # Target validation
        target_val = self.selected_target_id
        if target_val != "NO_LYNCH":
            target_val = int(target_val)
            t_player = self.state.get_player(target_val)
            if not t_player or not t_player.is_alive:
                await interaction.response.send_message("❌ Objetivo inválido o muerto.", ephemeral=True)
                return

        # Cast the vote in the engine
        self.bot.voting_manager.cast_vote(self.state, self.user_id, target_val, weight=vote_weight)
        
        # Evaluate Phase State Machine
        from cognitas.core.time import TimeManager
        time_manager = TimeManager(self.state)
        current_phase = time_manager.get_current_phase_machine()
        
        eval_result = current_phase.evaluate_lynch(self.bot.voting_manager)
        
        # UI Feedback: Update the personal dashboard
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)
        
        # UI Feedback: Public notification
        target_name = "NO LINCHAR" if target_val == "NO_LYNCH" else interaction.guild.get_member(target_val).display_name
        await interaction.channel.send(f"🗳️ **{interaction.user.display_name}** ha votado por **{target_name}**.")

        # Process majority execution
        if eval_result.get("resolved"):
            majority_target = eval_result.get("target")
            if majority_target == "NO_LYNCH":
                await interaction.channel.send("⚖️ **¡MAYORÍA ALCANZADA!** El pueblo ha decidido no linchar a nadie hoy.\n🔒 *Canal bloqueado.*")
            else:
                condemned = self.state.get_player(majority_target)
                from cognitas.utils.discord_sync import process_player_death
                await process_player_death(self.bot, interaction.guild, condemned, reason="Linchado por mayoría absoluta.")
                await interaction.channel.send(f"⚖️ **¡MAYORÍA ALCANZADA!** <@{majority_target}> ha sido linchado.\n🔒 *Canal bloqueado.*")
            
            self.bot.voting_manager.clear_all_votes(self.state)
            await current_phase.lock_channel(interaction.guild)
        
        self.bot.storage.save_state(self.state)

    @discord.ui.button(label="Retirar Voto", style=discord.ButtonStyle.secondary, custom_id="btn_clear_vote")
    async def btn_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.bot.voting_manager.unvote(self.state, self.user_id)
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)
        self.bot.storage.save_state(self.state)
        await interaction.channel.send(f"💨 **{interaction.user.display_name}** ha retirado su voto.")

    @discord.ui.button(label="Terminar Día", style=discord.ButtonStyle.primary, custom_id="btn_end_day")
    async def btn_end_day(self, interaction: discord.Interaction, button: discord.ui.Button):
        alive_count = len(self.state.get_alive_players())
        self.bot.voting_manager.cast_end_day(self.state, self.user_id)
        
        current_votes = len(self.state.end_day_votes)
        threshold = (alive_count * 2 + 2) // 3
        
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)
        await interaction.channel.send(f"⏩ **{interaction.user.display_name}** ha votado para terminar el Día anticipadamente. *({threshold - current_votes} votos faltantes)*")

        from cognitas.core.time import TimeManager
        time_manager = TimeManager(self.state)
        current_phase = time_manager.get_current_phase_machine()
        
        if current_phase.evaluate_end_day(self.bot.voting_manager).get("resolved"):
            await interaction.channel.send("🌙 **¡MAYORÍA DE 2/3 ALCANZADA!**\nEl pueblo ha decidido dormir temprano.\n🔒 *Canal bloqueado.*")
            await current_phase.lock_channel(interaction.guild)

        self.bot.storage.save_state(self.state)

    @discord.ui.button(label="Ver Resumen", style=discord.ButtonStyle.success, custom_id="btn_summary")
    async def btn_summary(self, interaction: discord.Interaction, button: discord.ui.Button):
        tally = self.bot.voting_manager.get_tally(self.state)
        alive_count = len(self.state.get_alive_players())
        threshold = (alive_count // 2) + 1
        
        embed = discord.Embed(title="📊 Resumen de Votación en Vivo", description=f"Requeridos para mayoría absoluta: **{threshold}**", color=discord.Color.dark_red())
        
        if not tally:
            embed.add_field(name="Estado Actual", value="Aún no hay votos emitidos.", inline=False)
        else:
            voters_by_target = {}
            for v_id, t_id in self.state.votes.items():
                v = self.state.get_player(v_id)
                v_name = f"👁️‍🗨️ **Anónimo**" if (v and v.role and v.role.flags.get("hidden_vote")) else f"<@{v_id}>"
                voters_by_target.setdefault(t_id, []).append(v_name)
                
            for t_id, weight in tally.items():
                t_threshold = threshold
                if t_id == "NO_LYNCH":
                    t_name = "🛑 NO LINCHAR"
                else:
                    t_member = self.guild.get_member(int(t_id))
                    t_name = t_member.display_name if t_member else str(t_id)
                    t_player = self.state.get_player(t_id)
                    if t_player and t_player.role:
                        t_threshold += float(t_player.role.flags.get("lynch_weight", 0))
                        
                progress = "🟥" * int(weight) + "⬜" * max(0, int(t_threshold - weight))
                if weight >= t_threshold: progress = "💀 MAYORÍA"
                
                voter_mentions = ", ".join(voters_by_target.get(t_id, []))
                embed.add_field(name=f"{t_name} ({weight:.1f} votos)", value=f"{progress}\n↳ **Votantes:** {voter_mentions}", inline=False)

        end_day_count = len(self.state.end_day_votes)
        if end_day_count > 0:
            end_day_threshold = (alive_count * 2 + 2) // 3
            embed.add_field(name=f"⏩ Terminar Día ({end_day_count}/{end_day_threshold})", value="Revisa el chat público para ver los votantes.", inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

class TargetDropdown(discord.ui.Select):
    def __init__(self, state: GameState, guild: discord.Guild):
        self.state = state
        options = []
        
        # Populate the dropdown with players (Discord limit: 25 options)
        for player in state.players.values():
            member = guild.get_member(player.user_id)
            name = member.display_name if member else f"ID: {player.user_id}"
            
            # Visual status indicator for the UI
            emoji = "🟢" if player.is_alive else "💀"
            desc = "Vivo" if player.is_alive else "Muerto"
            
            options.append(discord.SelectOption(
                label=name, 
                value=str(player.user_id), 
                description=desc, 
                emoji=emoji
            ))

        super().__init__(placeholder="👤 Selecciona un objetivo...", min_values=1, max_values=1, options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        # Save the selected value in the parent view so the buttons can access it later
        self.view.selected_target_id = int(self.values[0])
        # Defer the interaction silently to prevent Discord from showing an "interaction failed" error
        await interaction.response.defer()

class ActionNoteModal(discord.ui.Modal, title="Detalles de la Acción"):
    note_input = discord.ui.TextInput(
        label="Especificaciones (Postura, Elementos, etc.)",
        style=discord.TextStyle.paragraph,
        placeholder="Escribe aquí los detalles requeridos para tu habilidad...",
        required=True,
        max_length=500
    )

    def __init__(self, button_instance: 'ActionButton', source_player, final_target_id, burn_prefix: str):
        super().__init__()
        self.button_instance = button_instance
        self.source_player = source_player
        self.final_target_id = final_target_id
        self.burn_prefix = burn_prefix

    async def on_submit(self, interaction: discord.Interaction):
        # Combine the Burn result (if any) with the player's written note
        final_note = f"{self.burn_prefix}{self.note_input.value}"
        
        # Re-use the action submission logic
        result = self.button_instance.bot.action_manager.submit_action(
            source_player=self.source_player, 
            target_id=self.final_target_id, 
            ability=self.button_instance.ability, 
            state=self.button_instance.state,
            gimmick=getattr(self.button_instance.bot, "active_gimmick", None),
            note=final_note
        )
        
        # Process secret notifications
        secret_notes = result.get("secret_notifications", {})
        if secret_notes:
            for uid, msg_text in secret_notes.items():
                notified_player = self.button_instance.state.get_player(uid)
                if notified_player and notified_player.private_channel_id:
                    priv_channel = interaction.guild.get_channel(notified_player.private_channel_id)
                    if priv_channel:
                        await priv_channel.send(msg_text)

        # Visual feedback based on engine response
        if result["status"] == "blocked":
            await interaction.response.send_message(f"🛑 {result['ui_text']}", ephemeral=True)
        elif result["status"] == "redirected":
            msg = f"🌀 {result.get('ui_try', 'Intentas actuar...')}\nRedirigido hacia <@{result['new_target']}>."
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            embed = self.button_instance.view.message.embeds[0]
            embed.color = discord.Color.green()
            embed.set_footer(text=f"Última acción registrada con nota: {self.button_instance.ability.name}")
            await interaction.response.edit_message(embed=embed, view=self.button_instance.view)
            await interaction.followup.send(f"✅ Has preparado **{self.button_instance.ability.name}** con la información proporcionada.", ephemeral=False)


class ActionButton(discord.ui.Button):
    def __init__(self, ability: Ability, bot: commands.Bot, state: GameState):
        super().__init__(label=ability.name, style=discord.ButtonStyle.primary, custom_id=f"act_{ability.identifier}")
        self.ability = ability
        self.bot = bot
        self.state = state

    async def callback(self, interaction: discord.Interaction):
        # 1. Retrieve the source player who clicked the button
        source_player = self.state.get_player(interaction.user.id)
        
        # 2. Target Logic
        final_target_id = None
        
        if self.ability.target_type == TargetType.SINGLE:
            if not self.view.selected_target_id:
                await interaction.response.send_message("⚠️ **Debes seleccionar un objetivo en el menú desplegable primero.**", ephemeral=True)
                return
            final_target_id = self.view.selected_target_id
        elif self.ability.target_type == TargetType.SELF:
            final_target_id = source_player.user_id

        # 3. GENERIC PREFIX CONDITION LOGIC (Calculated before submission)
        action_prefix = ""
        roll = random.randint(1, 100)
        for condition in source_player.statuses:
            prefix = condition.get_action_prefix(roll)
            if prefix:
                action_prefix += prefix

        # 4. CHECK IF MODAL IS REQUIRED (Data-driven logic)
        if self.ability.requires_note:
            modal = ActionNoteModal(self, source_player, final_target_id, action_prefix)
            await interaction.response.send_modal(modal)
            return

        # 5. Submit to ActionManager (Standard flow if no modal is required)
        gimmick = getattr(self.bot, "active_gimmick", None)
        result = self.bot.action_manager.submit_action(
            source_player=source_player, 
            target_id=final_target_id, 
            ability=self.ability, 
            state=self.state,
            gimmick=gimmick,
            note=action_prefix if action_prefix else None
        )

        # 6. Process secret expansion notifications
        secret_notes = result.get("secret_notifications", {})
        if secret_notes:
            for uid, msg_text in secret_notes.items():
                notified_player = self.state.get_player(uid)
                if notified_player and notified_player.private_channel_id:
                    priv_channel = interaction.guild.get_channel(notified_player.private_channel_id)
                    if priv_channel:
                        await priv_channel.send(msg_text)

        # 7. Visual feedback to the user based on Engine response
        if result["status"] == "blocked":
            await interaction.response.send_message(f"🛑 {result['ui_text']}", ephemeral=True)
        elif result["status"] == "redirected":
            msg = f"🌀 {result.get('ui_try', 'Intentas actuar...')}\nRedirigido hacia <@{result['new_target']}>."
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            target_str = ""
            if final_target_id:
                target_member = interaction.guild.get_member(final_target_id)
                target_name = target_member.display_name if target_member else "Desconocido"
                target_str = f" sobre **{target_name}**"
            
            embed = self.view.message.embeds[0]
            embed.color = discord.Color.green()
            embed.set_footer(text=f"Última acción registrada: {self.ability.name}{target_str}")
            
            await interaction.response.edit_message(embed=embed, view=self.view)
            await interaction.followup.send(f"✅ Has preparado **{self.ability.name}**{target_str}.", ephemeral=False)

class ActionUI(discord.ui.View):
    def __init__(self, state: GameState, guild: discord.Guild, valid_abilities: List[Ability], bot: commands.Bot):
        super().__init__(timeout=None)
        self.selected_target_id: Optional[int] = None
        self.message: Optional[discord.Message] = None

        # Add the target selection dropdown
        self.add_item(TargetDropdown(state, guild))

        # Dynamically append a button for each valid ability the user has
        for ab in valid_abilities:
            self.add_item(ActionButton(ab, bot, state))


# ---------------------------------------------------------
# GAMEPLAY COMMANDS
# ---------------------------------------------------------

class GameplayCog(commands.Cog):
    """
    Handles player-facing commands (Voting, Actions, Status).
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _validate_voter(self, interaction: discord.Interaction) -> bool:
        """Helper to ensure the user can actually vote right now."""
        if not hasattr(self.bot, "game_state"):
            await interaction.response.send_message("❌ La partida no ha comenzado.", ephemeral=True)
            return False
            
        state: GameState = self.bot.game_state
        
        game_channel_id = state.discord_setup.get("game_channel_id")
        if game_channel_id and interaction.channel_id != game_channel_id:
            await interaction.response.send_message("❌ Solo puedes votar en el canal público de juego.", ephemeral=True)
            return False

        if state.phase != Phase.DAY:
            await interaction.response.send_message("🌙 Solo puedes votar durante el Día.", ephemeral=True)
            return False

    @app_commands.command(name="vote", description="Abre tu panel personal de votación.")
    async def open_vote_panel(self, interaction: discord.Interaction):
        if not await self._validate_voter(interaction):
            return
            
        voter = self.bot.game_state.get_player(interaction.user.id)
        if not voter.is_alive:
            await interaction.response.send_message("💀 Los muertos no pueden votar.", ephemeral=True)
            return

        # Instantiate UI and fetch the initial render of the Embed
        view = VotingUI(self.bot.game_state, self.bot, interaction.guild, interaction.user.id)
        embed = view.generate_embed()
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="status", description="Muestra el estado global y resumen de la partida.")
    async def game_status(self, interaction: discord.Interaction):
        if not hasattr(self.bot, "game_state"):
            await interaction.response.send_message("❌ La partida no está activa.", ephemeral=True)
            return

        state: GameState = self.bot.game_state
        
        # 1. Translate Phase to Spanish for the UI
        phase_translations = {
            Phase.SETUP: "Preparación",
            Phase.DAY: "Día",
            Phase.NIGHT: "Noche"
        }
        current_phase_es = phase_translations.get(state.phase, "Desconocida")

        # 2. Count alive vs total players
        alive_count = len(state.get_alive_players())
        total_count = len(state.players)

        # 3. Build the core UI Embed
        embed = discord.Embed(
            title="📊 Estado de la Partida",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Fase Actual", value=f"**{current_phase_es} {state.cycle}**", inline=True)
        embed.add_field(name="Jugadores Vivos", value=f"**{alive_count}** / {total_count}", inline=True)

        # 4. TIMER INTEGRATION (NUEVO)
        end_time = state.discord_setup.get("phase_end_time")
        current_time = int(time.time())
        
        if end_time and end_time > current_time:
            # Shows a live countdown like "en 15 minutos" and the exact hour
            embed.add_field(
                name="⏳ Tiempo Restante", 
                value=f"<t:{end_time}:R> (hasta las <t:{end_time}:t>)", 
                inline=False
            )
        else:
            embed.add_field(
                name="⏳ Tiempo Restante", 
                value="*Sin límite definido o a la espera del Mod.*", 
                inline=False
            )

        # 5. Check for Expansion specific data (Gimmicks)
        if hasattr(self.bot, "active_gimmick") and self.bot.active_gimmick:
            gimmick_info = self.bot.active_gimmick.get_status_info(state)
            if gimmick_info:
                embed.add_field(name="✨ Efecto de Expansión", value=gimmick_info, inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="player_list", description="Muestra la lista de jugadores vivos y muertos.")
    async def player_list(self, interaction: discord.Interaction):
        state: GameState = getattr(self.bot, "game_state", None)
        if not state:
            await interaction.response.send_message("❌ La partida no ha comenzado.", ephemeral=True)
            return

        alive_players = state.get_alive_players()
        dead_players = [p for p in state.players.values() if not p.is_alive]

        # Format the lists using Discord mentions for easy tagging
        alive_text = "\n".join([f"🟢 <@{p.user_id}>" for p in alive_players])
        dead_text = "\n".join([f"💀 <@{p.user_id}>" for p in dead_players])

        # Fallbacks in case the lists are empty
        if not alive_text: alive_text = "*Nadie ha sobrevivido...*"
        if not dead_text: dead_text = "*Nadie ha muerto (aún).*"

        embed = discord.Embed(
            title="👥 Registro de Supervivientes",
            description="Lista oficial de jugadores:",
            color=discord.Color.blue()
        )
        
        embed.add_field(name=f"Vivos ({len(alive_players)})", value=alive_text, inline=True)
        
        # Only show the graveyard if someone is actually dead
        if dead_players:
            embed.add_field(name=f"Muertos ({len(dead_players)})", value=dead_text, inline=True)

        # Send publicly so everyone in the channel can see the reference
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="act", description="Abre tu panel de control de habilidades nocturnas/diurnas.")
    async def act_ui(self, interaction: discord.Interaction):
        state: GameState = getattr(self.bot, "game_state", None)
        if not state:
            await interaction.response.send_message("❌ La partida no ha comenzado.", ephemeral=True)
            return

        player = state.get_player(interaction.user.id)
        if not player or not player.is_alive or not player.role:
            await interaction.response.send_message("💀 Los muertos no pueden actuar.", ephemeral=True)
            return

        # 1. Gather valid base abilities for the current phase
        valid_abilities: List[Ability] = [
            ab for ab in player.role.abilities 
            if (state.phase == Phase.DAY and ab.tag == ActionTag.DAY_ACT) or 
               (state.phase == Phase.NIGHT and ab.tag == ActionTag.NIGHT_ACT)
        ]
        
        # Inject dynamic/temporary abilities based on active Flags
        temp_registry = getattr(self.bot, "temp_registry", {})
        for flag_name, temp_data in temp_registry.items():
            if player.role.flags.get(flag_name):
                temp_list = temp_data if isinstance(temp_data, list) else [temp_data]
                
                for temp_ab in temp_list:
                    if (state.phase == Phase.DAY and temp_ab.tag == ActionTag.DAY_ACT) or \
                       (state.phase == Phase.NIGHT and temp_ab.tag == ActionTag.NIGHT_ACT):
                        valid_abilities.append(temp_ab)

        if not valid_abilities:
            await interaction.response.send_message("💤 No tienes habilidades disponibles en esta fase.", ephemeral=True)
            return

        # 2. Build the visual interface
        embed = discord.Embed(
            title="🎮 Panel de Acción",
            description=(
                f"Hola {interaction.user.mention}, eres **{player.role.name}**.\n\n"
                f"**1.** Selecciona un objetivo en el menú desplegable (si tu habilidad lo requiere).\n"
                f"**2.** Haz clic en el botón de la acción que deseas ejecutar."
            ),
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Puedes cambiar de opinión seleccionando otra acción. Se guardará la última.")

        view = ActionUI(state, interaction.guild, valid_abilities, self.bot)
        
        # Send the UI and store the message reference in the view so we can update it later
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GameplayCog(bot))
    logger.info("GameplayCog loaded.")