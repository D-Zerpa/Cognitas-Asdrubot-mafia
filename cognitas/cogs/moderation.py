import discord
from discord import app_commands
from discord.ext import commands
from ..core.state import game
from ..core.game import set_channels

class ModerationCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="bc", description="Broadcast al canal del Día (admin)")
    @app_commands.default_permissions(administrator=True)
    async def bc(self, interaction: discord.Interaction, text: str):
        if not game.day_channel_id:
            return await interaction.response.send_message("No hay canal de Día configurado.", ephemeral=True)
        chan = interaction.guild.get_channel(game.day_channel_id)
        if not chan:
            return await interaction.response.send_message("El canal de Día configurado no existe.", ephemeral=True)
        await chan.send(text)
        await interaction.response.send_message("Mensaje enviado.", ephemeral=True)

    @app_commands.command(name="set_day_channel", description="Configurar canal del Día (admin)")
    @app_commands.default_permissions(administrator=True)
    async def set_day_channel(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        target = channel or interaction.channel
        set_channels(day=target)
        await interaction.response.send_message(f"Canal de Día: {target.mention}", ephemeral=True)

    @app_commands.command(name="set_admin_channel", description="Configurar canal de Admin (admin)")
    @app_commands.default_permissions(administrator=True)
    async def set_admin_channel(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        target = channel or interaction.channel
        set_channels(admin=target)
        await interaction.response.send_message(f"Canal de Admin: {target.mention}", ephemeral=True)

    @app_commands.command(name="show_channels", description="Ver canales configurados (admin)")
    @app_commands.default_permissions(administrator=True)
    async def show_channels(self, interaction: discord.Interaction):
        day = interaction.guild.get_channel(getattr(game, "day_channel_id", None))
        adm = interaction.guild.get_channel(getattr(game, "admin_channel_id", None))
        await interaction.response.send_message(
            f"**Día**: {day.mention if day else '—'}\n**Admin**: {adm.mention if adm else '—'}",
            ephemeral=True
        )

    @app_commands.command(name="purge", description="Borrar N mensajes del canal actual (mod)")
    @app_commands.default_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: int):
        if amount <= 0:
            return await interaction.response.send_message("Número inválido.", ephemeral=True)
        try:
            await interaction.channel.purge(limit=amount)
            await interaction.response.send_message(f"Purged {amount}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("No tengo permisos.", ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message("No hay tantos mensajes para borrar.", ephemeral=True)

async def setup(bot): await bot.add_cog(ModerationCog(bot))
