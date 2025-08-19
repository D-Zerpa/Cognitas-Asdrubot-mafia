import time, asyncio, discord
from discord.ext import commands
from ..core.state import game
from ..core.storage import save_state
from ..core.timer import parse_duration_to_seconds, _night_timer_worker

class ActionsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------- Player action registration ----------
    @commands.command(name="act")
    async def act_register(self, ctx, target: discord.Member, *, note: str = ""):
        """
        Register your Night action target (manual resolution by mods).
        Usage: !act @Target [optional note]
        - Acknowledges to the user.
        - Forwards to admin log channel with order & timestamp.
        """
        actor_uid = str(ctx.author.id)
        target_uid = str(target.id)

        # Basic sanity checks
        if actor_uid not in game.players or not game.players[actor_uid].get("alive", True):
            return await ctx.reply("You cannot act (not a registered living player).")
        if not game.players.get(target_uid):
            return await ctx.reply("Target is not a registered player.")

        # Optional: restrict to a Night channel only
        if game.night_channel_id and ctx.channel.id != game.night_channel_id:
            return await ctx.reply("Night actions must be sent in the designated Night channel.")

        # Log entry
        entry = {
            "day": game.current_day_number,
            "ts_epoch": int(time.time()),
            "actor_uid": actor_uid,
            "target_uid": target_uid,
            "note": note.strip()
        }
        game.night_actions.append(entry)
        save_state("state.json")

        # Acknowledge to the user (private in-channel)
        await ctx.reply("✅ Action registered.")

        # Forward to admin channel
        admin_id = game.admin_log_channel_id
        if admin_id:
            admin_chan = ctx.guild.get_channel(admin_id)
            if admin_chan:
                ts = f"<t:{entry['ts_epoch']}:T>"
                note_part = f" — _{note.strip()}_" if note.strip() else ""
                idx = len(game.night_actions)
                await admin_chan.send(
                    f"📥 **Night action #{idx}** (Day {game.current_day_number})\n"
                    f"• Actor: <@{actor_uid}>\n"
                    f"• Target: <@{target_uid}>\n"
                    f"• Time: {ts}{note_part}"
                )

    # ---------- Night controls ----------
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def start_night(self, ctx, duration: str = "12h", day_channel: discord.TextChannel = None, force: str = ""):
        """
        Start Night with a timer; at deadline, open the provided (or default) Day channel.
        Idempotent by default. Use trailing 'force' to restart Night even if active.
        Examples:
        !start_night
        !start_night 8h
        !start_night 6h #village
        !start_night 6h #village force
        """
        from ..core.timer import parse_duration_to_seconds, start_night_timer
        import time, asyncio

        if game.game_over:
            return await ctx.reply("Game is finished. Start a new game before starting a Night.")

        seconds = parse_duration_to_seconds(duration)
        if seconds <= 0:
            return await ctx.reply("Provide a valid duration (e.g., `12h`, `6h`, `90m`).")

        # Guard: refuse if a Night is already active, unless 'force'
        if game.is_night_active() and force.lower() != "force":
            when = f"<t:{game.night_deadline_epoch}:R>" if game.night_deadline_epoch else ""
            return await ctx.reply(f"Night already active (ends {when}). Use `force` to restart.")

        # If forcing, cancel existing timer
        if force.lower() == "force" and game.night_timer_task and not game.night_timer_task.done():
            game.night_timer_task.cancel()
            game.night_timer_task = None

        open_channel_id = day_channel.id if day_channel else game.default_day_channel_id
        if not open_channel_id:
            return await ctx.reply("Please set a Day channel with `!set_day_channel` or pass one here.")

        # Optional: restrict where !act is allowed = current channel
        game.night_channel_id = ctx.channel.id
        game.night_deadline_epoch = int(time.time()) + seconds
        game.next_day_channel_id = open_channel_id
        await start_night_timer(self.bot, ctx.guild.id)
        save_state("state.json")

        await ctx.send(
            f"🌙 **Night begins.** Ends at <t:{game.night_deadline_epoch}:F> (<t:{game.night_deadline_epoch}:R>).\n"
            f"Players can register actions with `!act @Target [note]`."
        )

        # (re)start night timer
        if game.night_timer_task and not game.night_timer_task.done():
            game.night_timer_task.cancel()
        game.night_timer_task = asyncio.create_task(night_timer_worker(self.bot, ctx.guild.id))


    @commands.command()
    @commands.has_permissions(administrator=True)
    async def end_night(self, ctx):
        """End Night now; open the Day channel (idempotent)."""
        day_chan = ctx.guild.get_channel(game.next_day_channel_id) if game.next_day_channel_id else None
        if not day_chan:
            return await ctx.reply("No Day channel configured to open.")

        # Open day channel for sending if not already open
        overw = day_chan.overwrites_for(ctx.guild.default_role)
        already_open = (overw.send_messages is True)
        if not already_open:
            overw.send_messages = True
            await day_chan.set_permissions(ctx.guild.default_role, overwrite=overw)
            await day_chan.send("🌞 **Dawn breaks. Day is open.**")

        game.night_deadline_epoch = None
        if game.night_timer_task and not game.night_timer_task.done():
            game.night_timer_task.cancel()
            game.night_timer_task = None
        save_state("state.json")

        if already_open:
            await ctx.reply("Day was already open. Night state synced.")
        else:
            await ctx.send("🛑 Night ended by a moderator.")
