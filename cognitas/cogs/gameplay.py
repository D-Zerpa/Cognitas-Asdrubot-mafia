import time
import logging
import random
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List, Dict, Union, Any

from cognitas.core.state import GameState
from cognitas.core.voting import VotingManager
from cognitas.core.time import Phase
from cognitas.core.actions import Ability, ActionTag, TargetType

from typing import List

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


class ActionButton(discord.ui.Button):
    def __init__(self, ability: Ability, bot: commands.Bot, state: GameState):
        super().__init__(label=ability.name, style=discord.ButtonStyle.primary, custom_id=f"act_{ability.identifier}")
        self.ability = ability
        self.bot = bot
        self.state = state

    async def callback(self, interaction: discord.Interaction):
        # 1. Retrieve the source player who clicked the button
        source_player = self.state.get_player(interaction.user.id)
        
        # 2. Target Logic (Psycho Mode: Smart Targeting)
        final_target_id = None
        
        if self.ability.target_type == TargetType.SINGLE:
            if not self.view.selected_target_id:
                await interaction.response.send_message("⚠️ **Debes seleccionar un objetivo en el menú desplegable primero.**", ephemeral=True)
                return
            final_target_id = self.view.selected_target_id
            
            # Quick alive/dead validation context
            # (If you want certain abilities not to affect dead players, validate here. 
            # For now, we delegate to the Game Master when reading the report, 
            # or you could add a 'targets_dead' flag to the Ability class in the future).
            target_player = self.state.get_player(final_target_id)

        elif self.ability.target_type == TargetType.SELF:
            # Overrides any dropdown selection and targets the user
            final_target_id = source_player.user_id
            
        elif self.ability.target_type in (TargetType.NONE, TargetType.ALL):
            final_target_id = None

        # 3. Submit to ActionManager
        gimmick = getattr(self.bot, "active_gimmick", None)
        result = self.bot.action_manager.submit_action(
            source_player=source_player, 
            target_id=final_target_id, 
            ability=self.ability, 
            state=self.state,
            gimmick=gimmick
        )

        # 4. Process secret expansion notifications (e.g., Fuuka's Oracle Radar)
        secret_notes = result.get("secret_notifications", {})
        if secret_notes:
            for uid, msg_text in secret_notes.items():
                notified_player = self.state.get_player(uid)
                if notified_player and notified_player.private_channel_id:
                    priv_channel = interaction.guild.get_channel(notified_player.private_channel_id)
                    if priv_channel:
                        await priv_channel.send(msg_text)

        # 5. Visual feedback to the user based on Engine response
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
            
            # Update the original message embed to confirm the action was locked in
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
# DYNAMIC AUTOCOMPLETE
# ---------------------------------------------------------
async def ability_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    # 1. Check if the game is running
    if not hasattr(interaction.client, "game_state"):
        return []
        
    state: GameState = interaction.client.game_state
    player = state.get_player(interaction.user.id)
    
    if not player or not player.is_alive or not player.role:
        return []

    valid_abilities: List[Ability] = []
    
    # 2. Add Base Abilities matching the current phase
    for ab in player.role.abilities:
        if (state.phase == Phase.DAY and ab.tag == ActionTag.DAY_ACT) or \
           (state.phase == Phase.NIGHT and ab.tag == ActionTag.NIGHT_ACT):
            valid_abilities.append(ab)

    # 3. Add Dynamic/Temporary Abilities based on Flags
    # EJEMPLO: Si el GM le puso el flag "has_gun" (Tiene un arma temporal)
    if state.phase == Phase.NIGHT and player.role.flags.get("has_gun"):
        gun_ability = Ability(
            identifier="temp_shoot", 
            name="🔫 Disparar Arma (Objeto)", 
            tag=ActionTag.NIGHT_ACT, 
            priority=80, 
            target_type=TargetType.SINGLE
        )
        valid_abilities.append(gun_ability)
        
    # EJEMPLO 2: Si por un evento global se le dio el flag "can_investigate_today"
    if state.phase == Phase.DAY and player.role.flags.get("can_investigate_today"):
        inv_ability = Ability(
            identifier="temp_investigate", 
            name="🔍 Investigar (Ventaja Temporal)", 
            tag=ActionTag.DAY_ACT, 
            priority=50, 
            target_type=TargetType.SINGLE
        )
        valid_abilities.append(inv_ability)

    # 4. Filter choices based on what the user is typing
    choices = []
    for ab in valid_abilities:
        if current.lower() in ab.name.lower() or current.lower() in ab.identifier.lower():
            # Mostramos el NOMBRE bonito, pero el bot recibe el IDENTIFICADOR seguro
            choices.append(app_commands.Choice(name=ab.name, value=ab.identifier))

    return choices[:25]

class GameplayCog(commands.Cog):
    """
    Handles player-facing commands (Voting, Actions, Status).
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # The voting manager handles the math. We keep an instance here.
        self.voting_manager = VotingManager()

    # Create a Slash Command Group for all /vote commands
    vote_group = app_commands.Group(name="vote", description="Comandos de votación para la fase de Día.")

    async def _validate_voter(self, interaction: discord.Interaction) -> bool:
        """Helper to ensure the user can actually vote right now."""
        if not hasattr(self.bot, "game_state"):
            await interaction.response.send_message("❌ La partida no ha comenzado.", ephemeral=True)
            return False
            
        state: GameState = self.bot.game_state
        if state.phase != Phase.DAY:
            await interaction.response.send_message("🌙 Solo puedes votar durante el Día.", ephemeral=True)
            return False

        player = state.get_player(interaction.user.id)
        if not player or not player.is_alive:
            await interaction.response.send_message("💀 Los muertos no votan.", ephemeral=True)
            return False

        return True

    @vote_group.command(name="cast", description="Emite tu voto contra un jugador.")
    @app_commands.describe(target="El jugador que deseas linchar")
    async def vote_cast(self, interaction: discord.Interaction, target: discord.Member):
        if not await self._validate_voter(interaction):
            return

        state: GameState = self.bot.game_state
        voter = state.get_player(interaction.user.id)
        target_player = state.get_player(target.id)

        if not target_player or not target_player.is_alive:
            await interaction.response.send_message("❌ No puedes votar por alguien que no está en la partida o ya está muerto.", ephemeral=True)
            return

        # Calculate vote weight based on Conditions (e.g., Double Vote, Sanctioned)
        vote_weight = float(voter.role.flags.get("vote_weight", 1.0))

        # Multiply by active conditions (Buffs/Debuffs)
        for condition in voter.statuses:
            vote_weight *= condition.get_vote_multiplier()

        if vote_weight <= 0:
            await interaction.response.send_message("❌ Tu derecho a voto ha sido revocado.", ephemeral=True)
            return

        # Register the vote in the engine
        state = self.bot.game_state
        self.bot.voting_manager.cast_vote(state, voter.user_id, target_player.user_id, weight=vote_weight)
        
        # UI Feedback
        await interaction.response.send_message(f"🗳️ **{interaction.user.display_name}** ha votado por **{target.display_name}**.")
        
        # Check for absolute majority automatically
        alive_players = state.get_alive_players()
        alive_count = len(alive_players)

        vote_modifiers = {}
        for p in alive_players:
            if p.role:
                extra = p.role.flags.get("lynch_weight", 0)
                if extra > 0:
                    vote_modifiers[p.user_id] = extra

        majority_target = self.voting_manager.check_majority(alive_count, extra_thresholds=vote_modifiers)
        
        if majority_target:
            await interaction.channel.send(
                f"⚖️ **¡MAYORÍA ALCANZADA!** <@{majority_target}> ha sido condenado a la horca.\n"
                "🔒 *El canal ha sido silenciado a la espera del Game Master.*"
            )
            # Lock the channel to prevent post-lynch discussion
            # Note: This locks it for everyone without explicit admin override.
            await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)

    @vote_group.command(name="clear", description="Retira tu voto actual.")
    async def vote_clear(self, interaction: discord.Interaction):
        if not await self._validate_voter(interaction):
            return
        state = self.bot.game_state
        
        self.voting_manager.unvote(state, interaction.user.id)
        
        await interaction.response.send_message(f"💨 **{interaction.user.display_name}** ha retirado su voto.")

    @vote_group.command(name="mine", description="Revisa por quién estás votando actualmente.")
    async def vote_mine(self, interaction: discord.Interaction):
        if not hasattr(self.bot, "game_state"):
            await interaction.response.send_message("❌ La partida no ha comenzado.", ephemeral=True)
            return

        current_target_id = self.voting_manager.votes.get(interaction.user.id)
        if current_target_id:
            await interaction.response.send_message(f"🔍 Actualmente estás votando por: <@{current_target_id}>.", ephemeral=True)
        else:
            await interaction.response.send_message("🔍 Actualmente no estás votando por nadie.", ephemeral=True)


    @vote_group.command(name="end_day", description="Vota para terminar el Día anticipadamente (requiere 2/3).")
    async def vote_end_day(self, interaction: discord.Interaction):
        # 1. Validate the voter using the helper we created in Paso 16
        if not await self._validate_voter(interaction):
            return

        # 2. Fetch state data
        state: GameState = self.bot.game_state
        alive_count = len(state.get_alive_players())
        
        # 3. Register the vote in the engine
        self.voting_manager.cast_end_day(interaction.user.id)
        
        # 4. Calculate threshold for the UI
        current_votes = len(self.voting_manager.end_day_votes)
        threshold = (alive_count * 2 + 2) // 3

        # 5. UI Feedback
        await interaction.response.send_message(
            f"⏩ **{interaction.user.display_name}** ha votado para terminar el Día anticipadamente. "
            f"*(Faltan {threshold - current_votes} votos)*"
        )

        # 6. Check if the 2/3 majority was reached
        if self.voting_manager.check_end_day_majority(alive_count):
            await interaction.channel.send(
                "🌙 **¡MAYORÍA DE 2/3 ALCANZADA!**\n"
                "El pueblo ha decidido que no hay nada más que discutir.\n"
                "🔒 *El canal ha sido silenciado a la espera del Game Master.*"
            )
            # Lock the channel to prevent further chatter
            await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)

    @vote_group.command(name="summary", description="Muestra el resumen y recuento actual de los votos.")
    async def vote_summary(self, interaction: discord.Interaction):
        # 1. Basic validations
        if not hasattr(self.bot, "game_state"):
            await interaction.response.send_message("❌ La partida no ha comenzado.", ephemeral=True)
            return

        state: GameState = self.bot.game_state
        if state.phase != Phase.DAY:
            await interaction.response.send_message("🌙 Las votaciones solo ocurren durante el Día.", ephemeral=True)
            return

        tally = self.voting_manager.get_tally()
        alive_count = len(state.get_alive_players())
        
        if alive_count == 0:
            await interaction.response.send_message("❌ No hay jugadores vivos.", ephemeral=True)
            return

        # 2. Group voters by their target to show "Who voted for whom"
        voters_by_target = {}
        for voter_id, target in self.voting_manager.votes.items():
            voter = state.get_player(voter_id)
            
            if voter and voter.role and voter.role.flags.get("hidden_vote"):
                voter_name = f"👁️‍🗨️ **{_glitch_name()}**"
            else:
                voter_name = f"<@{voter_id}>"

            if target not in voters_by_target:
                voters_by_target[target] = []
            voters_by_target[target].append(voter_name)

        # Absolute majority formula
        base_threshold = (alive_count // 2) + 1

        # 3. Build the UI
        embed = discord.Embed(
            title="📊 Resumen de Votación", 
            description=f"Se requieren **{threshold}** votos para alcanzar la mayoría absoluta.",
            color=discord.Color.dark_red()
        )

        # Lynch Votes
        if not tally:
            embed.add_field(name="Estado Actual", value="Nadie ha emitido un voto aún.", inline=False)
        else:
            for target_id, weight in tally.items():
                target_threshold = base_threshold

                if target_id == "NO_LYNCH":
                    target_name = "🛑 Saltar Linchamiento"
                else:
                    target_name = f"<@{target_id}>"
                    target_player = state.get_player(target_id)
                    if target_player and target_player.role:
                        extra_votes = target_player.role.flags.get("lynch_weight", 0)
                        target_threshold += extra_votes
                    
                filled_blocks = int(weight)
                empty_blocks = max(0, int(threshold - filled_blocks))
                
                if weight >= threshold:
                    progress_bar = "🟥" * int(threshold) + " 💀 MAYORÍA"
                else:
                    progress_bar = "🟥" * filled_blocks + "⬜" * empty_blocks
                
                formatted_weight = f"{weight:.1f}".rstrip('0').rstrip('.')
                
                # Join the voters with a comma
                voter_mentions = ", ".join(voters_by_target.get(target_id, []))
                
                embed.add_field(
                    name=f"{target_name} ({formatted_weight} votos)", 
                    value=f"{progress_bar}\n↳ **Votantes:** {voter_mentions}", 
                    inline=False
                )

        # 4. End Day Votes summary
        end_day_count = len(self.voting_manager.end_day_votes)
        if end_day_count > 0:
            end_day_threshold = (alive_count * 2 + 2) // 3
            end_day_voters = ", ".join([f"<@{v_id}>" for v_id in self.voting_manager.end_day_votes])
            
            embed.add_field(
                name=f"⏩ Votos para Terminar el Día ({end_day_count}/{end_day_threshold})",
                value=f"**Votantes:** {end_day_voters}",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

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
                value="*Sin límite definido o a la espera del Game Master.*", 
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
        for flag_name, temp_ab in temp_registry.items():
            if player.role.flags.get(flag_name):
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