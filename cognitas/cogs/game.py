import discord
from discord import app_commands
from discord.ext import commands
from ..core import game as game_core

class GameCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="game_start", description="Iniciar partida con profile (admin)")
    @app_commands.describe(profile="default | smt | ...")
    @app_commands.default_permissions(administrator=True)
    async def game_start(self, interaction: discord.Interaction, profile: str = "default"):
        ctx = await commands.Context.from_interaction(interaction)
        await game_core.start(ctx, profile=profile, day_channel=interaction.channel, admin_channel=None)
        
    @app_commands.command(name="game_reset", description="Hard reset of game state")
    @app_commands.default_permissions(administrator=True)
    async def game_reset(self, interaction: discord.Interaction):
        await game_core.hard_reset(interaction)

    @app_commands.command(name="finish_game", description="Terminar partida (admin)")
    @app_commands.default_permissions(administrator=True)
    async def finish_game(self, interaction: discord.Interaction, reason: str | None = None):
        ctx = await commands.Context.from_interaction(interaction)
        await game_core.finish(ctx, reason=reason)
        
    @app_commands.command(name="who", description="Info de jugador (admin)")
    @app_commands.default_permissions(administrator=True)
    async def who(self, interaction: discord.Interaction, member: discord.Member | None = None):
        ctx = await commands.Context.from_interaction(interaction)
        await game_core.who(ctx, member)
        
    @app_commands.command(name="assign", description="Asignar rol a jugador (admin)")
    @app_commands.default_permissions(administrator=True)
    async def assign(self, interaction: discord.Interaction, member: discord.Member, role_name: str):
        ctx = await commands.Context.from_interaction(interaction)
        await game_core.assign_role(ctx, member, role_name)
        
async def setup(bot): await bot.add_cog(GameCog(bot))

