import time
import logging
import discord
from discord.ext import commands
from discord import app_commands

from core.state import GameState
from core.voting import VotingManager
from core.time import Phase

logger = logging.getLogger("cognitas.cogs.gameplay")

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
        vote_weight = 1.0

        if voter.role and voter.role.flags.get("permanent_double_vote"):
            vote_weight *= 2.0
            
        # Then multiply by active conditions
        for condition in voter.statuses:
            vote_weight *= condition.get_vote_multiplier()

        if vote_weight <= 0:
            await interaction.response.send_message("❌ Tu derecho a voto ha sido revocado por un estado alterado.", ephemeral=True)
            return

        # Register the vote in the engine
        self.voting_manager.cast_vote(voter.user_id, target_player.user_id, weight=vote_weight)
        
        # UI Feedback
        await interaction.response.send_message(f"🗳️ **{interaction.user.display_name}** ha votado por **{target.display_name}**.")
        
        # Check for absolute majority automatically
        alive_count = len(state.get_alive_players())
        majority_target = self.voting_manager.check_majority(alive_count)
        
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

        self.voting_manager.unvote(interaction.user.id)
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
            if target not in voters_by_target:
                voters_by_target[target] = []
            voters_by_target[target].append(f"<@{voter_id}>")

        # Absolute majority formula
        threshold = (alive_count // 2) + 1

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
                if target_id == "NO_LYNCH":
                    target_name = "🛑 Saltar Linchamiento"
                else:
                    target_name = f"<@{target_id}>"
                    
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

    @app_commands.command(name="act", description="Usa la habilidad de tu rol para la fase actual.")
    @app_commands.describe(
        target="El jugador objetivo de tu habilidad (si aplica).",
        note="Nota opcional para el Game Master."
    )
    async def act(self, interaction: discord.Interaction, target: discord.Member = None, note: str = None):
        # 1. Base validations
        if not hasattr(self.bot, "game_state"):
            await interaction.response.send_message("❌ La partida no está activa.", ephemeral=True)
            return

        state: GameState = self.bot.game_state
        player = state.get_player(interaction.user.id)

        if not player or not player.is_alive:
            await interaction.response.send_message("💀 Los muertos no pueden usar habilidades.", ephemeral=True)
            return

        if not player.role or not player.role.abilities:
            await interaction.response.send_message("❌ Tu rol no tiene habilidades asignadas.", ephemeral=True)
            return

        # 2. Determine the correct ability based on the current Phase
        from core.time import Phase
        from core.actions import ActionTag, TargetType

        expected_tag = ActionTag.DAY_ACT if state.phase == Phase.DAY else ActionTag.NIGHT_ACT
        
        # Find the first ability that matches the phase
        # (Assuming 1 active ability per phase for standard SMT/P3 roles)
        active_ability = next((ab for ab in player.role.abilities if ab.tag == expected_tag), None)

        if not active_ability:
            fase_str = "el Día" if state.phase == Phase.DAY else "la Noche"
            await interaction.response.send_message(f"💤 Tu rol no tiene habilidades activas durante {fase_str}.", ephemeral=True)
            return

        # 3. Target Validation based on Ability Blueprint
        target_id = target.id if target else None

        if active_ability.target_type == TargetType.SINGLE and not target_id:
            await interaction.response.send_message(f"🎯 Tu habilidad (**{active_ability.name}**) requiere que selecciones un objetivo.", ephemeral=True)
            return
            
        if active_ability.target_type == TargetType.NONE and target_id:
            # We ignore the target but warn the user to avoid confusion
            logger.debug(f"User {player.user_id} provided a target for a NONE target ability. Ignoring target.")
            target_id = None 

        if target_id:
            target_player = state.get_player(target_id)
            if not target_player or not target_player.is_alive:
                await interaction.response.send_message("❌ El objetivo no es válido o ya está muerto.", ephemeral=True)
                return
            
            # Prevent self-targeting unless explicitly allowed (Future-proofing)
            if target_id == player.user_id and active_ability.target_type != TargetType.SELF:
                await interaction.response.send_message("❌ No puedes usar esta habilidad en ti mismo.", ephemeral=True)
                return

        # 4. Submit to ActionManager
        if not hasattr(self.bot, "action_manager"):
            await interaction.response.send_message("⚠️ Error interno: ActionManager no inicializado.", ephemeral=True)
            return

        gimmick = getattr(self.bot, "active_gimmick", None)

        # The ActionManager returns a payload with the UI text, status, and notifications
        result = self.bot.action_manager.submit_action(
            source_player=player, 
            target_id=target_id, 
            ability=active_ability, 
            state=state,           
            gimmick=gimmick,       
            note=note              
        )

        # 5. Process Expansion Gimmick Notifications (e.g., Fuuka's Radar) (NUEVO)
        secret_notes = result.get("secret_notifications", {})
        if secret_notes:
            for uid, msg_text in secret_notes.items():
                notified_player = state.get_player(uid)
                if notified_player and notified_player.private_channel_id:
                    priv_channel = interaction.guild.get_channel(notified_player.private_channel_id)
                    if priv_channel:
                        # Mandamos el mensaje silenciosamente al canal del oráculo
                        await priv_channel.send(msg_text)

        # 6. UI Feedback based on Engine response (ACTUALIZADO)
        if result["status"] == "blocked":
            await interaction.response.send_message(f"🛑 {result['ui_text']}", ephemeral=True)
            
        elif result["status"] == "redirected" and result.get("condition") == "confusion":
            msg = f"🌀 {result['ui_try']}\n"
            msg += result['ui_result'].format(new_target=f"<@{result['new_target']}>")
            await interaction.response.send_message(msg, ephemeral=True)
            
        else:
            target_str = f" sobre <@{result.get('new_target', target_id)}>" if target_id else ""
            note_str = f"\n📝 *Nota para el GM: {note}*" if note else ""
            await interaction.response.send_message(
                f"✅ Has preparado tu habilidad (**{active_ability.name}**){target_str} para esta fase.{note_str}", 
                ephemeral=True
            )

        # 6. Silent log for the Game Master
        log_channel_id = state.discord_setup.get("log_channel_id")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                t_mention = f"<@{target_id}>" if target_id else "Ninguno"
                await log_channel.send(f"📥 **ACCIÓN REGISTRADA:** {interaction.user.mention} preparó **{active_ability.name}** -> Objetivo: {t_mention}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GameplayCog(bot))
    logger.info("GameplayCog loaded.")