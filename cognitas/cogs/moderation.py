import discord
import asyncio
from discord import app_commands
from discord.ext import commands
from ..core.state import game
from ..core.game import set_channels
from ..core.logs import set_log_channel as set_log_channel_core

from ..core.storage import save_state
from ..core.game import _load_expansion_for
from typing import Literal
from .. import config as cfg

class ModerationCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="bc", description="Broadcast to the Day channel (admin)")
    @app_commands.default_permissions(administrator=True)
    async def bc(self, interaction: discord.Interaction, text: str):
        if not game.day_channel_id:
            return await interaction.response.send_message("No Day channel configured.", ephemeral=True)
        chan = interaction.guild.get_channel(game.day_channel_id)
        if not chan:
            return await interaction.response.send_message("Day channel not found.", ephemeral=True)
        await chan.send(text)
        await interaction.response.send_message("✅ Broadcast sent.", ephemeral=True)

    @app_commands.command(name="set_channels", description="Bind Day/Night/Admin channels for the game.")
    @app_commands.describe(
        day="Day channel",
        night="Night channel",
        admin="Admin control channel",
    )
    @app_commands.default_permissions(administrator=True)
    async def set_channels_cmd(
        self,
        interaction: discord.Interaction,
        day: discord.TextChannel | None = None,
        night: discord.TextChannel | None = None,
        admin: discord.TextChannel | None = None,
    ):
        await set_channels(day or interaction.channel, night, admin)
        await interaction.response.send_message("✅ Channels configured.", ephemeral=True)

    @app_commands.command(name="set_log_channel", description="Set the logs channel.")
    @app_commands.describe(channel="Logs channel (defaults to current if omitted).")
    @app_commands.default_permissions(administrator=True)
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        target = channel or interaction.channel
        await set_log_channel_core(target)
        await interaction.response.send_message(f"🧾 Logs channel set to {target.mention}", ephemeral=True)

    # ------------------------------
    # Admin: expansion & phase tools
    # ------------------------------
    @app_commands.command(name="set_expansion", description="Set the active expansion (preferably before starting).")
    @app_commands.describe(
        profile="Profile name, e.g. 'default' or 'smt'.",
        force="Allow switching after game start (dangerous)."
    )
    @app_commands.default_permissions(administrator=True)
    async def set_expansion(self, interaction: discord.Interaction, profile: str, force: bool = False):
        phase = getattr(game, "phase", "setup")
        if phase != "setup" and not force:
            return await interaction.response.send_message(
                f"⚠️ Game phase is `{phase}`. Use `force:true` to override (not recommended mid-game).",
                ephemeral=True
            )
        prof = (profile or "").strip().lower() or "default"
        try:
            exp = _load_expansion_for(prof)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Could not resolve expansion `{profile}`: {e}", ephemeral=True)
        game.profile = prof
        game.expansion = exp
        await save_state()
        await interaction.response.send_message(
            f"✅ Expansion set to **{exp.name}** (profile=`{prof}`).",
            ephemeral=True
        )

    @app_commands.command(name="set_phase", description="Force the game phase to day or night (no side-effects).")
    @app_commands.describe(phase="Target phase: 'day' or 'night'.")
    @app_commands.default_permissions(administrator=True)
    async def set_phase(self, interaction: discord.Interaction, phase: Literal["day", "night"]):
        game.phase = phase
        await save_state()
        await interaction.response.send_message(f"✅ Phase set to **{phase}** (forced).", ephemeral=True)

    @app_commands.command(name="set_day", description="Set the current Day number explicitly.")
    @app_commands.describe(number="New current day number (integer ≥ 1).")
    @app_commands.default_permissions(administrator=True)
    async def set_day(self, interaction: discord.Interaction, number: int):
        if number < 1:
            return await interaction.response.send_message("❌ Day must be ≥ 1.", ephemeral=True)
        game.current_day_number = int(number)
        await save_state()
        await interaction.response.send_message(f"✅ Current day set to **{number}**.", ephemeral=True)

    @app_commands.command(name="bump_day", description="Increment or decrement the current Day number.")
    @app_commands.describe(delta="Positive to increment, negative to decrement (e.g., -1).")
    @app_commands.default_permissions(administrator=True)
    async def bump_day(self, interaction: discord.Interaction, delta: int):
        current = int(getattr(game, "current_day_number", 1) or 1)
        new_val = current + int(delta)
        if new_val < 1:
            return await interaction.response.send_message(
                f"❌ Resulting day would be {new_val} (< 1). Aborting.", ephemeral=True
            )
        game.current_day_number = new_val
        await save_state()
        sign = f"+{delta}" if delta >= 0 else f"{delta}"
        await interaction.response.send_message(
            f"✅ Day bumped {sign} → **{new_val}**.", ephemeral=True
        )
    @app_commands.command(name="get_state", description="Show a compact snapshot of the current game state.")
    @app_commands.default_permissions(administrator=True)
    async def get_state(self, interaction: discord.Interaction):
        guild = interaction.guild
        def _m(ch_id):
            if not ch_id or not guild: return "—"
            ch = guild.get_channel(ch_id)
            return ch.mention if ch else f"(missing:{ch_id})"

        profile = getattr(game, "profile", "default")
        exp = getattr(getattr(game, "expansion", None), "name", "base")
        phase = getattr(game, "phase", "setup")
        day_no = int(getattr(game, "current_day_number", 1) or 1)

        # If expansion provides a banner, preview it without posting to public channels
        try:
            banner_preview = (game.expansion.banner_for_day(game) if getattr(game, "expansion", None) else None)
        except Exception:
            banner_preview = None

        msg = (
            f"**Profile:** `{profile}`  •  **Expansion:** `{exp}`\n"
            f"**Phase:** `{phase}`  •  **Day #:** `{day_no}`\n"
            f"**Channels:** Day={_m(getattr(game,'day_channel_id',None))}  •  "
            f"Night={_m(getattr(game,'night_channel_id',None))}  •  "
            f"Admin={_m(getattr(game,'admin_channel_id',None))}  •  "
            f"Logs={_m(getattr(game,'admin_log_channel_id',None))}\n"
            f"{('**Banner preview:** ' + str(banner_preview)) if banner_preview else ''}"
        )
        await interaction.response.send_message(msg, ephemeral=True)




    @app_commands.command(name="purge", description="Delete recent messages in this channel.")
    @app_commands.describe(
        amount="Amount of messages to consider (max 2000).",
        only_bots="If true, only delete messages sent by bots.",
        only_me="If true, only delete messages sent by me (the bot).",
        include_pins="If true, also delete pinned messages.",
        older_than_seconds="Keep messages newer than this many seconds.",
        newer_than_seconds="Keep messages older than this many seconds.",
        reason="A short note for why you are purging (for logs).",
    )
    @app_commands.default_permissions(manage_messages=True)
    async def purge(
        self,
        interaction: discord.Interaction,
        amount: int = 100,
        only_bots: bool = False,
        only_me: bool = False,
        include_pins: bool = False,
        older_than_seconds: int | None = None,
        newer_than_seconds: int | None = None,
        reason: str | None = None,
    ):
        # 1) Basic validation
        if amount < 1 or amount > 2000:
            return await interaction.response.send_message("Amount must be between 1 and 2000.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        # 2) Build checks
        def _check(msg: discord.Message) -> bool:
            if msg.type != discord.MessageType.default:
                return False
            if not include_pins and msg.pinned:
                return False
            if only_bots and not msg.author.bot:
                return False
            if only_me and msg.author.id != interaction.client.user.id:
                return False
            return True

        # 3) Time windows
        now_ts = discord.utils.utcnow().timestamp()
        min_ts = now_ts - older_than_seconds if older_than_seconds else None
        max_ts = now_ts - newer_than_seconds if newer_than_seconds else None

        # 4) Do the purge
        deleted_count = 0
        try:
            async for m in interaction.channel.history(limit=amount, oldest_first=False):
                if not _check(m):
                    continue
                created_ts = m.created_at.timestamp()
                if min_ts and created_ts > min_ts:
                    continue  # too new
                if max_ts and created_ts < max_ts:
                    continue  # too old
                # Prefer bulk delete when possible (Discord API only allows bulk for <14 days)
                if (discord.utils.utcnow() - m.created_at).total_seconds() <= (14 * 24 * 3600):
                    # Bulk delete needs a list; we collect singles if necessary
                    try:
                        await m.delete(reason=reason or "purge")
                        deleted_count += 1
                    except (discord.Forbidden, discord.HTTPException):
                        continue
                else:
                    # Too old for bulk — delete individually
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
