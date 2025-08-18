import discord
from discord.ext import commands
from ..core.state import game
from ..core.storage import save_state

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def assign(self, ctx, member: discord.Member, role_code: str):
        """Assign a role to a player and bind THIS channel as their private channel."""
        code = role_code.upper()
        if code not in game.roles:
            return await ctx.reply("❌ Unknown role (check roles.json).")
        uid = str(member.id)
        game.players.setdefault(uid, {})
        game.players[uid].update({
            "nick": member.display_name,
            "role": code,
            "channel_id": ctx.channel.id,
            "alive": True,
            "flags": game.players[uid].get("flags", {"silenced": False, "absent": False}),
            "effects": game.players[uid].get("effects", [])
        })
        save_state("players.json")

        overwrites = ctx.channel.overwrites
        overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        await ctx.channel.edit(overwrites=overwrites)

        await ctx.send(f"✅ Assigned **{game.roles[code]['name']}** to {member.mention} and bound to {ctx.channel.mention}.")

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
        save_state("players.json")
        await ctx.message.add_reaction("✨")
        await ctx.send(f"🎯 Effect added to {member.mention}: `{eff}`")

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
        save_state("players.json")
        await ctx.message.add_reaction("🛠️")
        await ctx.send(f"Flag `{key}` for {member.mention} = {bool(int(value))}")
