from __future__ import annotations
import math
import discord
from discord.ext import commands
from .state import game
from .storage import save_state

# -------------- Helpers for names (supports hidden votes) --------------

def _player_record(uid: str) -> dict:
    return game.players.get(uid, {})

def _player_name(uid: str) -> str:
    return _player_record(uid).get("name", uid)

def _is_hidden_voter(uid: str) -> bool:
    flags = _player_record(uid).get("flags", {})
    return bool(flags.get("hidden_vote", False))

def format_voter_name(uid: str, hidden_counter: dict | None = None) -> str:
    """
    Returns display name for a voter.
    - If the voter has hidden_vote=True, show "XXXX" (or "XXXX-1", "XXXX-2" if a counter dict is provided).
    - Otherwise show their stored display name.
    """
    if _is_hidden_voter(uid):
        if hidden_counter is not None:
            hidden_counter["n"] = hidden_counter.get("n", 0) + 1
            return f"XXXX-{hidden_counter['n']}"
        return "XXXX"
    return _player_name(uid)

def _alive_uids() -> list[str]:
    return [uid for uid, p in game.players.items() if p.get("alive", True)]

# -------------- Core vote ops (unchanged logic; presentation updated) --------------

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

# -------------- Breakdown & status (with hidden vote presentation) --------------

def _group_votes_by_target() -> dict[str, list[str]]:
    by_target: dict[str, list[str]] = {}
    for voter, target in game.votes.items():
        by_target.setdefault(target, []).append(voter)
    return by_target

async def votes_breakdown(ctx: commands.Context):
    """
    Public breakdown of votes. Honors hidden_vote flag:
    - Voters with hidden_vote=True are shown as "XXXX" (or numbered variants).
    - Tally is computed normally.
    """
    if not game.votes:
        return await ctx.reply("No votes have been cast.")

    by_target = _group_votes_by_target()
    hidden_counter = {"n": 0}

    lines: list[str] = []
    for target, voters in sorted(by_target.items(), key=lambda kv: (-len(kv[1]), _player_name(kv[0]).lower())):
        target_name = _player_name(target)
        # Format voter list with hidden handling
        formatted_voters = [format_voter_name(v, hidden_counter) for v in voters]
        voter_list = ", ".join(formatted_voters)
        lines.append(f"**{target_name}** — **{len(voters)}** votes: {voter_list}")

    # Optional: show non-voters
    alive = set(_alive_uids())
    voted = set(game.votes.keys())
    non_voters = [uid for uid in alive if uid not in voted]
    if non_voters:
        non_list = ", ".join(_player_name(uid) for uid in non_voters)
        lines.append(f"\nNon-voters: {non_list}")

    text = "\n".join(lines)
    await ctx.reply(text)

async def status(ctx: commands.Context):
    """
    Public status for the Day: shows current tally with hidden votes masked.
    """
    day_no = getattr(game, "current_day_number", None)
    header = f"**Day {day_no} Status**" if day_no else "**Day Status**"

    if not game.votes:
        return await ctx.reply(f"{header}\nNo votes have been cast.")

    by_target = _group_votes_by_target()
    hidden_counter = {"n": 0}

    lines: list[str] = []
    for target, voters in sorted(by_target.items(), key=lambda kv: (-len(kv[1]), _player_name(kv[0]).lower())):
        tgt = _player_name(target)
        voters_fmt = ", ".join(format_voter_name(v, hidden_counter) for v in voters)
        lines.append(f"{tgt}: **{len(voters)}** ({voters_fmt})")

    await ctx.reply(f"{header}\n" + "\n".join(lines))

# -------------- Two-thirds end-day request (unchanged logic) --------------

async def request_end_day(ctx: commands.Context):
    """
    A player requests to end the Day without lynch.
    When >= 2/3 of alive players request it, the Day ends.
    """
    voter = str(ctx.author.id)
    if voter not in _alive_uids():
        return await ctx.reply("Only alive players can request to end the Day.")

    end_set = getattr(game, "end_day_votes", set())
    if not isinstance(end_set, set):
        end_set = set(end_set)  # migrate if older saves
    end_set.add(voter)
    game.end_day_votes = end_set

    alive_count = len(_alive_uids())
    needed = math.ceil((2 * alive_count) / 3)
    save_state("state.json")

    remaining = max(0, needed - len(end_set))
    await ctx.reply(f"🕯️ End-day request registered. **{len(end_set)}/{needed}** votes. {('Ready to end.' if remaining == 0 else f'{remaining} more needed.')}")

# (If you have an admin-only 'votes()' alias for votes_breakdown, ensure it calls the same function)
