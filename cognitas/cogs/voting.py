# cognitas/cogs/voting.py
import discord
from discord import app_commands
from discord.ext import commands
from ..core import phases, votes as votes_core

class VotingCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    # ------- Fases -------
    @app_commands.command(name="start_day", description="Inicia el Día (admin)")
    @app_commands.describe(duration="Ej: 24h, 90m, 1h30m", channel="Canal de Día", force="Reinicia si ya hay un día activo")
    @app_commands.default_permissions(administrator=True)
    async def start_day(self, interaction: discord.Interaction, duration: str = "24h", channel: discord.TextChannel | None = None, force: bool = False):
        ctx = await commands.Context.from_interaction(interaction)
        await phases.start_day(ctx, duration_str=duration, target_channel=channel, force=force)
        await interaction.response.defer(ephemeral=True)  # ya respondimos vía ctx.reply

    @app_commands.command(name="end_day", description="Termina el Día (admin)")
    @app_commands.default_permissions(administrator=True)
    async def end_day(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await phases.end_day(ctx)
        await interaction.response.defer(ephemeral=True)

    @app_commands.command(name="start_night", description="Inicia la Noche (admin)")
    @app_commands.describe(duration="Ej: 12h, 8h, 45m")
    @app_commands.default_permissions(administrator=True)
    async def start_night(self, interaction: discord.Interaction, duration: str = "12h"):
        ctx = await commands.Context.from_interaction(interaction)
        await phases.start_night(ctx, duration_str=duration)
        await interaction.response.defer(ephemeral=True)

    @app_commands.command(name="end_night", description="Termina la Noche (admin)")
    @app_commands.default_permissions(administrator=True)
    async def end_night(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await phases.end_night(ctx)
        await interaction.response.defer(ephemeral=True)

    # ------- Votos -------
    vote_group = app_commands.Group(name="vote", description="Votaciones")

    @vote_group.command(name="cast", description="Votar a un jugador")
    async def vote_cast(self, interaction: discord.Interaction, member: discord.Member):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.vote(ctx, member)
        await interaction.response.defer(ephemeral=True)

    @vote_group.command(name="clear", description="Quitar tu voto")
    async def vote_clear(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.unvote(ctx)
        await interaction.response.defer(ephemeral=True)

    @vote_group.command(name="mine", description="Ver tu voto actual")
    async def vote_mine(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.myvote(ctx)
        await interaction.response.defer(ephemeral=True)

    @app_commands.command(name="votos", description="Resumen de votaciones en curso")
    async def votos(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.votes_breakdown(ctx)
        await interaction.response.defer(ephemeral=True)

    @app_commands.command(name="status", description="Estado del Día")
    async def status(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.status(ctx)
        await interaction.response.defer(ephemeral=True)

    @app_commands.command(name="clearvotes", description="Limpiar todas las votaciones (admin)")
    @app_commands.default_permissions(administrator=True)
    async def clearvotes(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.clearvotes(ctx)
        await interaction.response.defer(ephemeral=True)

    @vote_group.command(name="end_day", description="Pedir terminar el Día sin linchamiento (2/3 de vivos)")
    async def vote_end_day(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.request_end_day(ctx)
        await interaction.response.defer(ephemeral=True)

async def setup(bot: commands.Bot):
    cog = VotingCog(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(cog.vote_group)
