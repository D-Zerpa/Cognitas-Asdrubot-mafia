from __future__ import annotations
import json
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from ..core.state import game
from ..core.storage import save_state
from ..core.players import send_to_player
from ..status import list_registered, get_state_cls
from ..status import engine as SE
from ..status import builtin

class StatusCog(commands.Cog, name="Status"):
    def __init__(self, bot): self.bot = bot

    # autocomplete for status names
    async def _status_autocomplete(self, interaction: discord.Interaction, current: str):
        names = list(list_registered().keys())
        current_l = (current or "").lower()
        return [app_commands.Choice(name=n, value=n)
                for n in names if current_l in n.lower()][:20]

    group = app_commands.Group(name="effects", description="Altered states tools (GM)")

    @group.command(name="apply", description="Apply a status to a player (GM only).")
    @app_commands.autocomplete(name=_status_autocomplete)
    @app_commands.describe(
        user="Target player",
        name="Status name",
        duration="Override default duration (ticks); leave empty for default",
        source="Optional source tag (GM/system/uid)",
        meta_json="Optional JSON payload (magnitude, notes...)"
    )
    @app_commands.default_permissions(administrator=True)
    async def apply(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        name: str,
        duration: Optional[int] = None,
        source: Optional[str] = "GM",
        meta_json: Optional[str] = None,
    ):
        meta = {}
        if meta_json:
            try: meta = json.loads(meta_json)
            except Exception: pass

        ok, banner = SE.apply(game, str(user.id), name, source=source, duration=duration, meta=meta)
        await save_state()

        if not ok:
            return await interaction.response.send_message(f"❌ Unknown status `{name}`.", ephemeral=True)

        # deliver banner per visibility (night -> DM; day -> public) is handled by your policy;
        # here: send DM to user always; you can also post public depending on status.

        if banner:
            await send_to_player(interaction.guild, str(user.id), banner)

        await interaction.response.send_message(f"✅ Applied **{name}** to {user.mention}.", ephemeral=True)

    @group.command(name="heal", description="Cleanse statuses from a player (GM only).")
    @app_commands.autocomplete(name=_status_autocomplete)
    @app_commands.describe(
        user="Target player",
        name="Specific status to cleanse (leave empty to cleanse all)",
        all="If true, cleanses all statuses"
    )
    @app_commands.default_permissions(administrator=True)
    async def heal(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        name: Optional[str] = None,
        all: Optional[bool] = False,
    ):
        banners = SE.heal(game, str(user.id), name=name, all_=bool(all))
        await save_state()

        # DM banners to the user
        for b in banners:
            await send_to_player(interaction.guild, str(user.id), b)

        detail = f"all statuses" if all else (f"`{name}`" if name else "nothing")
        await interaction.response.send_message(f"✅ Cleansed {detail} from {user.mention}.", ephemeral=True)

    @group.command(name="list", description="List statuses; if user omitted, shows totals.")
    @app_commands.default_permissions(administrator=True)
    async def list_(
        self, interaction: discord.Interaction, user: Optional[discord.Member] = None
    ):
        if user:
            m = SE.list_active(game, str(user.id))
            if not m:
                return await interaction.response.send_message(f"{user.mention} has no active statuses.", ephemeral=True)
            lines = [f"- **{k}**: {v.get('remaining',0)}t, stacks={v.get('stacks',1)}" for k, v in m.items()]
            return await interaction.response.send_message("\n".join(lines), ephemeral=True)
        else:
            total = sum(len(v) for v in getattr(game, "status_map", {}).values()) if hasattr(game, "status_map") else 0
            return await interaction.response.send_message(f"Total active statuses: **{total}**", ephemeral=True)

    @group.command(name="inspect", description="Show docs for a status type.")
    @app_commands.autocomplete(name=_status_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def inspect(self, interaction: discord.Interaction, name: str):
        cls = get_state_cls(name)
        if not cls:
            return await interaction.response.send_message("Unknown status.", ephemeral=True)
        s = cls()
        doc = (cls.__doc__ or "").strip()
        blocks = ", ".join(k for k, v in getattr(s, "blocks", {}).items() if v) or "—"
        msg = (f"**{s.name}** ({s.type}) vis={s.visibility} policy={s.stack_policy} "
               f"default_dur={s.default_duration}\nBlocks: {blocks}\n{doc}")
        await interaction.response.send_message(msg, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(StatusCog(bot))
