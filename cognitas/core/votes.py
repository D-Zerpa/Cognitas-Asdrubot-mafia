from __future__ import annotations
import math, time
import discord
from discord.ext import commands
from .state import game
from .storage import save_state

# ---------- Helpers (names, hidden voters, etc.) ----------

def _player_record(uid: str) -> dict:
    return game.players.get(uid, {})

def _player_name(uid: str) -> str:
    return _player_record(uid).get("name", uid)

def _is_hidden_voter(uid: str) -> bool:
    return bool(_player_record(uid).get("flags", {}).get("hidden_vote", False))

def _alive_uids() -> list[str]:
    return [uid for uid, p in game.players.items() if p.get("alive", True)]

def _majority_needed() -> int:
    alive = len(_alive_uids())
    return math.floor(alive / 2) + 1 if alive > 0 else 1

def _group_votes_by_target() -> dict[str, list[str]]:
    by_target: dict[str, list[str]] = {}
    for voter, target in game.votes.items():
        by_target.setdefault(target, []).append(voter)
    return by_target

def _progress_bar(current: int, needed: int, width: int = 10) -> str:
    if needed <= 0: needed = 1
    filled = max(0, min(width, round((current / needed) * width)))
    return "█" * filled + "░" * (width - filled)

def _remaining_time_str() -> str | None:
    # If you store day_deadline_epoch in seconds
    dl = getattr(game, "day_deadline_epoch", None)
    if not dl: 
        return None
    try:
        ts = int(dl)
        # Discord relative timestamp
        return f"<t:{ts}:R>"
    except Exception:
        return None

# For hidden voters numbering (XXXX-1, XXXX-2, ...)
def _format_voter_list(voters: list[str], use_numbered_hidden: bool = True) -> str:
    hidden_counter = 0
    labels: list[str] = []
    for uid in voters:
        if _is_hidden_voter(uid):
            if use_numbered_hidden:
                hidden_counter += 1
                labels.append(f"XXXX-{hidden_counter}")
            else:
                labels.append("XXXX")
        else:
            labels.append(_player_name(uid))
    return ", ".join(labels) if labels else "—"

# ---------- Core vote operations (unchanged) ----------

async def vote(ctx: commands.Context, member: discord.Member):
    voter = str(ctx.author.id)
    target = str(member.id)
    if voter not in game.players or not game.players[voter].get("alive", True):
        return await ctx.reply("You must be a registered and alive player to vote.")
    if target not in game.players or not game.players[target].get("alive", True):
        return await ctx.reply("Target must be a registered and alive player.")
    game.votes[voter] = target
    save_state("state.json")
    await ctx.reply(f"✅ Vote registered: `{_player_name(voter)}` → `{_player_name(target)}`")

async def unvote(ctx: commands.Context):
    voter = str(ctx.author.id)
    if voter in game.votes:
        del game.votes[voter]
        save_state("state.json")
        return await ctx.reply("✅ Your vote has been cleared.")
    await ctx.reply("You have no active vote.")

async def myvote(ctx: commands.Context):
    voter = str(ctx.author.id)
    target = game.votes.get(voter)
    if not target:
        return await ctx.reply("You have no active vote.")
    await ctx.reply(f"Your current vote: `{_player_name(voter)}` → `{_player_name(target)}`")

async def clearvotes(ctx: commands.Context):
    game.votes.clear()
    save_state("state.json")
    await ctx.reply("🧹 All votes cleared.")

# ---------- Fancy EMBED outputs ----------

async def votes_breakdown(ctx: commands.Context):
    """
    Pretty vote breakdown embed.
    - Hidden voters are shown as 'XXXX' (numbered).
    - Shows per-target bars towards majority.
    - Shows non-voters at the bottom.
    """
    by_target = _group_votes_by_target()
    majority = _majority_needed()
    day_no = getattr(game, "current_day_number", None)
    rt = _remaining_time_str()

    embed = discord.Embed(
        title=f"Vote Tally — Day {day_no}" if day_no else "Vote Tally",
        description=f"Majority needed: **{majority}**" + (f" • Ends {rt}" if rt else ""),
        color=0x3498DB,
    )

    if not game.votes:
        embed.description += "\n\n*No votes have been cast.*"
    else:
        # Sort by most votes, then by target name
        for target, voters in sorted(by_target.items(), key=lambda kv: (-len(kv[1]), _player_name(kv[0]).lower())):
            tname = _player_name(target)
            count = len(voters)
            bar = _progress_bar(count, majority)
            voters_fmt = _format_voter_list(voters, use_numbered_hidden=True)
            embed.add_field(
                name=f"{tname} — {count} / {majority} {bar}",
                value=voters_fmt,
                inline=False
            )

    # Non-voters
    alive = set(_alive_uids())
    voted = set(game.votes.keys())
    non_voters = [uid for uid in alive if uid not in voted]
    if non_voters:
        non_list = ", ".join(_player_name(uid) for uid in sorted(non_voters, key=_player_name))
        embed.add_field(name="Non-voters", value=non_list, inline=False)

    embed.set_footer(text="Asdrubot v2.0 — Voting UI")
    await ctx.reply(embed=embed)

async def status(ctx: commands.Context):
    """
    Day status embed (compact).
    - Hidden voters masked as 'XXXX'.
    - Shows a compact per-target line with counts and voters.
    """
    by_target = _group_votes_by_target()
    majority = _majority_needed()
    day_no = getattr(game, "current_day_number", None)
    rt = _remaining_time_str()

    embed = discord.Embed(
        title=f"Day {day_no} Status" if day_no else "Day Status",
        description=f"Majority needed: **{majority}**" + (f" • Ends {rt}" if rt else ""),
        color=0x2ECC71,
    )

    if not game.votes:
        embed.add_field(name="Votes", value="No votes have been cast.", inline=False)
    else:
        lines: list[str] = []
        # Deterministic ordering
        for target, voters in sorted(by_target.items(), key=lambda kv: (-len(kv[1]), _player_name(kv[0]).lower())):
            tname = _player_name(target)
            voters_fmt = _format_voter_list(voters, use_numbered_hidden=True)
            lines.append(f"**{tname}** — **{len(voters)}** ({voters_fmt})")
        embed.add_field(name="Votes", value="\n".join(lines), inline=False)

    # End-day requests (2/3)
    end_set = getattr(game, "end_day_votes", set())
    if isinstance(end_set, set):
        need_end = math.ceil((2 * len(_alive_uids())) / 3) if _alive_uids() else 0
        embed.add_field(
            name="End-Day Requests",
            value=f"{len(end_set)}/{need_end} players have requested to end the Day.",
            inline=False
        )

    embed.set_footer(text="Asdrubot v2.0 — Voting UI")
    await ctx.reply(embed=embed)



async def request_end_day(ctx: commands.Context):
    """Register a player's request to end the Day early (2/3 of alive players)."""
    uid = str(ctx.author.id)
    if uid not in game.players or not game.players[uid].get("alive", True):
        return await ctx.reply("You must be a registered and alive player to request end of Day.")
    # ensure set exists
    end_set = getattr(game, "end_day_votes", None)
    if not isinstance(end_set, set):
        end_set = set()
        game.end_day_votes = end_set
    # add request
    end_set.add(uid)
    save_state("state.json")

    alive = [x for x in game.players if game.players[x].get("alive", True)]
    need = math.ceil( (2*len(alive)) / 3 ) if alive else 0
    have = len(end_set)
    await ctx.reply(f"🛎️ End-Day request registered ({have}/{need}).")

    if need and have >= need:
        # reached threshold → close the Day
        from . import phases
        await phases.end_day(ctx, closed_by_threshold=True)
