import discord
from discord import app_commands
from discord.ext import commands
from ..core import game as game_core
from .. import config as cfg

class GameCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="game_start", description="Iniciar una nueva partida (Configuración manual).") 
    @app_commands.describe(
        profile="Perfil de roles (default, smt, p3, etc.)", 
        alive_role="(Opcional) Rol de 'Vivos' existente para vincular", 
        dead_role="(Opcional) Rol de 'Muertos' existente para vincular" 
    )
    @app_commands.default_permissions(administrator=True)
    async def game_start(
        self, 
        interaction: discord.Interaction, 
        profile: str | None = None,
        alive_role: discord.Role | None = None,
        dead_role: discord.Role | None = None):

        ctx = await commands.Context.from_interaction(interaction)
        # Core handles the logic and replies
        await game_core.start(
            ctx, 
            profile=(profile or cfg.DEFAULT_PROFILE), 
            game_channel=interaction.channel, 
            admin_channel=None,
            alive_role_id=alive_role.id if alive_role else None,
            dead_role_id=dead_role.id if dead_role else None)
        
    @app_commands.command(name="game_reset", description="Reinicio forzado del estado de la partida.") 
    @app_commands.default_permissions(administrator=True)
    async def game_reset(self, interaction: discord.Interaction):
        await game_core.hard_reset(interaction)

    @app_commands.command(name="finish_game", description="Terminar la partida actual (admin).") 
    @app_commands.default_permissions(administrator=True)
    async def finish_game(self, interaction: discord.Interaction, reason: str | None = None):
        ctx = await commands.Context.from_interaction(interaction)
        await game_core.finish(ctx, reason=reason)
        
    @app_commands.command(name="who", description="Ver información interna de un jugador (admin).") 
    @app_commands.default_permissions(administrator=True)
    async def who(self, interaction: discord.Interaction, member: discord.Member | None = None):
        ctx = await commands.Context.from_interaction(interaction)
        await game_core.who(ctx, member)
        
    @app_commands.command(name="assign", description="Asignar rol manualmente a un jugador (admin).") 
    @app_commands.default_permissions(administrator=True)
    async def assign(self, interaction: discord.Interaction, member: discord.Member, role_name: str):
        ctx = await commands.Context.from_interaction(interaction)
        await game_core.assign_role(ctx, member, role_name)

async def setup(bot: commands.Bot):
    await bot.add_cog(GameCog(bot))

