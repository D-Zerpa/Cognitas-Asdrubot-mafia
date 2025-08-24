import discord
from discord import app_commands
from discord.ext import commands
from ..core import players as players_core

class PlayersCog(commands.GroupCog, name="player", description="Gestionar jugadores"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="list", description="Ver jugadores vivos y muertos")
    async def list_cmd(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.list_players(ctx)

    @app_commands.command(name="register", description="Registrar jugador (admin)")
    @app_commands.describe(member="Jugador a registrar", name="Nombre opcional")
    @app_commands.default_permissions(administrator=True)
    async def register_cmd(self, interaction: discord.Interaction, member: discord.Member | None = None, name: str | None = None):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.register(ctx, member, name=name)

    @app_commands.command(name="unregister", description="Dar de baja (admin)")
    @app_commands.default_permissions(administrator=True)
    async def unregister_cmd(self, interaction: discord.Interaction, member: discord.Member):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.unregister(ctx, member)

    @app_commands.command(name="rename", description="Renombrar jugador (admin)")
    @app_commands.default_permissions(administrator=True)
    async def rename_cmd(self, interaction: discord.Interaction, member: discord.Member, new_name: str):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.rename(ctx, member, new_name=new_name)

    # Subgrupo /player alias …
    @app_commands.command(name="alias_show", description="Ver alias de un jugador")
    async def alias_show_cmd(self, interaction: discord.Interaction, member: discord.Member):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.alias_show(ctx, member)

    @app_commands.command(name="alias_add", description="Añadir alias (admin)")
    @app_commands.default_permissions(administrator=True)
    async def alias_add_cmd(self, interaction: discord.Interaction, member: discord.Member, alias: str):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.alias_add(ctx, member, alias=alias)

    @app_commands.command(name="alias_del", description="Eliminar alias (admin)")
    @app_commands.default_permissions(administrator=True)
    async def alias_del_cmd(self, interaction: discord.Interaction, member: discord.Member, alias: str):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.alias_del(ctx, member, alias=alias)

async def setup(bot: commands.Bot):
    await bot.add_cog(PlayersCog(bot))

