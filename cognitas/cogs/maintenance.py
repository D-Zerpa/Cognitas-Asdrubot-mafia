from __future__ import annotations
from typing import List, Optional
import discord
from discord import app_commands
from discord.ext import commands

def _local_has_subs(bot: commands.Bot, name: str) -> bool:
    try:
        for c in bot.tree.get_commands():
            if c.name == name:
                return bool(getattr(c, "options", None))
    except Exception:
        pass
    return False

class Maintenance(commands.Cog):
    """Admin utilities for slash commands maintenance."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="sync_here", description="Sync slash commands for THIS server (instant).")
    @app_commands.default_permissions(administrator=True)
    async def sync_here(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        # Opcional: trae los globales a este guild para que aparezcan ya
        try:
            self.bot.tree.copy_global_to(guild=interaction.guild)
        except Exception:
            pass
        synced = await self.bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send(f"✅ Synced {len(synced)} commands for this server.", ephemeral=True)

    @app_commands.command(name="list_commands", description="List remote slash commands (global or this guild).")
    @app_commands.describe(scope="Where to inspect: 'global' or 'guild'")
    @app_commands.choices(scope=[
        app_commands.Choice(name="global", value="global"),
        app_commands.Choice(name="guild", value="guild"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def list_commands(
        self,
        interaction: discord.Interaction,
        scope: app_commands.Choice[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if scope is None or scope.value == "global":
            remote = await self.bot.tree.fetch_commands()
            title = "Global commands (remote)"
            gid = None
        else:
            if not interaction.guild:
                return await interaction.followup.send("Use this in a server.", ephemeral=True)
            remote = await self.bot.tree.fetch_commands(guild=interaction.guild)
            title = f"Guild commands (remote) — {interaction.guild.name}"
            gid = interaction.guild.id

        lines: List[str] = []
        for cmd in remote:
            kind = "slash"
            if cmd.type is discord.AppCommandType.user:
                kind = "user"
            elif cmd.type is discord.AppCommandType.message:
                kind = "message"
            has_opts = bool(getattr(cmd, "options", None))
            lines.append(f"- /{cmd.name}  ({kind})  {'with subs' if has_opts else 'no subs'}")

        local_names = sorted(c.qualified_name for c in self.bot.tree.get_commands())
        await interaction.followup.send(
            f"**{title}**\n" +
            ("\n".join(lines) if lines else "_none_") +
            "\n\n**Local (in-process) commands:**\n" +
            ("\n".join(f"- /{n}" for n in local_names) if local_names else "_none_"),
            ephemeral=True,
        )

    @app_commands.command(name="clean_commands", description="Remove stray slash commands then sync (global or this guild).")
    @app_commands.describe(
        scope="Where to clean: 'global' or 'guild'",
        nuke="Delete ALL in chosen scope before syncing (dangerous)",
        prune_empty_roots="Remove chat-input roots with NO subcommands when local has a grouped version",
        also_remove="Extra names to remove (comma-separated), e.g. 'vote, help'",
    )
    @app_commands.choices(scope=[
        app_commands.Choice(name="global", value="global"),
        app_commands.Choice(name="guild", value="guild"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def clean_commands(
        self,
        interaction: discord.Interaction,
        scope: app_commands.Choice[str] = None,
        nuke: bool = False,
        prune_empty_roots: bool = True,
        also_remove: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)

        guild_obj: discord.abc.Snowflake | None
        if scope is None or scope.value == "global":
            guild_obj = None
            remote = await self.bot.tree.fetch_commands()
            scope_label = "global"
        else:
            if not interaction.guild:
                return await interaction.followup.send("Use this in a server.", ephemeral=True)
            guild_obj = interaction.guild
            remote = await self.bot.tree.fetch_commands(guild=guild_obj)
            scope_label = f"guild:{interaction.guild.id}"

        removed = []
        if nuke:
            self.bot.tree.clear_commands(guild=guild_obj)
            await self.bot.tree.sync(guild=guild_obj)
            return await interaction.followup.send(
                f"🧨 Nuked and re-synced **{scope_label}** commands.", ephemeral=True
            )

        extra_names = set(n.strip().lower() for n in (also_remove or "").split(",") if n.strip())
        for cmd in remote:
            try:
                if cmd.type is not discord.AppCommandType.chat_input:
                    continue
                name = cmd.name.lower()
                opts = getattr(cmd, "options", None)

                if name in extra_names:
                    await self.bot.tree.remove_command(name, type=discord.AppCommandType.chat_input, guild=guild_obj)
                    removed.append(name)
                    continue

                if prune_empty_roots and (not opts) and _local_has_subs(self.bot, name):
                    await self.bot.tree.remove_command(name, type=discord.AppCommandType.chat_input, guild=guild_obj)
                    removed.append(name)
            except Exception as e:
                removed.append(f"{cmd.name} (error: {e})")

        await self.bot.tree.sync(guild=guild_obj)

        if removed:
            await interaction.followup.send(
                f"🧹 Removed from **{scope_label}**: {', '.join(sorted(set(removed)))}\n✔️ Synced.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(f"Nothing to remove in **{scope_label}**. ✔️ Synced.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Maintenance(bot))
