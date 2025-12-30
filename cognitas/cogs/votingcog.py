from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..core import phases, votes as votes_core
from ..status import engine as SE
from ..core.state import game


# --- Adapter to bridge slash Interaction <-> legacy ctx-style calls ---
class InteractionCtx:
    """
    Minimal context adapter so core functions that expect a 'ctx' with
    .reply(), .send(), .guild, .bot, .channel, .author keep working.
    """
    def __init__(self, interaction: discord.Interaction):
        self._i = interaction
        self.guild: discord.Guild | None = interaction.guild
        self.bot: discord.Client = interaction.client  # type: ignore
        self.channel = interaction.channel
        self.author = interaction.user
        self.message = None

    async def reply(self, content: str = None, **kwargs):
        # Prefer followup if we've already responded or deferred
        try:
            if self._i.response.is_done():
                return await self._i.followup.send(content or "\u200b", **kwargs)
            else:
                return await self._i.response.send_message(content or "\u200b", **kwargs)
        except Exception:
            # Fallback to channel send
            try:
                if self.channel:
                    return await self.channel.send(content or "\u200b", **kwargs)
            except Exception:
                pass

    async def send(self, content: str = None, **kwargs):
        return await self.reply(content, **kwargs)

    async def delete(self, *args, **kwargs):
        return


class VotingAdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -----------------------
    # Phase controls (admin)
    # -----------------------

    @app_commands.command(name="start_day", description="Iniciar el Día (Admin)")
    @app_commands.describe(
        duration="Duración (ej: 24h, 90m)", 
        channel="Canal donde ocurrirá el día", 
        force="Forzar reinicio si ya hay un día activo"
    )
    @app_commands.default_permissions(administrator=True)
    async def start_day(self, interaction: discord.Interaction, duration: str = "24h", channel: discord.TextChannel | None = None, force: bool = False):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        # Core handles announcements and logic
        await phases.start_day(ctx, duration_str=duration, target_channel=channel, force=force)

    @app_commands.command(name="end_day", description="Terminar el Día manualmente (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def end_day(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await phases.end_day(ctx)

    @app_commands.command(name="start_night", description="Iniciar la Noche (Admin)")
    @app_commands.describe(duration="Duración (ej: 12h, 8h)")
    @app_commands.default_permissions(administrator=True)
    async def start_night(self, interaction: discord.Interaction, duration: str = "12h"):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await phases.start_night(ctx, duration_str=duration)

    @app_commands.command(name="end_night", description="Terminar la Noche manualmente (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def end_night(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await phases.end_night(ctx)

    # -----------------------
    # Status & votes (public)
    # -----------------------

    @app_commands.command(name="votes", description="Ver recuento de votos detallado (Embed)")
    async def votes(self, interaction: discord.Interaction):
        await interaction.response.defer() 
        ctx = InteractionCtx(interaction)
        await votes_core.votes_breakdown(ctx)

    @app_commands.command(name="status", description="Ver estado actual de la partida")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer() 
        ctx = InteractionCtx(interaction)
        await votes_core.status(ctx)

    @app_commands.command(name="clearvotes", description="Limpiar todos los votos (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def clearvotes(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await votes_core.clearvotes(ctx)


class VoteCog(commands.GroupCog, name="vote", description="Sistema de Votación"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="cast", description="Votar para linchar a un jugador")
    @app_commands.describe(member="Jugador objetivo")
    async def cast(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=False)
        ctx = InteractionCtx(interaction)

        await votes_core.vote(ctx, member)

    @app_commands.command(name="clear", description="Retirar tu voto actual")
    async def clear(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await votes_core.unvote(ctx)

    @app_commands.command(name="mine", description="Ver por quién has votado")
    async def mine(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await votes_core.myvote(ctx)

    @app_commands.command(name="end_day", description="Solicitar terminar el día (Solo Día 1).")
    async def end_day(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await votes_core.request_end_day(ctx)


async def setup(bot: commands.Bot):
    await bot.add_cog(VotingAdminCog(bot))
    await bot.add_cog(VoteCog(bot))

