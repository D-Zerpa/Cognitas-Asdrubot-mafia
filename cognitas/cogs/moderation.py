import discord
from discord import app_commands
from discord.ext import commands
from ..core.state import game
from ..core.game import set_channels
from ..core.logs import set_log_channel as set_log_channel_core

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

    @app_commands.command(name="set_log_channel", description="Set logs channel (admin)")
    @app_commands.default_permissions(administrator=True)
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        target = channel or interaction.channel
        set_log_channel_core(target)
        await interaction.response.send_message(f"🧾 Logs channel set to {target.mention}", ephemeral=True)

    @app_commands.command(name="purge", description="Delete recent messages in this channel.")
    @app_commands.describe(
        limit="How many messages to scan (max 1000)",
        user="Only delete messages from this user",
        contains="Only delete messages containing this text",
        include_bots="Also delete messages from bots",
        include_pinned="Also delete pinned messages (careful!)",
    )
    @app_commands.default_permissions(manage_messages=True)
    async def purge(
        self,
        interaction: discord.Interaction,
        limit: int = 100,
        user: discord.Member | None = None,
        contains: str | None = None,
        include_bots: bool = False,
        include_pinned: bool = False,
    ):
        # 1) Always defer first — prevents "Unknown interaction"
        await interaction.response.defer(ephemeral=True)

        chan = interaction.channel
        if not isinstance(chan, (discord.TextChannel, discord.Thread)):
            return await interaction.followup.send("This command only works in text channels or threads.", ephemeral=True)

        # 2) Permission checks (bot must have Manage Messages)
        me = chan.guild.me if isinstance(chan, discord.TextChannel) else interaction.guild.me  # type: ignore
        perms = chan.permissions_for(me)
        if not perms.manage_messages:
            return await interaction.followup.send("I need **Manage Messages** permission in this channel.", ephemeral=True)

        # 3) Clamp limit
        limit = max(1, min(1000, int(limit)))

        # 4) Build predicate
        needle = (contains or "").lower().strip()

        def _check(m: discord.Message) -> bool:
            if (not include_bots) and m.author.bot:
                return False
            if (not include_pinned) and m.pinned:
                return False
            if user and m.author.id != user.id:
                return False
            if needle and needle not in (m.content or "").lower():
                return False
            return True

        # 5) Try fast path: channel.purge (uses bulk delete when possible)
        deleted_count = 0
        try:
            deleted = await chan.purge(
                limit=limit,
                check=_check,
                bulk=True,
                reason=f"/purge by {interaction.user} ({interaction.user.id})",
            )
            deleted_count = len(deleted)
        except AttributeError:
            # Threads on some versions may not expose purge(); fallback to manual
            pass
        except discord.Forbidden:
            return await interaction.followup.send("I don’t have permission to delete messages here.", ephemeral=True)
        except discord.HTTPException:
            # Some messages older than 14 days cannot be bulk-deleted; fall back to manual
            pass

        if deleted_count == 0:
            # Manual fallback (handles >14d messages or missing purge())
            try:
                async for m in chan.history(limit=limit):
                    if _check(m):
                        try:
                            await m.delete()
                            deleted_count += 1
                            # Be polite with rate limits if many single deletes
                            await asyncio.sleep(0.2)
                        except (discord.Forbidden, discord.HTTPException):
                            continue
            except Exception as e:
                return await interaction.followup.send(f"Failed to fetch history: {e}", ephemeral=True)

        # 6) Single, safe follow-up (no double replies)
        await interaction.followup.send(f"🧹 Purged **{deleted_count}** message(s).", ephemeral=True)

async def setup(bot): await bot.add_cog(ModerationCog(bot))
