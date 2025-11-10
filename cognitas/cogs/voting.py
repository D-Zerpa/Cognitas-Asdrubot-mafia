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

    - First response is handled with interaction.response if not done.
    - After defer (which we do in commands), followups are used automatically.
    - Falls back to channel.send if something goes wrong.
    """
    def __init__(self, interaction: discord.Interaction):
        self._i = interaction
        self.guild: discord.Guild | None = interaction.guild
        self.bot: discord.Client = interaction.client  # type: ignore
        self.channel = interaction.channel
        self.author = interaction.user
        self.message = None  # for compatibility (some code checks existence)

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

    # Some legacy code may call ctx.send(...)
    async def send(self, content: str = None, **kwargs):
        return await self.reply(content, **kwargs)

    # Some legacy code may call ctx.reply then delete ctx.message; keep no-ops
    async def delete(self, *args, **kwargs):
        return


class VotingAdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -----------------------
    # Phase controls (admin)
    # -----------------------

    @app_commands.command(name="start_day", description="Starts day (admin)")
    @app_commands.describe(duration="Ex: 24h, 90m, 1h30m", channel="Day channel", force="Restart if a day is already active")
    @app_commands.default_permissions(administrator=True)
    async def start_day(self, interaction: discord.Interaction, duration: str = "24h", channel: discord.TextChannel | None = None, force: bool = False):
        # Defer once to avoid InteractionResponded errors
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        await phases.start_day(ctx, duration_str=duration, target_channel=channel, force=force)
        # Optional admin ack
        await interaction.followup.send("✅ Day started", ephemeral=True)

    @app_commands.command(name="end_day", description="Ends day (admin)")
    @app_commands.default_permissions(administrator=True)
    async def end_day(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        await phases.end_day(ctx)
        await interaction.followup.send("☑️ Day finished", ephemeral=True)

    @app_commands.command(name="start_night", description="Starts night (admin)")
    @app_commands.describe(duration="Ex: 12h, 8h, 45m")
    @app_commands.default_permissions(administrator=True)
    async def start_night(self, interaction: discord.Interaction, duration: str = "12h"):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        await phases.start_night(ctx, duration_str=duration)
        await interaction.followup.send("✅ Night started", ephemeral=True)

    @app_commands.command(name="end_night", description="Ends night (admin)")
    @app_commands.default_permissions(administrator=True)
    async def end_night(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        await phases.end_night(ctx)
        await interaction.followup.send("☑️ Night ended", ephemeral=True)

    # -----------------------
    # Status & votes (public)
    # -----------------------

    @app_commands.command(name="votes", description="Vote breakdown (embed)")
    async def votes(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = InteractionCtx(interaction)

        await votes_core.votes_breakdown(ctx)

    @app_commands.command(name="status", description="Day status (embed)")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = InteractionCtx(interaction)

        await votes_core.status(ctx)

    @app_commands.command(name="clearvotes", description="Clean votes(admin)")
    @app_commands.default_permissions(administrator=True)
    async def clearvotes(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        await votes_core.clearvotes(ctx)
        await interaction.followup.send("🧹 Votes cleared.", ephemeral=False)


class VoteCog(commands.GroupCog, name="vote", description="Votes"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="cast", description="Vote for a player")
    async def cast(self, interaction: discord.Interaction, member: discord.Member):
        # Defer first to avoid interaction timing issues
        await interaction.response.defer(ephemeral=False)
        ctx = InteractionCtx(interaction)

        # 1) Gate voting through the Status Engine for clear UX
        voter_uid = str(interaction.user.id)
        chk = SE.check_action(game, voter_uid, "vote")
        if not chk.get("allowed", True):
            # Map engine reason -> human-friendly message
            msg = SE.get_block_message(chk.get("reason") or "")
            return await ctx.reply(msg or "You can't vote right now.", ephemeral=True)

        # 2) Proceed with normal vote
        await votes_core.vote(ctx, member)
        return 

    @app_commands.command(name="clear", description="Unvote")
    async def clear(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        ctx = InteractionCtx(interaction)

        await votes_core.unvote(ctx)
        await interaction.followup.send("🗑️ Vote cleared.", ephemeral=False)

    @app_commands.command(name="mine", description="See your current vote")
    async def mine(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        await votes_core.myvote(ctx)
        # No extra ack; core should output your current vote.

    @app_commands.command(name="end_day", description="Ask for finish the day early (2/3 of alive players)")
    async def end_day(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        await votes_core.request_end_day(ctx)
        await interaction.followup.send("📣 Your request to end day has been registered.")


async def setup(bot: commands.Bot):
    await bot.add_cog(VotingAdminCog(bot))
    await bot.add_cog(VoteCog(bot))  # /vote …

