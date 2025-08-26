import discord
from discord import app_commands
from discord.ext import commands
from ..core import phases, votes as votes_core
from ..core.logs import log_event

class VotingAdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Fases (comandos sueltos)
    @app_commands.command(name="start_day", description="Starts day (admin)")
    @app_commands.describe(duration="Ej: 24h, 90m, 1h30m", channel="Canal de Día", force="Reinicia si ya hay un día activo")
    @app_commands.default_permissions(administrator=True)
    async def start_day(self, interaction: discord.Interaction, duration: str = "24h", channel: discord.TextChannel | None = None, force: bool = False):
        ctx = await commands.Context.from_interaction(interaction)
        await phases.start_day(ctx, duration_str=duration, target_channel=channel, force=force)
        await interaction.response.send_message("Day started", ephemeral=True)

    @app_commands.command(name="end_day", description="Ends day (admin)")
    @app_commands.default_permissions(administrator=True)
    async def end_day(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await phases.end_day(ctx)
        await interaction.response.send_message("Day finished", ephemeral=True)

    @app_commands.command(name="start_night", description="Starts night (admin)")
    @app_commands.describe(duration="Ej: 12h, 8h, 45m")
    @app_commands.default_permissions(administrator=True)
    async def start_night(self, interaction: discord.Interaction, duration: str = "12h"):
        ctx = await commands.Context.from_interaction(interaction)
        await phases.start_night(ctx, duration_str=duration)
        await interaction.response.send_message("Night started", ephemeral=True)

    @app_commands.command(name="end_night", description="Ends night (admin)")
    @app_commands.default_permissions(administrator=True)
    async def end_night(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await phases.end_night(ctx)
        await interaction.response.send_message("Night Ended", ephemeral=True)

    @app_commands.command(name="votes", description="Vote breakdown (embed)")
    async def votos(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.votes_breakdown(ctx)

    @app_commands.command(name="status", description="Day status (embed)")
    async def status(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.status(ctx)

    @app_commands.command(name="clearvotes", description="Clean votes(admin)")
    @app_commands.default_permissions(administrator=True)
    async def clearvotes(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.clearvotes(ctx)
        await interaction.response.send_message("Votes cleaned.", ephemeral=True)


class VoteCog(commands.GroupCog, name="vote", description="Votes"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="cast", description="Vote for a player")
    async def cast(self, interaction: discord.Interaction, member: discord.Member):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.vote(ctx, member)
        await interaction.response.send_message("Vote registered.", ephemeral=True)

    @app_commands.command(name="clear", description="Unvote")
    async def clear(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.unvote(ctx)
        await interaction.response.send_message("Unvoted.", ephemeral=True)

    @app_commands.command(name="mine", description="See your current vote")
    async def mine(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.myvote(ctx)
        await interaction.response.send_message("This is your vote.", ephemeral=True)

    @app_commands.command(name="end_day", description="Ask for finish the day early (2/3 of alive players)")
    async def end_day(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await votes_core.request_end_day(ctx)
        await interaction.response.send_message("Early finish pettition sent.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(VotingAdminCog(bot))
    await bot.add_cog(VoteCog(bot))  # /vote …
