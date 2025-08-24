import discord
from discord import app_commands
from discord.ext import commands
from ..core import phases, votes as votes_core

class VotingAdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Fases (comandos sueltos)
    @app_commands.command(name="start_day", description="Inicia el Día (admin)")
    @app_commands.describe(duration="Ej: 24h, 90m, 1h30m", channel="Canal de Día", force="Reinicia si ya hay un día activo")
    @app_commands.default_permissions(administrator=True)
    async def start_day(self, interaction: discord.Interaction, duration: str = "24h", channel: discord.TextChannel | None = None, force: bool = False):
        ctx = await commands.Context.from_interaction(interaction)
        await phases.start_day(ctx, duration_str=duration, target_channel=channel, force=force)
        await interaction.response.send_message("Día iniciado.", ephemeral=True)

    @app_commands.command(name="end_day", description="Termina el Día (admin)")
    @app_commands.default_permissions(administrator=True)
    async def end_day(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await phases.end_day(ctx)
        await interaction.response.send_message("Día terminado.", ephemeral=True)

    @app_commands.command(name="start_night", description="Inicia la Noche (admin)")
    @app_commands.describe(duration="Ej: 12h, 8h, 45m")
    @app_commands.default_permissions(administrator=True)
    async def start_night(self, interaction: discord.Interaction, duration: str = "12h"):
        ctx = await commands.Context.from_interaction(interaction)
        await phases.start_night(ctx, duration_str=duration)
        await interaction.response.send_message("Noche iniciada.", ephemeral=True)

    @app_commands.command(name="end_night", description="Termina la Noche (admin)")
    @app_commands.default_permissions(administrator=True)
    async def end_night(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await phases.end_night(ctx)
        await interaction.response.send_message("Noche terminada.", ephemeral=True)

    @app_commands.command(name="votos", description="Resumen de votaciones")
    async def votos(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.votes_breakdown(ctx)
        await interaction.response.send_message("Mostrando votos…", ephemeral=True)

    @app_commands.command(name="status", description="Estado del Día")
    async def status(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.status(ctx)
        await interaction.response.send_message("Estado enviado.", ephemeral=True)

    @app_commands.command(name="clearvotes", description="Limpiar todas las votaciones (admin)")
    @app_commands.default_permissions(administrator=True)
    async def clearvotes(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.clearvotes(ctx)
        await interaction.response.send_message("Votos limpiados.", ephemeral=True)


class VoteCog(commands.GroupCog, name="vote", description="Votaciones"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="cast", description="Votar a un jugador")
    async def cast(self, interaction: discord.Interaction, member: discord.Member):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.vote(ctx, member)
        await interaction.response.send_message("Voto registrado.", ephemeral=True)

    @app_commands.command(name="clear", description="Quitar tu voto")
    async def clear(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.unvote(ctx)
        await interaction.response.send_message("Voto quitado.", ephemeral=True)

    @app_commands.command(name="mine", description="Ver tu voto actual")
    async def mine(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.myvote(ctx)
        await interaction.response.send_message("Tu voto actual fue enviado.", ephemeral=True)

    @app_commands.command(name="end_day", description="Pedir terminar el Día sin linchamiento (2/3 de vivos)")
    async def end_day(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.request_end_day(ctx)
        await interaction.response.send_message("Solicitud registrada.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(VotingAdminCog(bot))
    await bot.add_cog(VoteCog(bot))  # /vote …
