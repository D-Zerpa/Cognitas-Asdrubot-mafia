from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from ..core.state import game

class HelpCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="help", description="Show available commands")
    async def help(self, interaction: discord.Interaction):
        user = interaction.user
        is_admin = user.guild_permissions.administrator
        can_purge = user.guild_permissions.manage_messages
        phase = getattr(game, "moon_phase", None)

        embed = discord.Embed(
            title="Asdrubot — Commands",
            description="Slash command index. You will only see admin/mod sections if you have permissions.",
            color=0x2ecc71
        )
        if phase:
            embed.set_footer(text=f"Asdrubot v2.0 — Moon: {phase}")
        else:
            embed.set_footer(text="Asdrubot v2.0 — Slash Edition")

        # Players
        embed.add_field(
            name="👥 Players",
            value="\n".join([
                "`/player list`",
                "`/player register @user [name]` *(admin)*",
                "`/player unregister @user` *(admin)*",
                "`/player rename @user <new_name>` *(admin)*",
                "`/player alias_show @user`",
                "`/player alias_add @user <alias>` *(admin)*",
                "`/player alias_del @user <alias>` *(admin)*",
            ]),
            inline=False
        )





        # Voting & Phases (user/admin mixed)
        embed.add_field(
            name="🗳️ Voting & Phases",
            value="\n".join([
                "`/vote cast @user`",
                "`/vote clear`",
                "`/vote mine`",
                "`/vote end_day` *(2/3 of alive)*",
                "`/votes`",
                "`/status`",
                "`/start_day [duration] [channel] [force]` *(admin)*",
                "`/end_day` *(admin)*",
                "`/start_night [duration]` *(admin)*",
                "`/end_night` *(admin)*",
            ]),
            inline=False
        )

        # Game (admin)
        if is_admin:
            embed.add_field(
                name="🎮 Game (admin)",
                value="\n".join([
                    "`/game_start [profile]`",
                    "`/game_reset`",
                    "`/finish_game [reason]`",
                    "`/who [@user]`",
                    "`/assign @user <role>`",
                ]),
                inline=False
            )

        # Moderation (admin/mod)
        if is_admin or can_purge:
            embed.add_field(
                name="🛡️ Moderation",
                value="\n".join([
                    "`/bc <text>` *(admin)*",
                    "`/set_day_channel [#channel]` *(admin)*",
                    "`/set_admin_channel [#channel]` *(admin)*",
                    "`/set_log_channel [#channel]` *(admin)*",
                    "`/show_channels` *(admin)*",
                    "`/purge N` *(manage_messages)*",
                ]),
                inline=False
            )

        # Utilities (everyone)
        embed.add_field(
            name="🎲 Utilities",
            value="`/dice [faces]`, `/coin`",
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot): await bot.add_cog(HelpCog(bot))

