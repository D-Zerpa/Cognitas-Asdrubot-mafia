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
        Register your Night action target from your PRIVATE ROLE CHANNEL (or DM).
        Usage: !act @Target [optional note]
        - Acknowledges to the user.
        - Forwards to admin log channel with order & timestamp.
        """
        import time
        from ..core.state import game
        from ..core.storage import save_state
        import discord

        actor_uid = str(ctx.author.id)
        target_uid = str(target.id)

        # Must be a registered, living player
        if actor_uid not in game.players or not game.players[actor_uid].get("alive", True):
            return await ctx.reply("You cannot act (not a registered living player).")

        if target_uid not in game.players:
            return await ctx.reply("Target is not a registered player.")

        # Enforce privacy: only from the actor's bound role channel OR DM
        actor_channel_id = game.players[actor_uid].get("channel_id")
        is_dm = isinstance(ctx.channel, discord.DMChannel) or ctx.guild is None
        is_own_role_channel = (ctx.channel.id == actor_channel_id) if not is_dm else True

        # Allow admins to relay from anywhere (optional)
        is_admin = bool(ctx.guild and ctx.author.guild_permissions.administrator)

        if not (is_own_role_channel or is_admin):
            # Try to mention the correct channel if we know it
            if ctx.guild and actor_channel_id:
                ch = ctx.guild.get_channel(actor_channel_id)
                hint = f"Please use your private channel: {ch.mention}" if ch else "Please use your private role channel."
            else:
                hint = "Please use your private role channel or DM me."
            return await ctx.reply(f"Night actions must be sent **from your private channel**. {hint}")

        # Optional: only accept when Night is active (comment out if you allow pre-queue)
        # if not game.night_deadline_epoch:
        #     return await ctx.reply("You can only send actions during Night.")

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

        # Acknowledge to the user (keep it brief)
        await ctx.reply("✅ Action registered.")

        # Forward to admin channel (with role names if available)
        admin_id = game.admin_log_channel_id
        if admin_id and ctx.guild:
            admin_chan = ctx.guild.get_channel(admin_id)
            if admin_chan:
                actor_role_code = game.players[actor_uid].get("role")
                target_role_code = game.players[target_uid].get("role")
                actor_role_name = (game.roles.get(actor_role_code, {}).get("name") or actor_role_code or "?")
                target_role_name = (game.roles.get(target_role_code, {}).get("name") or target_role_code or "?")
                ts = f"<t:{entry['ts_epoch']}:T>"
                note_part = f" — _{note.strip()}_" if note.strip() else ""
                idx = len(game.night_actions)
                await admin_chan.send(
                    f"📥 **Night action #{idx}** (Day {game.current_day_number})\n"
                    f"• Actor: <@{actor_uid}> — {actor_role_name}\n"
                    f"• Target: <@{target_uid}> — {target_role_name}\n"
                    f"• Time: {ts}{note_part}"
                )

        # Delete the original command for extra privacy
        try:
            await ctx.message.delete(delay=2)
        except Exception:
            pass

    # ---------- Night controls ----------
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def start_night(self, ctx, *args):
        """
        Start Night (idempotent). Accepts args in any order:
        !start_night
        !start_night 8h
        !start_night #village
        !start_night 6h #village
        !start_night #village 6h
        !start_night 6h #village force
        !start_night force
        At deadline, opens the Day channel (mentioned or saved default).
        """
        import time
        from ..core.timer import parse_duration_to_seconds, start_night_timer
        from ..core.state import game
        from ..core.storage import save_state

        if game.game_over:
            return await ctx.reply("Game is finished. Start a new game before starting a Night.")

        tokens = [t.strip() for t in args]
        mentioned_channels = ctx.message.channel_mentions
        target_day_channel = mentioned_channels[0] if mentioned_channels else None
        force = any(t.lower() == "force" for t in tokens)

        # find a duration token (not a channel mention like "<#...>")
        duration_token = None
        for t in tokens:
            if t.lower() == "force":
                continue
            if t.startswith("<#") and t.endswith(">"):
                continue
            if any(ch.isdigit() for ch in t):  # "8h", "90m", "1h30m"
                duration_token = t
                break

        duration_str = duration_token or "12h"
        seconds = parse_duration_to_seconds(duration_str)
        if seconds <= 0:
            return await ctx.reply("Provide a valid duration (e.g., `12h`, `6h`, `90m`).")

        # refuse if a Night is already active unless forcing
        if hasattr(game, "is_night_active") and game.is_night_active() and not force:
            when = f"<t:{game.night_deadline_epoch}:R>" if game.night_deadline_epoch else ""
            return await ctx.reply(f"Night already active (ends {when}). Add `force` to restart.")

        # cancel existing timer if forcing
        if force and game.night_timer_task and not game.night_timer_task.done():
            game.night_timer_task.cancel()
            game.night_timer_task = None

        # choose which Day channel will open at dawn: mention > saved default
        open_channel = (
            target_day_channel
            or (ctx.guild.get_channel(game.default_day_channel_id) if game.default_day_channel_id else None)
        )
        if not open_channel:
            return await ctx.reply("Please set a Day channel with `!set_day_channel` or pass one here (e.g., `!start_night 8h #village`).")

        # Optional: restrict where !act is allowed = current channel
        game.night_channel_id = ctx.channel.id
        game.next_day_channel_id = open_channel.id
        game.night_deadline_epoch = int(time.time()) + seconds
        save_state("state.json")

        await ctx.send(
            f"🌙 **Night begins.** Ends at <t:{game.night_deadline_epoch}:F> (<t:{game.night_deadline_epoch}:R>).\n"
            f"Players can register actions with `!act @Target [note]`."
        )

        # single source of truth: start the timer via API (no manual _worker spawn)
        await start_night_timer(self.bot, ctx.guild.id)

            # Delete the original command for extra privacy
        try:
            await ctx.message.delete(delay=2)
        except Exception:
            pass


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
            # Delete the original command for extra privacy
        
        try:
            await ctx.message.delete(delay=2)
        except Exception:
            pass    