# cognitas/cogs/help.py
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from ..core.state import game

class HelpCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="help", description="Mostrar lista de comandos disponibles")
    async def help(self, interaction: discord.Interaction):
        user = interaction.user
        is_admin = user.guild_permissions.administrator
        can_purge = user.guild_permissions.manage_messages
        phase = getattr(game, "phase", None)

        # Determinar etiqueta de fase para el footer
        phase_label = "Desconocida"
        if phase == "day": phase_label = "Día"
        elif phase == "night": phase_label = "Noche"

        embed = discord.Embed(
            title="Asdrubot — Comandos",
            description="Índice de comandos Slash. Solo verás las secciones de Admin/Mod si tienes permisos.",
            color=0x2ecc71
        )
        embed.set_footer(text=f"Asdrubot v3.0 — Fase actual: {phase_label}")

        # Jugadores
        embed.add_field(
            name="👥 Jugadores",
            value="\n".join([
                "`/player list` — Ver vivos/muertos",
                "`/player register @user [nombre]` *(admin)*",
                "`/player unregister @user` *(admin)*",
                "`/player rename @user <nombre>` *(admin)*",
                "`/player alias_show @user`",
                "`/player alias_add/del` *(admin)*",
            ]),
            inline=False
        )

        # Acciones (Fundamental)
        embed.add_field(
            name="⚡ Acciones y Votos",
            value="\n".join([
                "`/vote cast @user` — Votar para linchar (Día)",
                "`/vote clear` — Retirar voto",
                "`/vote mine` — Ver mi voto actual",
                "`/act @target [nota]` — Usar habilidad de rol (Noche/Día)",
                "`/end_day` — Solicitar terminar el día (requiere mayoría)",
            ]),
            inline=False
        )

        # Fases (admin)
        if is_admin:
            embed.add_field(
                name="🌞 Fases (Admin)",
                value="\n".join([
                    "`/start_day [tiempo]`",
                    "`/end_day` *(admin force)*",
                    "`/start_night [tiempo]`",
                    "`/end_night` *(admin force)*",
                ]),
                inline=False
            )

        # Game (admin)
        if is_admin:
            embed.add_field(
                name="🎮 Partida (Admin)",
                value="\n".join([
                    "`/game_start [perfil]`",
                    "`/game_reset`",
                    "`/finish_game [razón]`",
                    "`/who [@user]` — Ver rol real",
                    "`/assign @user <rol>`",
                    "`/effects apply/remove` — Gestionar estados",
                ]),
                inline=False
            )

        # Moderation (admin/mod)
        if is_admin or can_purge:
            embed.add_field(
                name="🛡️ Moderación",
                value="\n".join([
                    "`/bc <texto>` — Anuncio oficial *(admin)*",
                    "`/set_day_channel` / `/set_log_channel`",
                    "`/show_channels`",
                    "`/purge N` *(borrar mensajes)*",
                ]),
                inline=False
            )

        # Utilities (everyone)
        embed.add_field(
            name="🎲 Utilidades",
            value="`/dice [caras]`, `/coin`, `/lynch @user`",
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot): await bot.add_cog(HelpCog(bot))

