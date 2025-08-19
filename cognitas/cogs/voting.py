import time, asyncio, discord
from discord.ext import commands
from ..core.state import game
from ..core.storage import save_state
from ..core.timer import parse_duration_to_seconds, start_day_timer

class VotingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------- Day controls ----------
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def start_day(self, ctx, duration: str = "24h", channel: discord.TextChannel = None, force: str = ""):
        """
        Start the Day phase with a duration. Idempotent by default.
        Priority: provided channel > saved default Day channel > current channel.
        Use trailing 'force' to restart Day even if active (will increment the day).
        Examples:
        !start_day
        !start_day 12h
        !start_day 8h #village
        !start_day 8h #village force
        """
        from ..core.timer import parse_duration_to_seconds, start_day_timer
        import time, asyncio

        if game.game_over:
            return await ctx.reply("Game is finished. Start a new game before starting a Day.")

        seconds = parse_duration_to_seconds(duration)
        if seconds <= 0:
            return await ctx.reply("Provide a valid duration (e.g., `24h`, `1h30m`, `90m`).")

        # Guard: refuse if a Day is already active, unless 'force'
        if game.is_day_active() and force.lower() != "force":
            chan = ctx.guild.get_channel(game.day_channel_id)
            when = f"<t:{game.day_deadline_epoch}:R>" if game.day_deadline_epoch else ""
            return await ctx.reply(f"Day already active in {chan.mention if chan else '#?'} (ends {when}). Use `force` to restart.")

        # If forcing, cancel existing timer
        if force.lower() == "force" and game.day_timer_task and not game.day_timer_task.done():
            game.day_timer_task.cancel()
            game.day_timer_task = None

        # choose target channel
        target = channel or (ctx.guild.get_channel(game.default_day_channel_id) if game.default_day_channel_id else ctx.channel)

        game.day_channel_id = target.id
        game.votes = {}                       # reset votes idempotently
        game.current_day_number += 1          # increment day on (re)start
        game.day_deadline_epoch = int(time.time()) + seconds
        await start_day_timer(self.bot, ctx.guild.id, target.id)
        save_state("state.json")

        # open the target channel for sending
        overw = target.overwrites_for(ctx.guild.default_role)
        overw.send_messages = True
        await target.set_permissions(ctx.guild.default_role, overwrite=overw)

        await target.send(
            f"🌞 **Day {game.current_day_number} begins.** Base threshold: **{game.base_threshold()}**.\n"
            f"Ends at <t:{game.day_deadline_epoch}:F> (<t:{game.day_deadline_epoch}:R>). Use `!vote @user`."
        )

        # (re)start day timer
        if game.day_timer_task and not game.day_timer_task.done():
            game.day_timer_task.cancel()
        game.day_timer_task = asyncio.create_task(day_timer_worker(self.bot, ctx.guild.id, target.id))


    @commands.command()
    @commands.has_permissions(administrator=True)
    async def end_day(self, ctx):
        """End Day """
        chan = ctx.guild.get_channel(game.day_channel_id) if game.day_channel_id else None
        if not chan:
            return await ctx.reply("No active Day channel set.")

        # If already closed for sending, just mark deadlines and timers
        overw = chan.overwrites_for(ctx.guild.default_role)
        already_closed = (overw.send_messages is False)

        if not already_closed:
            overw.send_messages = False
            await chan.set_permissions(ctx.guild.default_role, overwrite=overw)
            await chan.send("🛑 Day ended by a moderator. Channel closed.")

        game.day_deadline_epoch = None
        if game.day_timer_task and not game.day_timer_task.done():
            game.day_timer_task.cancel()
            game.day_timer_task = None
        save_state("state.json")

        if already_closed:
            await ctx.reply("Day was already closed. State synced.")


    # ---------- Voting ----------
    @commands.command()
    async def vote(self, ctx, member: discord.Member):
        """Cast a vote (strict mode: must !unvote before changing)."""
        if game.day_channel_id != ctx.channel.id:
            return await ctx.reply("This is not the Day voting channel.")
        voter = str(ctx.author.id)
        target = str(member.id)

        if voter in game.votes:
            current = game.votes[voter]
            if current == target:
                return await ctx.reply(f"You already voted for <@{target}>.")
            return await ctx.reply(
                f"You already have an active vote on <@{current}>. Use `!unvote` first to change it."
            )

        if voter not in game.players or not game.players[voter].get("alive", True):
            return await ctx.reply("You cannot vote.")
        if game.flags_of(voter).get("silenced", False):
            return await ctx.reply("You are silenced.")
        if target not in game.players or not game.players[target].get("alive", True):
            return await ctx.reply("That player is not available.")
        if game.flags_of(target).get("absent", False):
            return await ctx.reply("That player is absent today (cannot be voted).")

        game.votes[voter] = target
        save_state("state.json")
        await ctx.message.add_reaction("🗳️")
        await ctx.send(f"Vote from <@{voter}> → <@{target}> (weight {game.vote_weight(voter)}).")
        await self._check_threshold_and_close(ctx)

    @commands.command()
    async def unvote(self, ctx):
        """Remove your vote in the Day channel."""
        if game.day_channel_id != ctx.channel.id:
            return await ctx.reply("This is not the Day voting channel.")
        voter = str(ctx.author.id)
        if game.votes.pop(voter, None) is not None:
            save_state("state.json")
            await ctx.message.add_reaction("✅")
            await self._check_threshold_and_close(ctx)
        else:
            await ctx.reply("You had no active vote.")

    @commands.command()
    async def myvote(self, ctx):
        """Show your current vote and its weight."""
        voter = str(ctx.author.id)
        tgt = game.votes.get(voter)
        if not tgt:
            return await ctx.reply("You have no active vote.")
        await ctx.reply(f"Your current vote is on <@{tgt}> (weight {game.vote_weight(voter)}).")

    @commands.command(name="votes")
    async def votes_breakdown(self, ctx):
        """Per-voter breakdown grouped by target, with weights (Day channel only)."""
        if game.day_channel_id != ctx.channel.id:
            return await ctx.reply("This is not the Day voting channel.")
        if not game.votes:
            return await ctx.send("No votes yet.")

        grouped = {}
        for voter_uid, target_uid in game.votes.items():
            w = game.vote_weight(voter_uid)
            if w <= 0:
                continue
            grouped.setdefault(target_uid, []).append((voter_uid, w))

        lines = [f"🗓️ Day **{game.current_day_number}** | Base threshold: **{game.base_threshold()}**", ""]
        for target_uid, entries in sorted(grouped.items(), key=lambda kv: kv[0]):
            req = game.required_for_target(target_uid)
            subtotal = sum(w for _, w in entries)
            lines.append(f"🎯 Target <@{target_uid}> — **{subtotal}/{req}**")
            for voter_uid, w in sorted(entries, key=lambda x: (-x[1], x[0])):
                lines.append(f"  • <@{voter_uid}> (w={w})")
            lines.append("")

        totals = game.totals_per_target()
        if totals:
            lines.append("**Totals:**")
            for target_uid, total in totals.items():
                req = game.required_for_target(target_uid)
                lines.append(f"- <@{target_uid}> → **{total}/{req}**")

        msg = "\n".join(lines)
        await ctx.send(msg if len(msg) < 1800 else (msg[:1700] + "\n… (truncated)"))

    @commands.command()
    async def status(self, ctx):
        """Quick totals view (Day channel only)."""
        if game.day_channel_id != ctx.channel.id:
            return await ctx.reply("This is not the Day voting channel.")
        totals = game.totals_per_target()
        lines = [f"🗓️ Day: **{game.current_day_number}**  |  Base threshold: **{game.base_threshold()}**"]
        if not totals:
            lines.append("No votes yet.")
        else:
            # optional: tie detection
            if totals:
                max_total = max(totals.values())
                leaders = [uid for uid, t in totals.items() if t == max_total]
                if len(leaders) > 1:
                    tags = ", ".join(f"<@{u}>" for u in leaders)
                    lines.append(f"⚖️ Currently tied among: {tags} ({max_total}).")
            for obj_uid, total in totals.items():
                req = game.required_for_target(obj_uid)
                lines.append(f"- <@{obj_uid}> → **{total}/{req}**")
        await ctx.send("\n".join(lines))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def clearvotes(self, ctx):
        """Clear all current votes (admin only)."""
        game.votes = {}
        save_state("state.json")
        await ctx.send("🗑️ All votes have been cleared.")

    # ---------- internal ----------
    async def _check_threshold_and_close(self, ctx):
        totals = game.totals_per_target()
        for obj_uid, total in totals.items():
            req = game.required_for_target(obj_uid)
            if total >= req:
                chan = ctx.guild.get_channel(game.day_channel_id)
                overw = chan.overwrites_for(ctx.guild.default_role)
                overw.send_messages = False
                await chan.set_permissions(ctx.guild.default_role, overwrite=overw)
                await chan.send(f"🗳️ Threshold reached: <@{obj_uid}> ({total}/{req}). **Channel closed.**")
                return
