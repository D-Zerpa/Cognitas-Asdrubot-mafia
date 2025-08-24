# cognitas/cogs/players.py
import discord
from discord import app_commands
from discord.ext import commands
from ..core import players as players_core

class PlayersCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    group = app_commands.Group(name="player", description="Gestionar jugadores")

    @group.command(name="list", description="Ver jugadores vivos y muertos")
    async def list_cmd(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.list_players(ctx)

    @group.command(name="register", description="Registrar jugador (admin)")
    @app_commands.describe(member="Jugador a registrar", name="Nombre opcional")
    @app_commands.default_permissions(administrator=True)
    async def register_cmd(self, interaction: discord.Interaction, member: discord.Member = None, name: str | None = None):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.register(ctx, member, name=name)

    @group.command(name="unregister", description="Dar de baja (admin)")
    @app_commands.default_permissions(administrator=True)
    async def unregister_cmd(self, interaction: discord.Interaction, member: discord.Member):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.unregister(ctx, member)

    @group.command(name="rename", description="Renombrar jugador (admin)")
    @app_commands.default_permissions(administrator=True)
    async def rename_cmd(self, interaction: discord.Interaction, member: discord.Member, new_name: str):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.rename(ctx, member, new_name=new_name)

    # ----- alias subgrupo -----
    alias_group = app_commands.Group(name="alias", description="Gestionar alias", parent=group)

    @alias_group.command(name="show", description="Ver alias de un jugador")
    async def alias_show_cmd(self, interaction: discord.Interaction, member: discord.Member):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.alias_show(ctx, member)

    @alias_group.command(name="add", description="Añadir alias (admin)")
    @app_commands.default_permissions(administrator=True)
    async def alias_add_cmd(self, interaction: discord.Interaction, member: discord.Member, alias: str):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.alias_add(ctx, member, alias=alias)

    @alias_group.command(name="del", description="Eliminar alias (admin)")
    @app_commands.default_permissions(administrator=True)
    async def alias_del_cmd(self, interaction: discord.Interaction, member: discord.Member, alias: str):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.alias_del(ctx, member, alias=alias)

async def setup(bot: commands.Bot):
    cog = PlayersCog(bot)
    await bot.add_cog(cog)
    # Registrar el grupo en el árbol (recomendado cuando usas app_commands.Group en Cogs)
    bot.tree.add_command(cog.group)
    bot.tree.add_command(cog.alias_group)
