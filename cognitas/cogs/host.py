import time
import logging
import discord
from discord.ext import commands
from discord import app_commands
import importlib
import asyncio
from data.loader import RoleLoader
from core.state import 
from core.time import TimeManager, Phase
from utils.discord_sync import process_player_death
from conditions.engine import 


logger = logging.getLogger("cognitas.cogs.host")

class HostCog(commands.Cog):
    """
    Handles Game Master commands.
    Acts as the UI layer connecting Discord interactions to the Game Engine.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    from conditions.builtin import (
        ParalyzedCondition, DrowsinessCondition, ConfusionCondition, 
        JailedCondition, SilencedCondition, DoubleVoteCondition, 
        SanctionedCondition, WoundedCondition, PoisonedCondition
    )

    condition_map = {
        "paralyzed": ParalyzedCondition,
        "drowsiness": DrowsinessCondition,
        "confusion": ConfusionCondition,
        "jailed": JailedCondition,
        "silenced": SilencedCondition,
        "double_vote": DoubleVoteCondition,
        "sanctioned": SanctionedCondition,
        "wounded": WoundedCondition,
        "poisoned": PoisonedCondition
    }

    # ---------------------------------------------------------
    # CONDITION MANAGEMENT COMMANDS
    # ---------------------------------------------------------
    effects_group = app_commands.Group(name="effects", description="GM: Gestión de estados alterados y condiciones.", default_permissions=discord.Permissions(administrator=True))

    @effects_group.command(name="apply", description="Aplica un estado alterado a un jugador.")
    @app_commands.describe(duration="Duración en fases (opcional, sobrescribe por defecto)")
    async def effects_apply(self, interaction: discord.Interaction, target: discord.Member, condition_id: str, duration: int = None):
        if condition_id not in self.condition_map:
            await interaction.response.send_message("❌ Estado alterado no reconocido.", ephemeral=True)
            return

        state: GameState = getattr(self.bot, "game_state", None)
        if not state: return
            
        cond_manager = ConditionManager(state)
        condition_class = self.condition_map[condition_id]
        
        # Instantiate and optionally override duration
        new_condition = condition_class()
        if duration is not None:
            new_condition.duration = duration
        
        cond_manager.apply_condition(target.id, new_condition)

        # UI Feedback
        ui_text = getattr(new_condition, "ui_on_apply", f"Se aplicó {new_condition.name} a {{mention}}.")
        await interaction.response.send_message(f"✅ {ui_text.format(mention=target.mention)}")
        logger.info(f"Applied {condition_id} to {target.id} (Duration: {new_condition.duration})")

    @effects_group.command(name="heal", description="Cura un estado específico de un jugador, o todos si se omite el estado.")
    @app_commands.describe(condition_id="ID del estado a curar (dejar vacío para limpiar todo)")
    async def effects_heal(self, interaction: discord.Interaction, target: discord.Member, condition_id: str = None):
        state: GameState = getattr(self.bot, "game_state", None)
        if not state: return

        player = state.get_player(target.id)
        if not player or not player.is_alive:
            await interaction.response.send_message("❌ Jugador no válido o muerto.", ephemeral=True)
            return

        if condition_id:
            # Heal specific condition
            original_count = len(player.statuses)
            player.statuses = [cond for cond in player.statuses if cond.id_name != condition_id]
            
            if len(player.statuses) < original_count:
                await interaction.response.send_message(f"⚕️ Se ha curado el estado **{condition_id}** de {target.mention}.")
            else:
                await interaction.response.send_message(f"⚠️ {target.mention} no estaba afectado por **{condition_id}**.", ephemeral=True)
        else:
            # Cleansed all
            player.statuses.clear()
            await interaction.response.send_message(f"✨ Todos los estados alterados de {target.mention} han sido purificados.")
            
        logger.info(f"Healed effects for {target.id}. Specific: {condition_id or 'ALL'}")

    @effects_group.command(name="list", description="Lista los estados activos de un jugador.")
    async def effects_list(self, interaction: discord.Interaction, target: discord.Member):
        state: GameState = getattr(self.bot, "game_state", None)
        if not state: return

        player = state.get_player(target.id)
        if not player:
            await interaction.response.send_message("❌ Jugador no encontrado en la partida.", ephemeral=True)
            return

        embed = discord.Embed(title=f"🔍 Estados de {target.display_name}", color=discord.Color.blue())
        
        if not player.statuses:
            embed.description = "El jugador está completamente sano."
        else:
            for cond in player.statuses:
                tipo = "🛑 Debuff" if cond.is_negative else "❇️ Buff"
                stack_info = f" | Cargas: {cond.stacks}" if cond.stacking_type == "sum" else ""
                embed.add_field(
                    name=f"{cond.name} ({tipo})", 
                    value=f"⏳ Duración restante: {cond.duration} fase(s){stack_info}", 
                    inline=False
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @effects_group.command(name="inspect", description="Inspecciona los detalles técnicos de un estado alterado.")
    async def effects_inspect(self, interaction: discord.Interaction, condition_id: str):
        if condition_id not in self.condition_map:
            await interaction.response.send_message("❌ Estado alterado no encontrado.", ephemeral=True)
            return

        cond_class = self.condition_map[condition_id]
        dummy_instance = cond_class() # Create a dummy to read default attributes

        embed = discord.Embed(title=f"📘 Inspección: {dummy_instance.name}", color=discord.Color.blurple())
        embed.add_field(name="ID Interno", value=f"`{dummy_instance.id_name}`", inline=True)
        embed.add_field(name="Tipo", value="🛑 Debuff" if dummy_instance.is_negative else "❇️ Buff", inline=True)
        embed.add_field(name="Acumulación (Stacking)", value=dummy_instance.stacking_type.capitalize(), inline=True)
        
        # Check hooks dynamically
        mechanics = []
        if dummy_instance.is_silenced(): mechanics.append("- 🤐 Silencia el canal de voz/texto.")
        if dummy_instance.is_protected(): mechanics.append("- 🛡️ Protege de asesinatos nocturnos.")
        if dummy_instance.get_vote_multiplier() != 1.0: mechanics.append(f"- ⚖️ Modificador de voto.")
        
        embed.add_field(name="Mecánicas Detectadas", value="\n".join(mechanics) if mechanics else "Ninguna mecánica especial bloqueante.", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------------------------------------------------------
    # DISCORD ENVIRONMENT SETUP COMMANDS
    # ---------------------------------------------------------

    @app_commands.command(name="set_channels", description="GM: Configura los canales principales de juego.")
    @app_commands.default_permissions(administrator=True) # Solo admins pueden usar esto
    @app_commands.describe(
        game_channel="El canal público donde se juega de Día",
        graveyard_channel="El canal exclusivo para los muertos (opcional)"
    )
    async def set_channels(self, interaction: discord.Interaction, 
                           game_channel: discord.TextChannel, 
                           graveyard_channel: discord.TextChannel = None):
        if not hasattr(self.bot, "game_state"):
            await interaction.response.send_message("❌ Inicializa la partida primero.", ephemeral=True)
            return

        state: GameState = self.bot.game_state
        state.discord_setup["game_channel_id"] = game_channel.id
        if graveyard_channel:
            state.discord_setup["graveyard_channel_id"] = graveyard_channel.id

        msg = f"✅ **Canal de Juego** configurado a {game_channel.mention}."
        if graveyard_channel:
            msg += f"\n✅ **Cementerio** configurado a {graveyard_channel.mention}."
            
        await interaction.response.send_message(msg, ephemeral=True)
        logger.info(f"Main channels updated by {interaction.user.id}")

    @app_commands.command(name="set_log_channel", description="GM: Configura el canal privado para registros del sistema.")
    @app_commands.default_permissions(administrator=True)
    async def set_log_channel(self, interaction: discord.Interaction, log_channel: discord.TextChannel):
        if not hasattr(self.bot, "game_state"):
            await interaction.response.send_message("❌ Inicializa la partida primero.", ephemeral=True)
            return

        self.bot.game_state.discord_setup["log_channel_id"] = log_channel.id
        await interaction.response.send_message(f"✅ **Canal de Logs** configurado a {log_channel.mention}.", ephemeral=True)
        logger.info(f"Log channel updated to {log_channel.id}")

    @app_commands.command(name="link_roles", description="GM: Vincula los roles de Discord para Vivos y Muertos.")
    @app_commands.default_permissions(administrator=True)
    async def link_roles(self, interaction: discord.Interaction, alive_role: discord.Role, dead_role: discord.Role):
        if not hasattr(self.bot, "game_state"):
            await interaction.response.send_message("❌ Inicializa la partida primero.", ephemeral=True)
            return

        state: GameState = self.bot.game_state
        state.discord_setup["alive_role_id"] = alive_role.id
        state.discord_setup["dead_role_id"] = dead_role.id

        await interaction.response.send_message(
            f"✅ Roles vinculados:\n"
            f"**Vivo:** {alive_role.mention}\n"
            f"**Muerto:** {dead_role.mention}", 
            ephemeral=True
        )
        logger.info("Alive and Dead roles linked successfully.")

    @app_commands.command(name="show_channels", description="GM: Muestra la configuración actual del entorno.")
    @app_commands.default_permissions(administrator=True)
    async def show_channels(self, interaction: discord.Interaction):
        if not hasattr(self.bot, "game_state"):
            await interaction.response.send_message("❌ No hay partida activa.", ephemeral=True)
            return

        setup_data = self.bot.game_state.discord_setup
        
        # Helper to format IDs cleanly for Discord UI
        def format_channel(c_id): return f"<#{c_id}>" if c_id else "No configurado"
        def format_role(r_id): return f"<@&{r_id}>" if r_id else "No configurado"

        embed = discord.Embed(title="⚙️ Configuración de Entorno", color=discord.Color.gold())
        embed.add_field(name="Canal de Juego", value=format_channel(setup_data.get("game_channel_id")), inline=False)
        embed.add_field(name="Canal de Logs", value=format_channel(setup_data.get("log_channel_id")), inline=False)
        embed.add_field(name="Cementerio", value=format_channel(setup_data.get("graveyard_channel_id")), inline=False)
        embed.add_field(name="Rol Vivo", value=format_role(setup_data.get("alive_role_id")), inline=True)
        embed.add_field(name="Rol Muerto", value=format_role(setup_data.get("dead_role_id")), inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="assign", description="GM: Asigna rol a un jugador, auto-detecta su cuarto y le da el rol Vivo.")
    @app_commands.describe(
        member="El usuario de Discord a ingresar a la partida",
        role_key="El ID del rol en el JSON (ej: makoto_yuki)",
        private_channel="(Opcional) Canal manual. Si se omite, buscará el del Terraform."
    )
    @app_commands.default_permissions(administrator=True)
    async def assign_player(self, interaction: discord.Interaction, member: discord.Member, 
                            role_key: str, private_channel: discord.TextChannel = None):
        
        # 1. Base validations
        if not hasattr(self.bot, "game_state"):
            await interaction.response.send_message("❌ La partida no está inicializada.", ephemeral=True)
            return
            
        if not hasattr(self.bot, "role_registry") or role_key not in self.bot.role_registry:
            await interaction.response.send_message(f"❌ El rol `{role_key}` no existe en memoria. ¿Cargaste la expansión?", ephemeral=True)
            return

        state = self.bot.game_state
        guild = interaction.guild

        # 2. Auto-detect the Private Channel if not provided
        if not private_channel:
            category_id = state.discord_setup.get("category_id")
            expected_name = f"hq-{role_key.replace('_', '-')}"
            
            if category_id:
                category = guild.get_channel(category_id)
                if category:
                    private_channel = discord.utils.get(category.text_channels, name=expected_name)
                    
            if not private_channel:
                await interaction.response.send_message(
                    f"❌ No pude encontrar el canal automático `{expected_name}`. "
                    f"Asegúrate de haber usado `/terraform` o especifica un canal manualmente.", 
                    ephemeral=True
                )
                return

        # 3. Grant the user exclusive access to their private room
        try:
            await private_channel.set_permissions(
                member, 
                read_messages=True, 
                send_messages=True,
                reason=f"Assigning {role_key} to {member.display_name}"
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Me faltan permisos para modificar el acceso al canal privado.", ephemeral=True)
            return

        # 4. Engine Registration
        from core.models import Player
        import copy
        
        new_player = Player(user_id=member.id)
        new_player.role = copy.deepcopy(self.bot.role_registry[role_key])
        new_player.private_channel_id = private_channel.id
        
        state.add_player(new_player)

        # 5. Discord Role Management (Alive/Dead)
        alive_role_id = state.discord_setup.get("alive_role_id")
        dead_role_id = state.discord_setup.get("dead_role_id")
        
        roles_to_add = []
        roles_to_remove = []

        if alive_role_id:
            alive_role = guild.get_role(alive_role_id)
            if alive_role: roles_to_add.append(alive_role)
            
        if dead_role_id:
            dead_role = guild.get_role(dead_role_id)
            if dead_role: roles_to_remove.append(dead_role)

        try:
            if roles_to_add: await member.add_roles(*roles_to_add)
            if roles_to_remove: await member.remove_roles(*roles_to_remove)
        except discord.Forbidden:
            logger.error("Permissions missing to assign Alive/Dead roles.")

        # 6. UI Feedback and Welcome Message
        await interaction.response.send_message(
            f"✅ Jugador {member.mention} asignado como **{new_player.role.name}**.\n"
            f"🔑 Se le dio acceso a {private_channel.mention}."
        )
        
        embed = discord.Embed(
            title=f"Bienvenido/a, {new_player.role.name}",
            description=(
                f"Este es tu canal privado. Aquí recibirás notificaciones secretas "
                f"y usarás el comando `/act` durante tus fases activas.\n\n"
                f"**Alineación:** {new_player.role.alignment}\n"
                f"*(Las mecánicas pasivas y de rol ya están activas en el motor)*"
            ),
            color=discord.Color.green()
        )
        await private_channel.send(content=member.mention, embed=embed)
        logger.info(f"Player {member.id} assigned to {role_key} in {private_channel.id}")

    @app_commands.command(name="set_expansion", description="GM: Carga los roles (JSON) y las mecánicas (Python) de una expansión.")
    @app_commands.describe(perfil="Nombre de la expansión (ej. 'persona', 'smt', 'vanilla')")
    @app_commands.default_permissions(administrator=True)
    async def set_expansion(self, interaction: discord.Interaction, perfil: str):
        perfil = perfil.lower()
        
        # 1. Load the Roles JSON
        filename = f"roles_{perfil}.json"
        loader = RoleLoader(data_dir="data")
        loaded_roles = loader.load_roles(filename)
        
        if not loaded_roles:
            await interaction.response.send_message(f"❌ Error al cargar los roles de `{filename}`.", ephemeral=True)
            return
            
        self.bot.role_registry = loaded_roles
        
        # 2. Dynamically inject the Python Gimmick Skeleton
        try:
            # This attempts to import cognitas/expansions/persona.py
            gimmick_module = importlib.import_module(f"expansions.{perfil}")
            # Grabs the ExpansionGimmick class from that file
            GimmickClass = getattr(gimmick_module, "ExpansionGimmick")
            self.bot.active_gimmick = GimmickClass()
            gimmick_name = self.bot.active_gimmick.name
        except (ImportError, AttributeError) as e:
            # Fallback to base expansion if no custom Python file exists
            logger.warning(f"No specific gimmick python file found for {perfil}. Using BaseExpansion. Error: {e}")
            from expansions.base import BaseExpansion
            self.bot.active_gimmick = BaseExpansion()
            gimmick_name = "Sin mecánicas especiales"

        if hasattr(self.bot, "game_state"):
            self.bot.game_state.discord_setup["expansion"] = perfil
            
        await interaction.response.send_message(
            f"✅ **Expansión Cargada:** {perfil.upper()}\n"
            f"👥 **Roles en memoria:** {len(loaded_roles)}\n"
            f"⚙️ **Mecánica Activa:** {gimmick_name}", 
            ephemeral=True
        )

    @app_commands.command(name="debug_roles", description="GM: Lista las claves de los roles cargados en memoria.")
    @app_commands.default_permissions(administrator=True)
    async def debug_roles(self, interaction: discord.Interaction):
        if not hasattr(self.bot, "role_registry") or not self.bot.role_registry:
            await interaction.response.send_message("❌ No hay roles cargados. Usa `/set_expansion` primero.", ephemeral=True)
            return
            
        keys = list(self.bot.role_registry.keys())
        keys_str = ", ".join(keys)
        
        embed = discord.Embed(
            title="🛠️ Debug: Roles Cargados", 
            description=f"**Total en memoria:** {len(keys)}\n\n`{keys_str}`", 
            color=discord.Color.light_grey()
        )
        embed.set_footer(text="Estas claves son las que debes usar en el comando /assign.")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------------------------------------------------------
    # CYCLE RELATED COMMANDS
    # ---------------------------------------------------------

    @app_commands.command(name="next_phase", description="GM: Avanza la fase, procesa estados y ajusta canales. Inicia el reloj.")
    @app_commands.describe(duracion="Minutos que durará la fase (0 para dejarla sin límite).")
    @app_commands.default_permissions(administrator=True)
    async def next_phase(self, interaction: discord.Interaction, duracion: int = 0):
        await interaction.response.defer()

        if not hasattr(self.bot, "game_state"):
            await interaction.followup.send("❌ La partida no está inicializada.")
            return

        state: GameState = self.bot.game_state
        guild = interaction.guild

        # 1. Process conditions and deaths (Same as Step 26)
        from conditions.engine import ConditionManager
        cond_manager = ConditionManager(state)
        cond_manager.process_phase_end()

        alive_role_id = state.discord_setup.get("alive_role_id")
        for player in state.players.values():
            if not player.is_alive:
                member = guild.get_member(player.user_id)
                if member and alive_role_id and any(r.id == alive_role_id for r in member.roles):
                    from utils.discord_sync import process_player_death
                    await process_player_death(self.bot, guild, player, reason="Efectos al final de la fase")

        # 2. Advance Clock
        from core.time import TimeManager, Phase
        gimmick = getattr(self.bot, "active_gimmick", None)
        time_manager = TimeManager(state, gimmick=gimmick)
        gimmick_announcement = time_manager.advance_phase()

        # 3. Clear Voting/Action Queues
        if hasattr(self.bot, "voting_manager"):
            self.bot.voting_manager.clear_all_votes()
        if hasattr(self.bot, "action_manager") and state.phase == Phase.DAY:
            self.bot.action_manager.clear_queue()

        # 4. Open/Close Channel
        can_speak = (state.phase == Phase.DAY)
        game_channel_id = state.discord_setup.get("game_channel_id")
        
        if game_channel_id:
            game_channel = guild.get_channel(game_channel_id)
            if game_channel:
                # 4.1 Update talking permissions
                await game_channel.set_permissions(guild.default_role, send_messages=can_speak)

                # 4.2 Dynamic Channel Renaming
                fase_url_name = "día" if state.phase == Phase.DAY else "noche"
                new_channel_name = f"{fase_url_name}-{state.cycle}"
                
                try:
                    if game_channel.name != new_channel_name:
                        await game_channel.edit(name=new_channel_name, reason="Phase transition rename")
                        logger.info(f"Game channel renamed to {new_channel_name}")
                except discord.RateLimited:
                    logger.warning("Rate limit hit while trying to rename the game channel. Skipping rename.")
                except discord.Forbidden:
                    logger.error("Missing permissions to rename the game channel.")

        # Configurar el reloj si se pasó una duración
        end_time_msg = ""
        if duracion > 0:
            end_time = int(time.time()) + (duracion * 60)
            state.discord_setup["phase_end_time"] = end_time
            end_time_msg = f"\n⏳ **Tiempo límite:** <t:{end_time}:R> (a las <t:{end_time}:t>)."
        else:
            state.discord_setup["phase_end_time"] = None

        # 5. UI Announcement
        fase_es = "☀️ DÍA" if state.phase == Phase.DAY else "🌙 NOCHE"
        msg = f"**¡La fase ha avanzado!** Ahora es **{fase_es} {state.cycle}**.{end_time_msg}"
        
        if gimmick_announcement:
            msg += f"\n\n✨ *{gimmick_announcement}*"

        await interaction.followup.send(msg)

    @app_commands.command(name="lock_channel", description="GM: Cierra el canal de juego prematuramente y detiene el reloj.")
    @app_commands.default_permissions(administrator=True)
    async def lock_channel(self, interaction: discord.Interaction):
        """Replaces the old 'end_day' manual close."""
        if not hasattr(self.bot, "game_state"):
            await interaction.response.send_message("❌ La partida no está inicializada.", ephemeral=True)
            return

        state: GameState = self.bot.game_state
        
        # 1. Stop the clock
        state.discord_setup["phase_end_time"] = None
        
        # 2. Lock the channel
        game_channel_id = state.discord_setup.get("game_channel_id")
        if game_channel_id:
            game_channel = interaction.guild.get_channel(game_channel_id)
            if game_channel:
                await game_channel.set_permissions(interaction.guild.default_role, send_messages=False)
                await interaction.response.send_message(
                    "🛑 **¡ALTO!**\n"
                    "🔒 *El Game Master ha detenido el tiempo y cerrado el canal. Por favor, esperen las resoluciones.*"
                )
                return
                
        await interaction.response.send_message("❌ No se pudo encontrar el canal de juego.", ephemeral=True)


    @app_commands.command(name="action_report", description="GM: Muestra quién ha actuado, quién falta y los resultados ordenados por prioridad.")
    @app_commands.default_permissions(administrator=True)
    async def action_report(self, interaction: discord.Interaction):
        if not hasattr(self.bot, "game_state") or not hasattr(self.bot, "action_manager"):
            await interaction.response.send_message("❌ El motor no está inicializado.", ephemeral=True)
            return

        from core.time import Phase
        from core.actions import ActionTag, ResolutionTime
        
        state: GameState = self.bot.game_state
        manager = self.bot.action_manager

        expected_tag = ActionTag.DAY_ACT if state.phase == Phase.DAY else ActionTag.NIGHT_ACT
        alive_players = state.get_alive_players()

        # 1. Identify who CAN act this phase
        expected_actors = []
        for p in alive_players:
            if p.role and any(ab.tag == expected_tag for ab in p.role.abilities):
                # Optionally, we could check if they are paralyzed/drowsy here and skip them,
                # but it's better to show them as "Missing" so the GM knows they are skipping.
                expected_actors.append(p.user_id)

        # 2. Get the submitted actions (Sorted automatically by our ActionManager)
        submitted_records = manager.get_resolution_report()
        submitted_ids = [record.source_id for record in submitted_records]

        # 3. Find the missing ones
        missing_ids = [u_id for u_id in expected_actors if u_id not in submitted_ids]

        # 4. Build the UI
        embed = discord.Embed(
            title=f"📋 Reporte de Acciones ({'Día' if state.phase == Phase.DAY else 'Noche'} {state.cycle})",
            color=discord.Color.dark_purple()
        )

        # --- SECTION: MISSING ACTIONS ---
        if missing_ids:
            missing_mentions = "\n".join([f"⚠️ <@{u_id}>" for u_id in missing_ids])
            embed.add_field(name=f"Faltan por Actuar ({len(missing_ids)})", value=missing_mentions, inline=False)
        else:
            embed.add_field(name="Faltan por Actuar", value="✅ ¡Todos han enviado sus acciones!", inline=False)

        # --- SECTION: SUBMITTED ACTIONS (Ordered) ---
        if not submitted_records:
            embed.add_field(name="Cola de Resolución", value="Vacía.", inline=False)
        else:
            report_lines = []
            for rec in submitted_records:
                # Target formatting
                target_str = f" ➔ <@{rec.target_id}>" if rec.target_id else ""
                
                # Accuracy Check Formatting (Hit or Miss)
                acc_icon = "🎯 ÉXITO" if rec.is_success else "❌ FALLO"
                acc_detail = f"({rec.roll}/{rec.ability.accuracy})" if not rec.is_success else ""
                
                # Resolution Timing Icon
                res_icon = "⚡" if rec.ability.resolution == ResolutionTime.INSTANT else "⏳"
                
                # Build the line
                line = f"`[{rec.ability.priority:02d}]` {res_icon} <@{rec.source_id}> usó **{rec.ability.name}**{target_str} | {acc_icon} {acc_detail}"
                
                # Append notes if they exist
                if rec.note:
                    line += f"\n   *📝 Nota: {rec.note}*"
                    
                report_lines.append(line)

            # Discord embeds have a 1024 character limit per field. 
            # We join them safely (Assuming it won't break 1024 for a standard 15 player game, 
            # but in production we might need to split chunks).
            embed.add_field(
                name="Acciones Registradas (Orden de Prioridad)", 
                value="\n\n".join(report_lines)[:1024], 
                inline=False
            )
            
        embed.set_footer(text="⚡ = Instantánea | ⏳ = En Cola (Fin de fase)")
        await interaction.response.send_message(embed=embed, ephemeral=True)


    # ---------------------------------------------------------
    # TERRAFORMING & WIPE COMMANDS
    # ---------------------------------------------------------

    @app_commands.command(name="terraform", description="GM: Crea roles, canales y carga la expansión automáticamente.")
    @app_commands.describe(expansion="Nombre de la expansión a cargar (ej. 'p3', 'smt')")
    @app_commands.default_permissions(administrator=True)
    async def terraform(self, interaction: discord.Interaction, expansion: str):
        # 1. Defer the response because creating 20 channels takes time
        await interaction.response.defer()
        guild = interaction.guild
        expansion = expansion.lower()

        # 2. Load Expansion Data (Roles & Gimmicks)
        filename = f"roles_{expansion}.json"
        loader = RoleLoader(data_dir="data")
        loaded_roles = loader.load_roles(filename)
        
        if not loaded_roles:
            await interaction.followup.send(f"❌ Error crítico: No se encontró `{filename}`.")
            return
            
        self.bot.role_registry = loaded_roles

        try:
            gimmick_module = importlib.import_module(f"expansions.{expansion}")
            GimmickClass = getattr(gimmick_module, "ExpansionGimmick")
            self.bot.active_gimmick = GimmickClass()
        except (ImportError, AttributeError):
            from expansions.base import BaseExpansion
            self.bot.active_gimmick = BaseExpansion()

        # 3. Create Discord Roles
        try:
            alive_role = await guild.create_role(name="Vivo", color=discord.Color.green(), reason="Terraform")
            dead_role = await guild.create_role(name="Muerto", color=discord.Color.dark_grey(), reason="Terraform")
        except discord.Forbidden:
            await interaction.followup.send("❌ No tengo permisos para crear roles en este servidor.")
            return

        # 4. Create Category
        category_name = f"🎮 MAFIA: {expansion.upper()}"
        category = await guild.create_category(name=category_name, reason="Terraform")

        # Base permissions: No one can see anything by default
        base_overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        # 5. Create Core Channels
        log_channel = await category.create_text_channel(name="logs-del-sistema", overwrites=base_overwrites)
        
        game_overwrites = base_overwrites.copy()
        game_overwrites[alive_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        game_overwrites[dead_role] = discord.PermissionOverwrite(read_messages=True, send_messages=False)
        game_channel = await category.create_text_channel(name="canal-de-juego", overwrites=game_overwrites)

        gy_overwrites = base_overwrites.copy()
        gy_overwrites[dead_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        graveyard = await category.create_text_channel(name="cementerio", overwrites=gy_overwrites)

        # 6. Create Private Channels for each loaded Role
        # We add a small delay to avoid hitting Discord's rate limits
        created_channels = []
        for role_key, role_obj in loaded_roles.items():
            ch_name = f"hq-{role_key.replace('_', '-')}"
            priv_ch = await category.create_text_channel(name=ch_name, overwrites=base_overwrites)
            created_channels.append(priv_ch)
            await asyncio.sleep(0.5) # Rate limit protection

        # 7. Save everything to GameState
        if not hasattr(self.bot, "game_state"):
            from core.state import GameState
            self.bot.game_state = GameState()
            
        state = self.bot.game_state
        state.discord_setup.update({
            "category_id": category.id,
            "game_channel_id": game_channel.id,
            "log_channel_id": log_channel.id,
            "graveyard_channel_id": graveyard.id,
            "alive_role_id": alive_role.id,
            "dead_role_id": dead_role.id,
            "expansion": expansion
        })

        # 8. Success Report
        await interaction.followup.send(
            f"✅ **Terraformación Completada ({expansion.upper()})**\n"
            f"🛠️ Categoría y Canales base creados.\n"
            f"🎭 Roles 'Vivo' y 'Muerto' generados.\n"
            f"🚪 {len(created_channels)} cuartos privados creados.\n\n"
            f"*Usa `/assign` para repartir los roles y los cuartos privados a los jugadores.*"
        )
        logger.info(f"Terraforming complete for expansion {expansion}.")

    @app_commands.command(name="wipe", description="GM: Destruye todos los canales y roles creados por el Terraform.")
    @app_commands.default_permissions(administrator=True)
    async def wipe(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        if not hasattr(self.bot, "game_state"):
            await interaction.followup.send("❌ No hay datos de partida para limpiar.")
            return
            
        state = self.bot.game_state
        setup = state.discord_setup
        guild = interaction.guild
        deleted_count = 0

        # 1. Delete all channels in the Terraformed Category
        category_id = setup.get("category_id")
        if category_id:
            category = guild.get_channel(category_id)
            if category:
                for channel in category.channels:
                    await channel.delete(reason="Wipe command")
                    deleted_count += 1
                    await asyncio.sleep(0.5) # Rate limit protection
                await category.delete(reason="Wipe command")
                deleted_count += 1

        # 2. Delete Roles
        alive_role_id = setup.get("alive_role_id")
        dead_role_id = setup.get("dead_role_id")
        
        for r_id in [alive_role_id, dead_role_id]:
            if r_id:
                role = guild.get_role(r_id)
                if role:
                    await role.delete(reason="Wipe command")

        # 3. Reset GameState (Hard reset of the core)
        from core.state import GameState
        self.bot.game_state = GameState()
        self.bot.action_manager.clear_queue()
        if hasattr(self.bot, "voting_manager"):
            self.bot.voting_manager.clear_all_votes()

        await interaction.followup.send(f"🧹 **Limpieza absoluta completada.** Se eliminaron {deleted_count} canales/categorías y se reinició la memoria del bot.")
        logger.info("Server wiped clean and core reset.")

        Este es el verdadero cinturón de herramientas de un Game Master. En la teoría del diseño de software, siempre asumimos que el usuario o el sistema se equivocarán en algún momento. Tener una suite de "Comandos de Intervención Divina" para editar el estado del juego sobre la marcha es lo que separa a un bot rígido que arruina partidas de un bot flexible que las salva.

Vamos a agrupar estas herramientas lógicamente. Añadiremos estos comandos a tu archivo cogs/host.py (y el de tiempo, que podemos hacer como un grupo).

Paso 43: Las Herramientas de Intervención (God Tools)

Explicación: Creamos comandos explícitos para forzar la muerte y resurrección (modificando roles de Discord en el proceso), editar las Flags al vuelo interpretando el tipo de dato (booleano, número o texto), sobrescribir la fase actual (y renombrar el canal de juego en el proceso) y ajustar o cancelar el reloj activo.

Líneas: Añadir al archivo cognitas/cogs/host.py (Dentro de HostCog).

Código:

Python
    # ---------------------------------------------------------
    # ERROR CORRECTION & GOD TOOLS
    # ---------------------------------------------------------

    @app_commands.command(name="force_kill", description="GM: Mata a un jugador instantáneamente saltándose las reglas.")
    @app_commands.describe(reason="Razón que aparecerá en el cementerio y logs.")
    @app_commands.default_permissions(administrator=True)
    async def force_kill(self, interaction: discord.Interaction, target: discord.Member, reason: str = "Intervención divina (Fuerza Mayor)"):
        state = getattr(self.bot, "game_state", None)
        if not state: return

        player = state.get_player(target.id)
        if not player or not player.is_alive:
            await interaction.response.send_message("❌ Jugador no encontrado o ya está muerto.", ephemeral=True)
            return

        from utils.discord_sync import process_player_death
        await process_player_death(self.bot, interaction.guild, player, reason=reason)
        await interaction.response.send_message(f"💀 **{target.display_name}** ha sido ejecutado por el Game Master.", ephemeral=True)

    @app_commands.command(name="force_revive", description="GM: Revive a un jugador y le devuelve los permisos de Vivo.")
    @app_commands.default_permissions(administrator=True)
    async def force_revive(self, interaction: discord.Interaction, target: discord.Member):
        state = getattr(self.bot, "game_state", None)
        if not state: return

        player = state.get_player(target.id)
        if not player:
            await interaction.response.send_message("❌ Jugador no encontrado en la partida.", ephemeral=True)
            return

        if player.is_alive:
            await interaction.response.send_message("⚠️ El jugador ya está vivo.", ephemeral=True)
            return

        # 1. Logical revive
        player.is_alive = True
        
        # 2. Discord Role Swap (Remove Dead, Add Alive)
        setup = state.discord_setup
        guild = interaction.guild
        roles_to_add, roles_to_remove = [], []
        
        if setup.get("alive_role_id"):
            alive_role = guild.get_role(setup["alive_role_id"])
            if alive_role: roles_to_add.append(alive_role)
            
        if setup.get("dead_role_id"):
            dead_role = guild.get_role(setup["dead_role_id"])
            if dead_role: roles_to_remove.append(dead_role)

        try:
            if roles_to_add: await target.add_roles(*roles_to_add)
            if roles_to_remove: await target.remove_roles(*roles_to_remove)
        except discord.Forbidden:
            logger.error("Missing permissions to revive player roles.")

        await interaction.response.send_message(f"✨ **{target.display_name}** ha sido revivido por el Game Master.", ephemeral=True)
        
        # Notify Logs
        log_channel_id = setup.get("log_channel_id")
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(f"👼 **SISTEMA (GM Override):** {target.mention} ha resucitado.")

    @app_commands.command(name="set_flag", description="GM: Añade o edita una variable pasiva (flag) de un jugador.")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Booleano (Verdadero/Falso)", value="bool"),
        app_commands.Choice(name="Número Entero", value="int"),
        app_commands.Choice(name="Texto", value="str")
    ])
    @app_commands.default_permissions(administrator=True)
    async def set_flag(self, interaction: discord.Interaction, target: discord.Member, flag_name: str, tipo: app_commands.Choice[str], valor: str):
        state = getattr(self.bot, "game_state", None)
        if not state: return

        player = state.get_player(target.id)
        if not player or not player.role:
            await interaction.response.send_message("❌ Jugador o rol no encontrado.", ephemeral=True)
            return

        # Type casting safely
        try:
            if tipo.value == "bool":
                parsed_value = valor.lower() in ("true", "1", "si", "yes", "t", "y")
            elif tipo.value == "int":
                parsed_value = int(valor)
            else:
                parsed_value = valor
        except ValueError:
            await interaction.response.send_message(f"❌ No se pudo convertir `{valor}` a `{tipo.name}`.", ephemeral=True)
            return

        # Apply to engine
        old_value = player.role.flags.get(flag_name, "None")
        player.role.flags[flag_name] = parsed_value

        await interaction.response.send_message(
            f"✅ Flag editada para {target.display_name}:\n"
            f"`{flag_name}`: `{old_value}` ➔ `{parsed_value}` ({tipo.value})", 
            ephemeral=True
        )

    @app_commands.command(name="set_phase", description="GM: Sobrescribe el número de ciclo y/o la fase actual.")
    @app_commands.choices(fase=[
        app_commands.Choice(name="Día", value="day"),
        app_commands.Choice(name="Noche", value="night")
    ])
    @app_commands.default_permissions(administrator=True)
    async def set_phase(self, interaction: discord.Interaction, fase: app_commands.Choice[str], ciclo: int):
        await interaction.response.defer(ephemeral=True)
        state = getattr(self.bot, "game_state", None)
        if not state: return

        from core.time import Phase
        new_phase = Phase.DAY if fase.value == "day" else Phase.NIGHT
        
        state.phase = new_phase
        state.cycle = ciclo

        # Update the visual channel name to match the forced reality
        game_channel_id = state.discord_setup.get("game_channel_id")
        if game_channel_id:
            game_channel = interaction.guild.get_channel(game_channel_id)
            if game_channel:
                fase_url_name = "día" if new_phase == Phase.DAY else "noche"
                new_channel_name = f"{fase_url_name}-{ciclo}"
                try:
                    await game_channel.edit(name=new_channel_name, reason="GM Forced Phase Edit")
                except discord.RateLimited:
                    pass

        await interaction.followup.send(f"⏱️ **Realidad alterada:** Ahora es **{fase.name} {ciclo}**.")

    # ---------------------------------------------------------
    # TIME MANIPULATION GROUP
    # ---------------------------------------------------------
    timer_group = app_commands.Group(name="timer", description="GM: Ajustes manuales del cronómetro de la fase.", default_permissions=discord.Permissions(administrator=True))

    @timer_group.command(name="adjust", description="Añade o resta minutos al cronómetro actual.")
    @app_commands.describe(minutos="Minutos a sumar (usa números negativos para restar).")
    async def timer_adjust(self, interaction: discord.Interaction, minutos: int):
        state = getattr(self.bot, "game_state", None)
        if not state: return

        current_end_time = state.discord_setup.get("phase_end_time")
        if not current_end_time:
            await interaction.response.send_message("❌ No hay ningún cronómetro activo en esta fase.", ephemeral=True)
            return

        import time
        # Add (or subtract) the seconds
        new_end_time = current_end_time + (minutos * 60)
        
        # Prevent the timer from being set in the past by accident
        if new_end_time <= int(time.time()):
            await interaction.response.send_message("❌ Ese ajuste haría que el tiempo terminara en el pasado. Usa `/timer cancel` o `/lock_channel` en su lugar.", ephemeral=True)
            return

        state.discord_setup["phase_end_time"] = new_end_time
        
        accion = "Añadidos" if minutos > 0 else "Restados"
        await interaction.response.send_message(f"⏳ **Cronómetro Ajustado:** {accion} {abs(minutos)} minutos.\nNuevo final: <t:{new_end_time}:R> (a las <t:{new_end_time}:t>).")

    @timer_group.command(name="cancel", description="Detiene el cronómetro actual sin cerrar el canal.")
    async def timer_cancel(self, interaction: discord.Interaction):
        state = getattr(self.bot, "game_state", None)
        if not state: return

        if not state.discord_setup.get("phase_end_time"):
            await interaction.response.send_message("⚠️ No hay cronómetro activo.", ephemeral=True)
            return

        state.discord_setup["phase_end_time"] = None
        await interaction.response.send_message("🛑 **Cronómetro cancelado.** La fase ah


async def setup(bot: commands.Bot) -> None:
    """Standard Cog setup function."""
    await bot.add_cog(HostCog(bot))
    logger.info("HostCog loaded.")