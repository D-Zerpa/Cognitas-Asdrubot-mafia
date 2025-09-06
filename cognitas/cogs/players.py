from __future__ import annotations

import re
import discord
from discord import app_commands
from discord.ext import commands

from ..core import players as players_core
from ..core.players import get_player_snapshot

# ------------------------------------------------------------
# Interaction -> ctx adapter (uses followup if interaction already responded/deferred)
# ------------------------------------------------------------
class InteractionCtx:
    def __init__(self, interaction: discord.Interaction):
        self._i = interaction
        self.guild = interaction.guild
        self.bot = interaction.client  # type: ignore
        self.channel = interaction.channel
        self.author = interaction.user
        self.message = None  # compat

    async def reply(self, content: str = None, **kwargs):
        try:
            if self._i.response.is_done():
                return await self._i.followup.send(content or "\u200b", **kwargs)
            else:
                return await self._i.response.send_message(content or "\u200b", **kwargs)
        except Exception:
            if self.channel:
                try:
                    return await self.channel.send(content or "\u200b", **kwargs)
                except Exception:
                    pass

    async def send(self, content: str = None, **kwargs):
        return await self.reply(content, **kwargs)


# ------------------------------------------------------------
# Canonical game flags (name -> {type, desc, aliases})
# Used for autocomplete and parsing in /player set_flag
# ------------------------------------------------------------
# types: "bool" | "int" | "str"
FLAG_DEFS: dict[str, dict] = {
    # Voting-related flags
    "hidden_vote": {
        "type": "bool",
        "desc": "Vote remains anonymous in public lists.",
        "aliases": ["incognito", "hidden"],
    },
    "voting_boost": {
        "type": "int",
        "desc": "Adds to the player's ballot weight (1+boost).",
        "aliases": ["vote_boost", "vote_bonus"],
    },
    "no_vote": {
        "type": "bool",
        "desc": "Player cannot cast votes (0 weight).",
        "aliases": ["silenced_vote", "mute_vote"],
    },
    "silenced": {
        "type": "bool",
        "desc": "Player is silenced (treated as 0 voting power).",
        "aliases": [],
    },

    # Lynch threshold modifiers (target extras)
    "lynch_plus": {
        "type": "int",
        "desc": "Extra votes required to lynch this target.",
        "aliases": ["lynch_resistance", "needs_extra_votes"],
    },

    # Night/action examples
    "immune_night": {
        "type": "bool",
        "desc": "Immune to night eliminations.",
        "aliases": ["night_immune"],
    },
    "action_blocked": {
        "type": "bool",
        "desc": "Night action is blocked for this player.",
        "aliases": ["blocked", "role_blocked"],
    },
    "protected": {
        "type": "bool",
        "desc": "Temporarily protected from kills.",
        "aliases": [],
    },
}

# Safe edit field suggestions — NO voting fields
EDIT_FIELD_SUGGESTIONS = [
    "name",
    "alias",
    "role",
    "alive",
    "effects",
    "notes",
]
# Other custom fields still accepted, but not suggested.


# ------------------------------------------------------------
# Autocomplete helpers
# ------------------------------------------------------------
def _all_flag_keys_with_aliases() -> dict[str, str]:
    """
    Returns a map normalized_name -> canonical_key to support aliases.
    """
    out = {}
    for key, meta in FLAG_DEFS.items():
        out[key.lower()] = key
        for a in meta.get("aliases", []):
            out[a.lower()] = key
    return out

def _canonical_flag_name(s: str) -> str | None:
    if not s:
        return None
    return _all_flag_keys_with_aliases().get(s.lower())

async def _flag_name_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    cur = (current or "").lower()
    items: list[tuple[str, str]] = []
    for key, meta in FLAG_DEFS.items():
        label = f"{key} — {meta.get('desc','')}"
        if cur in key.lower() or cur in label.lower():
            items.append((label, key))
        else:
            for a in meta.get("aliases", []):
                if cur in a.lower():
                    items.append((f"{key} (alias: {a}) — {meta.get('desc','')}", key))
                    break
    return [app_commands.Choice(name=lbl[:100], value=val) for lbl, val in items[:25]]

async def _field_name_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    cur = (current or "").lower()
    res = [f for f in EDIT_FIELD_SUGGESTIONS if cur in f.lower()]
    return [app_commands.Choice(name=f, value=f) for f in res[:25]]

async def _flag_value_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    ns = interaction.namespace
    flag_key = _canonical_flag_name(getattr(ns, "flag", "") or "")
    if not flag_key:
        return [app_commands.Choice(name="(select a flag first)", value=current or "")]
    ftype = FLAG_DEFS[flag_key]["type"]
    out: list[app_commands.Choice[str]] = []
    if ftype == "bool":
        for v in ["true", "false", "on", "off", "yes", "no", "1", "0"]:
            if current.lower() in v:
                out.append(app_commands.Choice(name=v, value=v))
    elif ftype == "int":
        for v in ["0", "1", "2", "3", "5", "10"]:
            if current.lower() in v:
                out.append(app_commands.Choice(name=v, value=v))
    else:  # str
        samples = ["note", "tag", "value"]
        for v in samples:
            if current.lower() in v:
                out.append(app_commands.Choice(name=v, value=v))
    return out[:25]

def _parse_flag_value(flag_key: str, raw: str):
    """Parses string into bool/int/str depending on FLAG_DEFS."""
    meta = FLAG_DEFS.get(flag_key) or {}
    ftype = meta.get("type", "str")
    s = (raw or "").strip()

    if ftype == "bool":
        if re.fullmatch(r"(?i)(true|on|yes|y|1)", s):
            return True
        if re.fullmatch(r"(?i)(false|off|no|n|0)", s):
            return False
        return bool(s)
    if ftype == "int":
        try:
            return int(s)
        except Exception:
            return 0
    return s


# ------------------------------------------------------------
# Cog
# ------------------------------------------------------------
class PlayersCog(commands.GroupCog, name="player", description="Manage players"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------
    # List / View
    # -------------------------
    @app_commands.command(name="list", description="List alive and dead players")
    async def list_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.list_players(ctx)

    @app_commands.command(name="view", description="View a player's full state (admin)")
    @app_commands.default_permissions(administrator=True)
    async def view_cmd(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)

        data = get_player_snapshot(str(member.id))
        if not data:
            return await interaction.followup.send("Player not registered.", ephemeral=True)

        def fmt_bool(b: bool | None):
            if b is None:
                return "—"
            return "✅ True" if b else "❌ False"

        def fmt_list(arr):
            return ", ".join(f"`{x}`" for x in arr) if arr else "—"

        def fmt_flags(d):
            if not d:
                return "—"
            parts = [f"`{k}`: `{v}`" for k, v in d.items()]
            if len(parts) > 10:
                parts = parts[:10] + ["…"]
            return "\n".join(parts)

        embed = discord.Embed(
            title=f"Player: {data.get('name') or data.get('alias') or member.display_name}",
            description=f"User: <@{data['uid']}>",
            color=0x3498DB if data.get("alive", True) else 0xC0392B,
        )
        embed.add_field(name="Alive", value=fmt_bool(data.get("alive")), inline=True)
        embed.add_field(name="Role", value=data.get("role") or "—", inline=True)
        embed.add_field(name="Aliases", value=fmt_list(data.get("aliases", [])), inline=False)
        embed.add_field(name="Effects", value=fmt_list(data.get("effects", [])), inline=False)
        embed.add_field(name="Flags", value=fmt_flags(data.get("flags", {})), inline=False)
        embed.set_footer(text="Asdrubot — Player inspector")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # -------------------------
    # Register / Unregister / Rename
    # -------------------------
    @app_commands.command(name="register", description="Register a player (admin)")
    @app_commands.describe(member="Target user to register", name="Optional display name/alias")
    @app_commands.default_permissions(administrator=True)
    async def register_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        name: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.register(ctx, member, name=name)

    @app_commands.command(name="unregister", description="Unregister a player (admin)")
    @app_commands.default_permissions(administrator=True)
    async def unregister_cmd(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.unregister(ctx, member)

    @app_commands.command(name="rename", description="Rename a player (admin)")
    @app_commands.describe(new_name="New display name")
    @app_commands.default_permissions(administrator=True)
    async def rename_cmd(self, interaction: discord.Interaction, member: discord.Member, new_name: str):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.rename(ctx, member, new_name=new_name)

    # -------------------------
    # Aliases
    # -------------------------
    @app_commands.command(name="alias_show", description="Show a player's aliases")
    async def alias_show_cmd(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.alias_show(ctx, member)

    @app_commands.command(name="alias_add", description="Add an alias (admin)")
    @app_commands.default_permissions(administrator=True)
    async def alias_add_cmd(self, interaction: discord.Interaction, member: discord.Member, alias: str):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.alias_add(ctx, member, alias=alias)

    @app_commands.command(name="alias_del", description="Remove an alias (admin)")
    @app_commands.default_permissions(administrator=True)
    async def alias_del_cmd(self, interaction: discord.Interaction, member: discord.Member, alias: str):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.alias_del(ctx, member, alias=alias)

    # -------------------------
    # Generic edit (NO voting fields suggested)
    # -------------------------
    @app_commands.command(name="edit", description="Edit stored player fields (safe suggestions)")
    @app_commands.describe(field="Field name", value="New value")
    @app_commands.autocomplete(field=_field_name_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def edit_cmd(self, interaction: discord.Interaction, member: discord.Member, field: str, value: str):
        """
        Suggests only safe fields (no voting_* / hidden_vote / etc).
        If admin writes a custom field manually, we still pass it to the helper.
        """
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.edit_player(ctx, member, field, value)

    # -------------------------
    # Flags (autocomplete + parsing)
    # -------------------------
    @app_commands.command(name="set_flag", description="Set a flag on a player (with suggestions)")
    @app_commands.describe(flag="Flag key", value="Value (typed: bool/int/str)")
    @app_commands.autocomplete(flag=_flag_name_autocomplete, value=_flag_value_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def set_flag_cmd(self, interaction: discord.Interaction, member: discord.Member, flag: str, value: str):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        canonical = _canonical_flag_name(flag) or flag
        parsed = _parse_flag_value(canonical, value)

        await players_core.set_flag(ctx, member, canonical, parsed)

    @app_commands.command(name="del_flag", description="Remove a flag from a player")
    @app_commands.describe(flag="Flag key to remove")
    @app_commands.autocomplete(flag=_flag_name_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def del_flag_cmd(self, interaction: discord.Interaction, member: discord.Member, flag: str):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        canonical = _canonical_flag_name(flag) or flag
        await players_core.del_flag(ctx, member, canonical)

    # -------------------------
    # Effects
    # -------------------------
    @app_commands.command(name="add_effect", description="Add an effect to a player (admin)")
    @app_commands.default_permissions(administrator=True)
    async def add_effect_cmd(self, interaction: discord.Interaction, member: discord.Member, effect: str):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.add_effect(ctx, member, effect)

    @app_commands.command(name="remove_effect", description="Remove an effect from a player (admin)")
    @app_commands.default_permissions(administrator=True)
    async def remove_effect_cmd(self, interaction: discord.Interaction, member: discord.Member, effect: str):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.remove_effect(ctx, member, effect)

    # -------------------------
    # Kill / Revive
    # -------------------------
    @app_commands.command(name="kill", description="Mark a player as dead (admin)")
    @app_commands.default_permissions(administrator=True)
    async def kill_cmd(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.kill(ctx, member)

    @app_commands.command(name="revive", description="Mark a player as alive (admin)")
    @app_commands.default_permissions(administrator=True)
    async def revive_cmd(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.revive(ctx, member)


async def setup(bot: commands.Bot):
    await bot.add_cog(PlayersCog(bot))


