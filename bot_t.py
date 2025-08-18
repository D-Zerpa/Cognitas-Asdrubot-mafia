import os, json, asyncio
from math import ceil
from dotenv import load_dotenv
import discord
from discord.ext import commands

# ================== CONFIG / TOKEN ==================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in .env")

# ================== INTENTS ==================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ================== PERSISTENCE ==================
DATA_PATH = "game/players.json"   # runtime state (players, votes, day, etc.)
ROLES_PATH = "game/roles.json"    # role definitions

def load_roles() -> dict:
    """
    Load roles from roles.json.
    """
    try:
        with open(ROLES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("roles.json must be an object {code: {...}}")
            normalized = {}
            for k, v in data.items():
                code = str(k).upper()
                v = v or {}
                v.setdefault("name", code)
                v.setdefault("faction", "NEUTRAL")
                v.setdefault("defaults", {})
                v["defaults"].setdefault("vote_weight_base", 1)
                normalized[code] = v
            return normalized
    except FileNotFoundError:
        raise FileNotFoundError("roles.json not found. Place it next to bot.py.")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid roles.json (JSON): {e}")

ROLES = load_roles()

players = {}
votes = {}
day_channel_id = None
current_day_number = 1
day_timer_task = None

def load_state():
    global players, votes, day_channel_id, current_day_number, day_deadline_epoch
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    players = data.get("players", {})
    votes = data.get("votes", {})
    day_channel_id = data.get("day_channel_id", None)
    current_day_number = data.get("current_day_number", 1)
    day_deadline_epoch = data.get("day_deadline_epoch", None)

def save_state():
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "players": players,
            "votes": votes,
            "day_channel_id": day_channel_id,
            "current_day_number": current_day_number,
            "day_deadline_epoch": day_deadline_epoch
        }, f, ensure_ascii=False, indent=2)


load_state()

# ================== HELPERS: ROLES / EFFECTS / FLAGS ==================
def role_of(uid: str) -> dict:
    code = players[uid]["role"]
    return ROLES.get(code, {})

def role_defaults(uid: str) -> dict:
    return role_of(uid).get("defaults", {})

def effects_of(uid: str) -> list:
    return players[uid].get("effects", [])

def flags_of(uid: str) -> dict:
    return players[uid].get("flags", {})

def alive_ids():
    return [uid for uid, p in players.items() if p.get("alive", True)]

def base_threshold():
    return ceil(len(alive_ids()) / 2)

def expired(effect: dict) -> bool:
    """Expire by day number. If no 'expires_day', it doesn't expire."""
    exp = effect.get("expires_day")
    return exp is not None and exp < current_day_number

def compute_vote_weight(uid: str) -> int:
    """Vote weight = max(base, active temporary boosts)."""
    base = int(role_defaults(uid).get("vote_weight_base", 1))
    boosts = [
        int(e.get("value", 0))
        for e in effects_of(uid)
        if e.get("type") == "vote_boost" and not expired(e)
    ]
    return max([base] + boosts) if boosts else base

def compute_lynch_delta(uid: str) -> int:
    """
    Delta applied to the lynch threshold for the TARGET:
    - Zeno example: +1 once if not consumed (defaults.lynch_bonus_once + no 'zenon_bonus_consumed' effect).
    - Plotinus example: -1 while 'plotino_mark' is active (not expired).
    """
    delta = 0
    dfl = role_defaults(uid)

    # Example: Zeno (+1 once)
    if dfl.get("lynch_bonus_once", 0) == 1:
        consumed = any(e.get("type") == "zenon_bonus_consumed" for e in effects_of(uid))
        if not consumed:
            delta += 1

    # Example: Plotinus (-1 while marked)
    marked = any(e.get("type") == "plotino_mark" and not expired(e) for e in effects_of(uid))
    if marked:
        delta -= 1

    return delta

def vote_weight(uid: str) -> int:
    p = players.get(uid, {})
    if not p or not p.get("alive", True):
        return 0
    fl = flags_of(uid)
    if fl.get("silenced", False) or fl.get("absent", False):
        return 0
    return compute_vote_weight(uid)

def required_for_target(obj_uid: str) -> int:
    o = players.get(obj_uid, {})
    if not o or not o.get("alive", True):
        return 9999
    if flags_of(obj_uid).get("absent", False):
        return 9999
    req = base_threshold() + compute_lynch_delta(obj_uid)
    return max(1, req)

def totals_per_target() -> dict:
    totals = {}
    for voter_uid, target_uid in votes.items():
        if not target_uid:
            continue
        if target_uid not in players:
            continue
        if not players[target_uid].get("alive", True):
            continue
        if flags_of(target_uid).get("absent", False):
            continue
        w = vote_weight(voter_uid)
        if w <= 0:
            continue
        totals[target_uid] = totals.get(target_uid, 0) + w
    return totals

def parse_duration_to_seconds(text: str) -> int:
    """
    Parse duration strings like '1d12h30m', '24h', '90m', '3600s' into seconds.
    Default unit is hours if only a number is provided.
    """
    text = (text or "").strip().lower()
    if not text:
        return 0
    # if only number, treat as hours
    if text.isdigit():
        return int(text) * 3600
    total = 0
    num = ""
    for ch in text:
        if ch.isdigit():
            num += ch
        else:
            if not num:
                continue
            val = int(num)
            if ch == 'd':
                total += val * 86400
            elif ch == 'h':
                total += val * 3600
            elif ch == 'm':
                total += val * 60
            elif ch == 's':
                total += val
            num = ""
    if num:  # trailing number without unit -> hours
        total += int(num) * 3600
    return total

async def day_timer_worker(bot: commands.Bot, guild_id: int, channel_id: int):
    """
    Sends reminders and auto-closes the day channel at deadline.
    Respects persisted 'day_deadline_epoch'.
    """
    global day_timer_task, day_deadline_epoch
    try:
        if day_deadline_epoch is None:
            return

        guild = bot.get_guild(guild_id)
        if not guild:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return

        # Compute schedule of reminders based on total remaining
        import time
        now = int(time.time())
        remaining = max(0, day_deadline_epoch - now)

        # Build a list of (when_to_fire_epoch, message)
        schedule = []

        # Helper to schedule "X left" if it fits
        def schedule_if_left(seconds_left: int, label: str):
            fire_at = day_deadline_epoch - seconds_left
            if fire_at > now:
                schedule.append((fire_at, label))

        # Midpoint reminder if total >= 2h
        if remaining >= 2 * 3600:
            schedule.append((now + remaining // 2, "⏳ Halfway through the Day."))

        # Fixed checkpoints
        schedule_if_left(4 * 3600, "🌗 4 hours left.")
        schedule_if_left(3600,     "🕐 1 hour left.")
        schedule_if_left(15 * 60,  "⌛ 15 minutes left.")
        schedule_if_left(5 * 60,   "⌛ 5 minutes left.")
        schedule_if_left(60,       "⌛ 1 minute left.")

        # Sort by time
        schedule.sort(key=lambda x: x[0])

        # Post a pinned “ends at” info line
        await channel.send(f"🕒 Day ends at <t:{day_deadline_epoch}:F> (<t:{day_deadline_epoch}:R>).")

        # Sleep until each reminder and send it (skip if we’re past due)
        import asyncio, time
        for fire_at, label in schedule:
            delay = fire_at - int(time.time())
            if delay > 0:
                await asyncio.sleep(delay)
            # If day changed or deadline cleared, abort
            if day_deadline_epoch is None or channel_id != day_channel_id:
                return
            await channel.send(f"@everyone {label}")

        # Final sleep to the deadline
        final_delay = max(0, day_deadline_epoch - int(time.time()))
        if final_delay > 0:
            await asyncio.sleep(final_delay)

        # Time’s up: auto-close channel if still the active Day
        if channel_id == day_channel_id and day_deadline_epoch is not None:
            overw = channel.overwrites_for(guild.default_role)
            overw.send_messages = False
            await channel.set_permissions(guild.default_role, overwrite=overw)
            await channel.send("⏰ Time is up. **Day is over; channel closed.**")

        # Clear deadline (the day is considered finished by time)
        day_deadline_epoch = None
        save_state()

    finally:
        day_timer_task = None

async def check_threshold_and_close(ctx: commands.Context):
    """If someone reaches their threshold in the day channel, close the channel for writing."""
    if day_channel_id is None or ctx.channel.id != day_channel_id:
        return
    totals = totals_per_target()
    for obj_uid, total in totals.items():
        req = required_for_target(obj_uid)
        if total >= req:
            chan = ctx.guild.get_channel(day_channel_id)
            overw = chan.overwrites_for(ctx.guild.default_role)
            overw.send_messages = False
            await chan.set_permissions(ctx.guild.default_role, overwrite=overw)
            await chan.send(f"🗳️ Threshold reached: <@{obj_uid}> ({total}/{req}). **Channel closed.**")
            return

# ================== EVENTS ==================
@bot.event
async def on_ready():
    print(f"Connected as {bot.user} (id: {bot.user.id})")
    print(f"Loaded roles: {len(ROLES)} → {', '.join(list(ROLES.keys())[:8])}{'...' if len(ROLES)>8 else ''}")

    # Resume Day timer if needed
    global day_timer_task
    try:
        import time
        if day_channel_id and day_deadline_epoch and day_deadline_epoch > int(time.time()):
            guilds = bot.guilds
            # day_channel_id is per-guild; we assume single-game bot or the channel exists in one of the guilds
            # Create the timer task again
            if day_timer_task and not day_timer_task.done():
                day_timer_task.cancel()
            # We need the guild id; find the guild that has this channel id
            for g in guilds:
                if g.get_channel(day_channel_id):
                    day_timer_task = asyncio.create_task(day_timer_worker(bot, g.id, day_channel_id))
                    break
    except Exception as e:
        print("Failed to resume Day timer:", e)

# ================== ADMIN: ASSIGN / INFO ==================
@bot.command()
@commands.has_permissions(administrator=True)
async def assign(ctx, member: discord.Member, role_code: str):
    """
    Assign a role to a player and bind THIS channel as their private role channel.
    Usage: !assign @player ZENON
    """
    code = role_code.upper()
    if code not in ROLES:
        return await ctx.reply("❌ Unknown role (check roles.json).")
    uid = str(member.id)
    players.setdefault(uid, {})
    players[uid].update({
        "nick": member.display_name,
        "role": code,
        "channel_id": ctx.channel.id,
        "alive": True,
        "flags": players[uid].get("flags", {"silenced": False, "absent": False}),
        "effects": players[uid].get("effects", [])
    })
    save_state()

    # Ensure the player can see and speak in this channel
    overwrites = ctx.channel.overwrites
    overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    await ctx.channel.edit(overwrites=overwrites)

    await ctx.send(f"✅ Assigned **{ROLES[code]['name']}** to {member.mention} and bound to {ctx.channel.mention}.")

@bot.command()
@commands.has_permissions(administrator=True)
async def who(ctx, member: discord.Member = None):
    """Show someone's assigned role and bound channel (or yours if no arg)."""
    target = member or ctx.author
    info = players.get(str(target.id))
    if not info:
        return await ctx.reply("ℹ️ No role assigned.")
    role = ROLES.get(info["role"], {})
    channel = ctx.guild.get_channel(info.get("channel_id")) if info.get("channel_id") else None
    await ctx.send(
        f"👤 {target.mention} → **{role.get('name','?')}** ({info['role']}). "
        f"Channel: {channel.mention if channel else 'N/A'}"
    )

# ================== ADMIN: EFFECTS / FLAGS ==================
@bot.command()
@commands.has_permissions(administrator=True)
async def effect(ctx, member: discord.Member, etype: str, value: int = None, expires_in_days: int = None):
    """
    Add an effect to a player.
    Examples:
      !effect @Pythagoras vote_boost 2 1          # x2 vote weight, expires after 1 day
      !effect @Marked plotino_mark 0 1            # -1 lynch threshold (as long as active)
      !effect @Zeno zenon_bonus_consumed          # consume Zeno's +1 once
    """
    uid = str(member.id)
    if uid not in players:
        return await ctx.reply("Assign a role to that player first.")
    eff = {"type": etype}
    if value is not None:
        eff["value"] = int(value)
    if expires_in_days is not None:
        eff["expires_day"] = current_day_number + int(expires_in_days)
    players[uid].setdefault("effects", []).append(eff)
    save_state()
    await ctx.message.add_reaction("✨")
    await ctx.send(f"🎯 Effect added to {member.mention}: `{eff}`")

@bot.command()
@commands.has_permissions(administrator=True)
async def flag(ctx, member: discord.Member, key: str, value: int):
    """
    Set player flags (0/1):
      - silenced (cannot vote; you may also restrict speaking)
      - absent   (cannot vote or be voted)
      - alive    (0 = dead, 1 = alive)
    Example: !flag @Player silenced 1
    """
    uid = str(member.id)
    if uid not in players:
        return await ctx.reply("Assign a role to that player first.")
    if key == "alive":
        players[uid]["alive"] = bool(int(value))
    else:
        flags = players[uid].setdefault("flags", {})
        flags[key] = bool(int(value))
    save_state()
    await ctx.message.add_reaction("🛠️")
    await ctx.send(f"Flag `{key}` for {member.mention} = {bool(int(value))}")

# ================== DAY / VOTING ==================
@bot.command()
@commands.has_permissions(administrator=True)
async def start_day(ctx, duration: str = "24h"):
    """
    Start the Day phase in THIS channel with a duration.
    Examples:
      !start_day            -> 24h
      !start_day 12h        -> 12 hours
      !start_day 1h30m      -> 1 hour 30 minutes
      !start_day 90m        -> 90 minutes
    """
    global day_channel_id, votes, current_day_number, day_deadline_epoch, day_timer_task

    # Parse duration
    seconds = parse_duration_to_seconds(duration)
    if seconds <= 0:
        return await ctx.reply("Please provide a valid duration, e.g. `24h`, `1h30m`, `90m`.")

    # Set state
    import time
    day_channel_id = ctx.channel.id
    votes = {}
    current_day_number += 1
    day_deadline_epoch = int(time.time()) + seconds
    save_state()

    # Open channel for sending
    overw = ctx.channel.overwrites_for(ctx.guild.default_role)
    overw.send_messages = True
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overw)

    await ctx.send(
        f"🌞 **Day {current_day_number} begins.** Base threshold: **{base_threshold()}**.\n"
        f"Ends at <t:{day_deadline_epoch}:F> (<t:{day_deadline_epoch}:R>). Use `!vote @user`."
    )

    # Cancel any previous timer and start a new one
    if day_timer_task and not day_timer_task.done():
        day_timer_task.cancel()
    day_timer_task = asyncio.create_task(day_timer_worker(bot, ctx.guild.id, ctx.channel.id))

@bot.command()
@commands.has_permissions(administrator=True)
async def end_day(ctx):
    """Manually end the Day now and close the channel (cancels timer)."""
    global day_deadline_epoch, day_timer_task
    if ctx.channel.id != day_channel_id:
        return await ctx.reply("This is not the active Day channel.")
    # Close channel
    overw = ctx.channel.overwrites_for(ctx.guild.default_role)
    overw.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overw)
    await ctx.send("🛑 Day ended by a moderator. Channel closed.")
    # Clear/cancel timer
    day_deadline_epoch = None
    save_state()
    if day_timer_task and not day_timer_task.done():
        day_timer_task.cancel()
        day_timer_task = None

@bot.command()
async def vote(ctx, member: discord.Member):
    """Cast a vote (strict: must !unvote before changing)."""
    if day_channel_id != ctx.channel.id:
        return await ctx.reply("This is not the Day voting channel.")
    voter = str(ctx.author.id)
    target = str(member.id)

    # checks if the user already voted
    if voter in votes:
        current = votes[voter]
        if current == target:
            return await ctx.reply(f"You already voted for <@{target}>.")
        return await ctx.reply(
            f"You already have an active vote on <@{current}>. Use `!unvote` first to change it."
        )

    # validations
    if voter not in players or not players[voter].get("alive", True):
        return await ctx.reply("You cannot vote.")
    if flags_of(voter).get("silenced", False):
        return await ctx.reply("You are silenced.")
    if target not in players or not players[target].get("alive", True):
        return await ctx.reply("That player is not available.")
    if flags_of(target).get("absent", False):
        return await ctx.reply("That player is absent today (cannot be voted).")

    votes[voter] = target
    save_state()
    await ctx.message.add_reaction("🗳️")
    await ctx.send(f"Vote from <@{voter}> → <@{target}> (weight {vote_weight(voter)}).")
    await check_threshold_and_close(ctx)


@bot.command()
async def unvote(ctx):
    """Remove your vote in the Day channel."""
    if day_channel_id != ctx.channel.id:
        return await ctx.reply("This is not the Day voting channel.")
    voter = str(ctx.author.id)
    if votes.pop(voter, None) is not None:
        save_state()
        await ctx.message.add_reaction("✅")
        await check_threshold_and_close(ctx)
    else:
        await ctx.reply("You had no active vote.")

@bot.command()
async def status(ctx):
    """Show current vote totals and required thresholds per target."""
    if day_channel_id != ctx.channel.id:
        return await ctx.reply("This is not the Day voting channel.")
    totals = totals_per_target()
    lines = [f"🗓️ Day: **{current_day_number}**  |  Base threshold: **{base_threshold()}**"]
    if not totals:
        lines.append("No votes yet.")
    else:
        for obj_uid, total in totals.items():
            req = required_for_target(obj_uid)
            lines.append(f"- <@{obj_uid}> → **{total}/{req}**")
    await ctx.send("\n".join(lines))

@bot.command()
async def myvote(ctx):
    """Show your current vote, if any."""
    voter = str(ctx.author.id)
    tgt = votes.get(voter)
    if not tgt:
        return await ctx.reply("You have no active vote.")
    await ctx.reply(f"Your current vote is on <@{tgt}> (weight {vote_weight(voter)}).")

@bot.command(name="votes")
async def votes_breakdown(ctx):
    """
    Show per-voter breakdown grouped by target, including each vote's weight.
    (Day channel only)
    """
    if day_channel_id != ctx.channel.id:
        return await ctx.reply("This is not the Day voting channel.")

    if not votes:
        return await ctx.send("No votes yet.")

    # Build groups: target -> [(voter_uid, weight)]
    grouped = {}
    for voter_uid, target_uid in votes.items():
        # ignore invalid/expired voters automatically (weight 0 won't appear in totals anyway)
        w = vote_weight(voter_uid)
        if w <= 0:
            continue
        grouped.setdefault(target_uid, []).append((voter_uid, w))

    # Compose message
    lines = [f"🗓️ Day **{current_day_number}** | Base threshold: **{base_threshold()}**", ""]
    # Detailed breakdown
    for target_uid, entries in sorted(grouped.items(), key=lambda kv: kv[0]):
        req = required_for_target(target_uid)
        subtotal = sum(w for _, w in entries)
        lines.append(f"🎯 Target <@{target_uid}> — **{subtotal}/{req}**")
        for voter_uid, w in sorted(entries, key=lambda x: (-x[1], x[0])):  # heavier votes first
            lines.append(f"  • <@{voter_uid}> (w={w})")
        lines.append("")  # blank line between targets

    # Totals summary (same as !status but kept here for convenience)
    totals = totals_per_target()
    if totals:
        lines.append("**Totals:**")
        for target_uid, total in totals.items():
            req = required_for_target(target_uid)
            lines.append(f"- <@{target_uid}> → **{total}/{req}**")

    msg = "\n".join(lines)
    # Discord has a message length limit; for very large lobbies you might paginate.
    await ctx.send(msg if len(msg) < 1800 else (msg[:1700] + "\n… (truncated)"))

@bot.command()
@commands.has_permissions(administrator=True)  # only mods/admins
async def clearvotes(ctx):
    """Clear all current votes (admin only)."""
    global votes
    votes = {}
    save_state()
    await ctx.send("🗑️ All votes have been cleared.")

# ================== LIVENESS / DEBUG ==================
@bot.command()
async def ping(ctx):
    await ctx.reply("pong 🏓")

@bot.command()
@commands.is_owner()
async def shutdown(ctx):
    await ctx.send("👋 Shutting down…")
    await bot.close()

# ================== RUN ==================
bot.run(TOKEN)

