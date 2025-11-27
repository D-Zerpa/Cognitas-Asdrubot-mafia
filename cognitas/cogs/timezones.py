from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

# Prefer Python's stdlib zoneinfo (py3.9+). Fall back to pytz if needed.
try:
    from zoneinfo import ZoneInfo  # type: ignore
    _HAS_ZONEINFO = True
except Exception:  # pragma: no cover
    _HAS_ZONEINFO = False
    import pytz  # type: ignore

# Persist using your existing storage
from ..core.state import game
from ..core.storage import save_state

import logging
log = logging.getLogger(__name__)


# -----------------------------
# Data model (persisted in state)
# -----------------------------
@dataclass
class TZEntry:
    channel_id: int                # Voice channel to rename
    tz: str                        # IANA tz like "Europe/Madrid"
    label: str                     # Short name shown in the channel
    fmt: str = "{HH}:{MM} {abbr}"  # Formatting template

@dataclass
class GuildTZConfig:
    enabled: bool = True
    interval_minutes: int = 10
    entries: List[TZEntry] = None  # filled at runtime

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "interval_minutes": self.interval_minutes,
            "entries": [asdict(e) for e in (self.entries or [])],
        }

    @staticmethod
    def from_dict(d: dict) -> "GuildTZConfig":
        if not d:
            return GuildTZConfig(enabled=True, interval_minutes=10, entries=[])
        return GuildTZConfig(
            enabled=bool(d.get("enabled", True)),
            interval_minutes=int(d.get("interval_minutes", 10) or 10),
            entries=[TZEntry(**x) for x in d.get("entries", [])],
        )


# -----------------------------
# Helpers
# -----------------------------
def _state_get_all() -> Dict[str, dict]:
    """Fetch root dict for tzclocks from game state."""
    root = getattr(game, "tzclocks", None)
    if not isinstance(root, dict):
        root = {}
        game.tzclocks = root
    return root

def _state_get_guild(guild_id: int) -> GuildTZConfig:
    root = _state_get_all()
    raw = root.get(str(guild_id), {})
    return GuildTZConfig.from_dict(raw)

def _state_save_guild(guild_id: int, cfg: GuildTZConfig) -> None:
    root = _state_get_all()
    root[str(guild_id)] = cfg.to_dict()

async def _persist():
    try:
        await save_state()
    except Exception:
        pass

def _now_in_tz(tzname: str) -> datetime:
    if _HAS_ZONEINFO:
        try:
            tz = ZoneInfo(tzname)
        except Exception:
            tz = ZoneInfo("UTC")
        return datetime.now(tz)
    else:  # pytz fallback
        try:
            tz = pytz.timezone(tzname)
        except Exception:
            tz = pytz.UTC
        return datetime.now(tz)

def _is_valid_tz(tzname: str) -> bool:
    if _HAS_ZONEINFO:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(tzname)
            return True
        except ZoneInfoNotFoundError:
            return False
    else:
        import pytz
        try:
            pytz.timezone(tzname)
            return True
        except pytz.UnknownTimeZoneError:
            return False

def _format_time(dt: datetime, fmt: str) -> str:
    # tokens: {HH} 24h, {MM} zero-padded, {abbr} TZ short name
    HH = f"{dt.hour:02d}"
    MM = f"{dt.minute:02d}"
    try:
        abbr = dt.tzname() or ""
    except Exception:
        abbr = ""
    return fmt.replace("{HH}", HH).replace("{MM}", MM).replace("{abbr}", abbr).strip()


# -----------------------------
# Cog
# -----------------------------
class TimezonesCog(commands.Cog, name="Timezones"):
    """
    Periodically renames selected voice channels to show the current time in given timezones.
    Safe by default: only updates when the name actually changes (reduces rate-limit pressure).
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # A single background loop handles all guilds
        self._loop_task: Optional[asyncio.Task] = None
        self._loop_running = False

    # ------------- Lifecycle -------------
    async def cog_load(self):
        # Start loop once the cog is loaded
        if not self._loop_running:
            self._loop_running = True
            self._loop_task = asyncio.create_task(self._main_loop(), name="tzclocks_loop")

    async def cog_unload(self):
        # Stop loop gracefully
        self._loop_running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except Exception:
                pass

    # ------------- Background Loop -------------
    async def _main_loop(self):
        """
        A dynamic loop: checks min interval across all guild configs, sleeps that much,
        then applies updates. This keeps changes reasonably frequent without spamming.
        """
        # Initial small delay to let the bot fully connect
        await asyncio.sleep(5)

        while self._loop_running:
            try:
                min_interval = self._compute_min_interval()  # in minutes
                await self._tick_all_guilds()
            except Exception:
                # Never crash the loop
                pass

            # Sleep with a sane default if nothing configured
            sleep_min = min_interval if min_interval > 0 else 10
            await asyncio.sleep(sleep_min * 60)

    def _compute_min_interval(self) -> int:
        root = _state_get_all()
        if not root:
            return 10
        mins = []
        for raw in root.values():
            try:
                mins.append(int(raw.get("interval_minutes", 10) or 10))
            except Exception:
                continue
        return min(mins) if mins else 10

    async def _tick_all_guilds(self):
        for guild in list(self.bot.guilds):
            cfg = _state_get_guild(guild.id)
            if not cfg.enabled or not cfg.entries:
                continue
            await self._update_guild(guild, cfg)

    async def _update_guild(self, guild: discord.Guild, cfg: GuildTZConfig):
        if not guild.me.guild_permissions.manage_channels:
            return

        for entry in list(cfg.entries or []):
            ch = guild.get_channel(entry.channel_id)
            if not isinstance(ch, discord.VoiceChannel):
                continue

            now_dt = _now_in_tz(entry.tz)
            time_str = _format_time(now_dt, entry.fmt)
            new_name = f"{entry.label}: {time_str}"

            if ch.name != new_name:
                try:
                    await ch.edit(name=new_name, reason="Timezone clock update")
                    log.info(f"[timezones] Updated {ch.id} to '{new_name}'")
                    # IMPORTANT: Sleep to prevent rate limit (Discord allows ~2 renames per 10 min per channel, 
                    # but hitting many channels at once can trigger global limits).
                    await asyncio.sleep(1.5) 
                except (discord.Forbidden, discord.HTTPException) as e:
                    log.warning(f"[timezones] Failed to update {ch.id}: {e}")
                    continue

    # ------------- Commands -------------
    # Group under /tz for cleanliness
    tz = app_commands.Group(name="tz", description="Timezone clock tools")

    @tz.command(name="add", description="Add a timezone clock on a voice channel.")
    @app_commands.describe(
        channel="Voice channel to rename periodically",
        tz="IANA timezone, e.g., 'Europe/Madrid', 'America/New_York'",
        label="Short label to show (e.g., 'Madrid', 'NYC')",
        fmt="Optional format: tokens {HH} {MM} {abbr}. Default: '{HH}:{MM} {abbr}'"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def tz_add(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        tz: str,
        label: str,
        fmt: Optional[str] = None,
    ):


        if not _is_valid_tz(tz):
            return await interaction.response.send_message(
                f"❌ Unknown timezone `{tz}`. Use IANA format (e.g. `Europe/Madrid`).", 
                ephemeral=True)

        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Guild context required.", ephemeral=True)

        cfg = _state_get_guild(guild.id)
        if cfg.entries is None:
            cfg.entries = []

        # Prevent duplicates for the same channel
        for e in cfg.entries:
            if e.channel_id == channel.id:
                return await interaction.response.send_message(
                    "This channel already has a timezone clock configured. Use `/tz edit` or `/tz remove`.",
                    ephemeral=True
                )

        cfg.entries.append(TZEntry(channel_id=channel.id, tz=tz, label=label, fmt=fmt or "{HH}:{MM} {abbr}"))
        _state_save_guild(guild.id, cfg)
        await _persist()
        asyncio.create_task(self._update_guild(guild, cfg))
        await interaction.response.send_message(
            f"✅ Added TZ clock on {channel.mention}: `{label}` @ `{tz}`.", ephemeral=True
        )

    @tz.command(name="remove", description="Remove a timezone clock from a voice channel.")
    @app_commands.describe(channel="Voice channel previously configured for TZ clock")
    @app_commands.default_permissions(manage_guild=True)
    async def tz_remove(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Guild context required.", ephemeral=True)

        cfg = _state_get_guild(guild.id)
        before = len(cfg.entries or [])
        cfg.entries = [e for e in (cfg.entries or []) if e.channel_id != channel.id]
        _state_save_guild(guild.id, cfg)
        await _persist()

        asyncio.create_task(self._update_guild(guild, cfg))
        if len(cfg.entries or []) < before:
            await interaction.response.send_message(f"✅ Removed TZ clock from {channel.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message("No TZ clock was set for that channel.", ephemeral=True)

    @tz.command(name="list", description="List all timezone clocks for this server.")
    @app_commands.default_permissions(manage_guild=True)
    async def tz_list(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Guild context required.", ephemeral=True)

        cfg = _state_get_guild(guild.id)
        if not cfg.entries:
            return await interaction.response.send_message("No timezone clocks configured.", ephemeral=True)

        def _mention(cid: int) -> str:
            ch = guild.get_channel(cid)
            return ch.mention if ch else f"(missing:{cid})"

        lines = [
            f"- { _mention(e.channel_id) } — **{e.label}** @ `{e.tz}`  (fmt: `{e.fmt}`)"
            for e in cfg.entries
        ]
        await interaction.response.send_message(
            f"**Enabled:** `{cfg.enabled}` • **Interval:** `{cfg.interval_minutes}m`\n" + "\n".join(lines),
            ephemeral=True
        )

    @tz.command(name="interval", description="Set global update interval (minutes) for this server.")
    @app_commands.describe(minutes="How often to update channel names (recommended ≥ 5).")
    @app_commands.default_permissions(manage_guild=True)
    async def tz_interval(self, interaction: discord.Interaction, minutes: int):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Guild context required.", ephemeral=True)

        if minutes < 2:
            return await interaction.response.send_message("Please choose an interval ≥ 2 minutes.", ephemeral=True)

        cfg = _state_get_guild(guild.id)
        cfg.interval_minutes = int(minutes)
        _state_save_guild(guild.id, cfg)
        await _persist()
        await interaction.response.send_message(f"✅ Interval set to `{minutes}m`.", ephemeral=True)

    @tz.command(name="toggle", description="Enable or disable timezone updates for this server.")
    @app_commands.describe(enabled="True to enable, False to disable.")
    @app_commands.default_permissions(manage_guild=True)
    async def tz_toggle(self, interaction: discord.Interaction, enabled: bool):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Guild context required.", ephemeral=True)

        cfg = _state_get_guild(guild.id)
        cfg.enabled = bool(enabled)
        _state_save_guild(guild.id, cfg)
        await _persist()
        await interaction.response.send_message(f"✅ Timezone updates {'enabled' if enabled else 'disabled'}.", ephemeral=True)

    @tz.command(name="edit", description="Edit an existing timezone clock entry.")
    @app_commands.describe(
        channel="Target voice channel",
        tz="New IANA timezone (leave empty to keep current)",
        label="New label (leave empty to keep current)",
        fmt="New format (leave empty to keep current)"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def tz_edit(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        tz: Optional[str] = None,
        label: Optional[str] = None,
        fmt: Optional[str] = None,
    ):

        if tz and not _is_valid_tz(tz):
            return await interaction.response.send_message(f"❌ Unknown timezone `{tz}`. Use IANA format (e.g. `Europe/Madrid`).", ephemeral=True)

        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Guild context required.", ephemeral=True)

        cfg = _state_get_guild(guild.id)
        found = None
        for e in (cfg.entries or []):
            if e.channel_id == channel.id:
                found = e
                break

        if not found:
            return await interaction.response.send_message("No TZ clock configured for that channel.", ephemeral=True)

        if tz:    found.tz = tz
        if label: found.label = label
        if fmt:   found.fmt = fmt

        _state_save_guild(guild.id, cfg)
        await _persist()
        asyncio.create_task(self._update_guild(guild, cfg))
        await interaction.response.send_message("✅ Entry updated.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TimezonesCog(bot))
