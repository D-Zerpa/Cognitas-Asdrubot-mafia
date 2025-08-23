import discord
from discord.ext import commands
from ..core.state import game
from ..core.storage import save_state

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="purge")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int, channel: discord.TextChannel = None):
        """
        Deletes a specific number of messages from a single channel.
        Usage:
        !purge 50                 → deletes 50 messages in the current channel
        !purge 100 #general       → deletes 100 messages in #general
        """
        target_channel = channel or ctx.channel

        # Safety limit to avoid accidental nukes
        if amount <= 0 or amount > 500:
            return await ctx.send("⚠️ Please choose an amount between **1** and **500**.")

        # Check if the bot has permissions
        if not target_channel.permissions_for(ctx.guild.me).manage_messages:
            return await ctx.send(f"❌ I don’t have permission to manage messages in {target_channel.mention}.")

        # Ask for confirmation
        await ctx.send(
            f"⚠️ Are you sure you want to delete **{amount}** messages in {target_channel.mention}?\n"
            "Type `CONFIRM` to proceed or anything else to cancel."
        )

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            confirm_msg = await self.bot.wait_for("message", check=check, timeout=20)
        except:
            return await ctx.send("❌ Timed out. Purge cancelled.")

        if confirm_msg.content.strip().upper() != "CONFIRM":
            return await ctx.send("❌ Purge cancelled.")

        # Do the purge
        deleted = await target_channel.purge(limit=amount)
        await ctx.send(f"🧹 Deleted **{len(deleted)}** messages in {target_channel.mention}.", delete_after=5)
    
    
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def assign(self, ctx, member: discord.Member, role_code: str):
        """Assign a role to a player and bind THIS channel as their private channel."""
        code = role_code.upper()
        uid = str(member.id)
        existing = game.players.get(uid)

        # If already assigned same role and same channel, be idempotent
        if existing and existing.get("role") == code and existing.get("channel_id") == ctx.channel.id:
            return await ctx.send(f"✅ {member.mention} already has **{game.roles[code]['name']}** bound to {ctx.channel.mention}.")

        game.players.setdefault(uid, {})
        game.players[uid].update({
            "nick": member.display_name,
            "role": code,
            "channel_id": ctx.channel.id,
            "alive": True,
            "flags": game.players[uid].get("flags", {"silenced": False, "absent": False}),
            "effects": game.players[uid].get("effects", [])
        })
        save_state("state.json")

        overwrites = ctx.channel.overwrites
        overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        await ctx.channel.edit(overwrites=overwrites)

        await ctx.send(f"✅ Assigned **{game.roles[code]['name']}** to {member.mention} and bound to {ctx.channel.mention}.")

                # Delete the original command for extra privacy
        try:
            await ctx.message.delete(delay=2)
        except Exception:
            pass

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def who(self, ctx, member: discord.Member = None):
        """Show someone's assigned role and bound channel (or yours if no arg)."""
        target = member or ctx.author
        info = game.players.get(str(target.id))
        if not info:
            return await ctx.reply("ℹ️ No role assigned.")
        role = game.roles.get(info["role"], {})
        channel = ctx.guild.get_channel(info.get("channel_id")) if info.get("channel_id") else None
        await ctx.send(
            f"👤 {target.mention} → **{role.get('name','?')}** ({info['role']}). "
            f"Channel: {channel.mention if channel else 'N/A'}"
        )

        
                # Delete the original command for extra privacy
        try:
            await ctx.message.delete(delay=2)
        except Exception:
            pass
        
        
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def effect(self, ctx, member: discord.Member, etype: str, value: int = None, expires_in_days: int = None):
        """Add a runtime effect to a player (vote_boost / plotino_mark / zenon_bonus_consumed)."""
        uid = str(member.id)
        if uid not in game.players:
            return await ctx.reply("Assign a role to that player first.")
        eff = {"type": etype}
        if value is not None:
            eff["value"] = int(value)
        if expires_in_days is not None:
            eff["expires_day"] = game.current_day_number + int(expires_in_days)
        game.players[uid].setdefault("effects", []).append(eff)
        save_state("state.json")
        await ctx.message.add_reaction("✨")
        await ctx.send(f"🎯 Effect added to {member.mention}: `{eff}`")
        
                # Delete the original command for extra privacy
        try:
            await ctx.message.delete(delay=2)
        except Exception:
            pass

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def flag(self, ctx, member: discord.Member, key: str, value: int):
        """Set player flags (0/1): silenced, absent, alive."""
        uid = str(member.id)
        if uid not in game.players:
            return await ctx.reply("Assign a role to that player first.")
        if key == "alive":
            game.players[uid]["alive"] = bool(int(value))
        else:
            flags = game.players[uid].setdefault("flags", {})
            flags[key] = bool(int(value))
        save_state("state.json")
        await ctx.message.add_reaction("🛠️")
        await ctx.send(f"Flag `{key}` for {member.mention} = {bool(int(value))}")
        
                # Delete the original command for extra privacy
        try:
            await ctx.message.delete(delay=2)
        except Exception:
            pass

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def set_admin_channel(self, ctx, channel: discord.TextChannel = None):
        """
        Set the admin log channel (where Night action logs are sent).
        Usage:
          !set_admin_channel            -> uses current channel
          !set_admin_channel #mod-log   -> uses the provided channel
        """
        target = channel or ctx.channel
        game.admin_log_channel_id = target.id
        save_state("state.json")
        await ctx.send(f"🧭 Admin log channel set to {target.mention}")
        
                # Delete the original command for extra privacy
        try:
            await ctx.message.delete(delay=2)
        except Exception:
            pass

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def set_day_channel(self, ctx, channel: discord.TextChannel = None):
        """
        Set the default Day/general channel (opened at dawn).
        Usage:
          !set_day_channel            -> uses current channel
          !set_day_channel #day       -> uses the provided channel
        """
        target = channel or ctx.channel
        game.default_day_channel_id = target.id
        save_state("state.json")
        await ctx.send(f"🌞 Default Day channel set to {target.mention}")
        
                # Delete the original command for extra privacy
        try:
            await ctx.message.delete(delay=2)
        except Exception:
            pass


    @commands.command(name="show_channels")
    @commands.has_permissions(administrator=True)
    async def show_channels(self, ctx):
        admin = ctx.guild.get_channel(game.admin_log_channel_id) if game.admin_log_channel_id else None
        day   = ctx.guild.get_channel(game.default_day_channel_id) if game.default_day_channel_id else None
        await ctx.send(
            "Current channels:\n"
            f"- Admin log: {admin.mention if admin else 'not set'}\n"
            f"- Default Day: {day.mention if day else 'not set'}"
        )
        
                # Delete the original command for extra privacy
        try:
            await ctx.message.delete(delay=2)
        except Exception:
            pass

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def finish_game(self, ctx, *, note: str = ""):
        """
        Finish the game: cancel timers, lock Day channel, clear deadlines,
        mark game_over=True, and announce. Does NOT delete players/states.
        """
        # Cancel timers if running
        if game.day_timer_task and not game.day_timer_task.done():
            game.day_timer_task.cancel()
            game.day_timer_task = None
        if game.night_timer_task and not game.night_timer_task.done():
            game.night_timer_task.cancel()
            game.night_timer_task = None

        # Lock Day channel if set
        if game.day_channel_id:
            chan = ctx.guild.get_channel(game.day_channel_id)
            if chan:
                overw = chan.overwrites_for(ctx.guild.default_role)
                overw.send_messages = False
                await chan.set_permissions(ctx.guild.default_role, overwrite=overw)
                await chan.send("🏁 **Game finished.** Channel locked.")

        # Clear deadlines and mark game over
        game.day_deadline_epoch = None
        game.night_deadline_epoch = None
        game.game_over = True

        # Optional: clear live votes to avoid confusion
        game.votes = {}

        save_state("state.json")

        # Post a summary/announcement here
        extra = f"\n\n**Note:** {note}" if note.strip() else ""
        await ctx.send(f"✅ Game marked as finished. State persisted.{extra}")
        
                # Delete the original command for extra privacy
        try:
            await ctx.message.delete(delay=2)
        except Exception:
            pass

    @commands.command(name="apply_mark")
    @commands.has_permissions(administrator=True)
    async def apply_mark(self, ctx, member: discord.Member):
        """
        Apply Plotino's mark to a player: -1 votes needed to lynch them.
        Usage: !apply_mark @Player
        """
        uid = str(member.id)
        if uid not in game.players:
            return await ctx.reply("Target is not a registered player.")

        # Add a unique, persistent mark
        added = False
        if hasattr(game, "add_unique_effect"):
            added = game.add_unique_effect(uid, "plotino_mark", value=0, expires_day=None)
        else:
            # Fallback if you didn't add helpers
            effs = game.players[uid].setdefault("effects", [])
            if not any(e.get("type") == "plotino_mark" for e in effs):
                effs.append({"type": "plotino_mark", "value": 0, "expires_day": None})
                added = True

        save_state("state.json")

        if added:
            await ctx.send(f"⚖️ {member.mention} is now **marked** (–1 vote to lynch).")
        else:
            await ctx.send(f"ℹ️ {member.mention} was already marked.")
            
                # Delete the original command for extra privacy
        try:
            await ctx.message.delete(delay=2)
        except Exception:
            pass

    @commands.command(name="remove_mark")
    @commands.has_permissions(administrator=True)
    async def remove_mark(self, ctx, member: discord.Member):
        """
        Remove Plotino's mark from a player.
        Usage: !remove_mark @Player
        """
        uid = str(member.id)
        if uid not in game.players:
            return await ctx.reply("Target is not a registered player.")

        removed = False
        if hasattr(game, "remove_effect"):
            removed = game.remove_effect(uid, "plotino_mark")
        else:
            effs = game.players[uid].get("effects", [])
            before = len(effs)
            game.players[uid]["effects"] = [e for e in effs if e.get("type") != "plotino_mark"]
            removed = len(game.players[uid]["effects"]) != before

        save_state("state.json")

        if removed:
            await ctx.send(f"🧹 Mark removed from {member.mention}.")
        else:
            await ctx.send(f"ℹ️ {member.mention} had no mark.")

                # Delete the original command for extra privacy
        try:
            await ctx.message.delete(delay=2)
        except Exception:
            pass


    @commands.command()
    @commands.has_permissions(administrator=True)
    async def reset_game(self, ctx, confirm: str = ""):
        """
        HARD RESET: wipe players, votes, timers, logs.
        Usage: !reset_game CONFIRM
        """
        if confirm != "CONFIRM":
            return await ctx.reply("This will ERASE the current game state. Use `!reset_game CONFIRM` to proceed.")

        # Cancel timers
        if game.day_timer_task and not game.day_timer_task.done():
            game.day_timer_task.cancel()
            game.day_timer_task = None
        if game.night_timer_task and not game.night_timer_task.done():
            game.night_timer_task.cancel()
            game.night_timer_task = None

        # Wipe state
        game.players = {}
        game.votes = {}
        game.day_channel_id = None
        game.current_day_number = 0
        game.day_deadline_epoch = None
        game.night_channel_id = None
        game.night_deadline_epoch = None
        game.next_day_channel_id = None
        game.night_actions = []
        game.game_over = False  # ready for a fresh game

        save_state("state.json")
        await ctx.send("🧹 Game state wiped. Ready for a new setup.")
        
                # Delete the original command for extra privacy
        try:
            await ctx.message.delete(delay=2)
        except Exception:
            pass