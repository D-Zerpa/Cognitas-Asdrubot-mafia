from __future__ import annotations

import math
import random
from typing import Dict, Tuple

import discord
from discord.ext import commands

from .state import game
from .storage import save_state  # async
from .logs import log_event
from . import phases


# ---------- Helpers (names, hidden voters, etc.) ----------

def _player_record(uid: str) -> dict:
    return (getattr(game, "players", {}) or {}).get(uid, {})  # safe

def _player_name(uid: str) -> str:
    p = _player_record(uid)
    return p.get("alias") or p.get("name") or p.get("display_name") or uid

def _is_hidden_voter(uid: str) -> bool:
    return bool(_player_record(uid).get("flags", {}).get("hidden_vote", False))

def _glitch_name(length: int = 6) -> str:
    """Visual 'glitched' name for anonymous votes (no identity leak)."""
    base_chars = "█▓▒░▞▚▛▜▟#@$%&"
    zalgo_marks = ["̴","̵","̶","̷","̸","̹","̺","̻","̼","̽","͜","͝","͞","͟","͠","͢"]
    out = []
    for _ in range(length):
        c = random.choice(base_chars)
        if random.random() < 0.5:
            c += "".join(random.choice(zalgo_marks) for _ in range(random.randint(1, 3)))
        out.append(c)
    return "".join(out)

def _alive_uids() -> list[str]:
    players = getattr(game, "players", {}) or {}
    return [uid for uid, p in players.items() if p.get("alive", True)]


# ---------- Voting logic (simple majority + boosts & target extras) ----------

def _voter_vote_value(voter_id: str) -> int:
    """
    Value contributed by a voter's ballot:
      - default: 1
      - + voting_boost (if present, non-negative int)
      - 0 if the voter is dead or has 'no_vote'/'silenced' flags
    """
    pdata = _player_record(voter_id)
    if not pdata.get("alive", True):
        return 0
    flags = pdata.get("flags", {}) or {}
    if flags.get("no_vote") or flags.get("silenced"):
        return 0
    boost = 0
    try:
        boost = int(flags.get("voting_boost", 0))
    except Exception:
        boost = 0
    return max(0, 1 + max(0, boost))

def _target_extra_needed(target_id: str) -> int:
    """
    Extra votes required to lynch this target (adds to base majority).
    Accepts any of these flag names for convenience:
      - lynch_plus
      - lynch_resistance
      - needs_extra_votes
    """
    pdata = _player_record(target_id)
    flags = pdata.get("flags", {}) or {}
    for key in ("lynch_plus", "lynch_resistance", "needs_extra_votes"):
        if key in flags:
            try:
                return int(flags.get(key, 0))
            except Exception:
                return 0
    return 0

def _majority_base_needed() -> int:
    """Base majority by heads (alive): floor(n/2) + 1; minimum 1."""
    alive = len(_alive_uids())
    if alive <= 0:
        return 1
    return (alive // 2) + 1

def _needed_for_target(target_id: str) -> int:
    """Specific lynch threshold for a target: base + target's extra."""
    return _majority_base_needed() + _target_extra_needed(target_id)

def _group_votes_by_target() -> dict[str, list[str]]:
    by_target: dict[str, list[str]] = {}
    for voter, target in (getattr(game, "votes", {}) or {}).items():
        by_target.setdefault(target, []).append(voter)
    return by_target

def _tally_votes_simple_plus_boosts() -> dict[str, int]:
    """
    Totals by target summing each voter's value:
    - Each voter contributes 1 + voting_boost (if they have one).
    - Voters with value 0 (dead/silenced/no_vote) are ignored.
    """
    totals: dict[str, int] = {}
    for voter_id, target_id in (getattr(game, "votes", {}) or {}).items():
        val = _voter_vote_value(voter_id)
        if val <= 0:
            continue
        totals[target_id] = totals.get(target_id, 0) + val
    return totals

def _progress_bar(current: int, needed: int, width: int = 10) -> str:
    if needed <= 0:
        needed = 1
    filled = max(0, min(width, round((current / needed) * width)))
    return "█" * filled + "░" * (width - filled)


# ---------- Vote operations ----------

async def vote(ctx: commands.Context | any, member: discord.Member):
    voter_id = str(getattr(getattr(ctx, "author", None), "id", None) or getattr(getattr(ctx, "user", None), "id", None))
    target_id = str(member.id)

    # Validations
    if voter_id not in game.players or not game.players[voter_id].get("alive", True):
        return await ctx.reply("You must be a registered and alive player to vote.", ephemeral=True)
    if target_id not in game.players or not game.players[target_id].get("alive", True):
        return await ctx.reply("Target must be a registered and alive player.", ephemeral=True)
    if getattr(game, "phase", "day") != "day":
        return await ctx.reply("Voting is only available during the **Day**.", ephemeral=True)

    # Register vote
    if not isinstance(getattr(game, "votes", None), dict):
        game.votes = {}
    game.votes[voter_id] = target_id
    await save_state()  # async

    # Anonymous vote?
    incognito = bool(game.players.get(voter_id, {}).get("flags", {}).get("hidden_vote", False))
    if incognito:
        fake_name = _glitch_name()
        await ctx.reply(f"✅ Vote registered: `{fake_name}` → `{_player_name(target_id)}`", ephemeral=True)
    else:
        await ctx.reply(f"✅ Vote registered: `{_player_name(voter_id)}` → `{_player_name(target_id)}`", ephemeral=True)

    # Log (best-effort)
    try:
        await log_event(
            getattr(ctx, "bot", None), getattr(getattr(ctx, "guild", None), "id", None), "VOTE_CAST",
            voter_id=voter_id, target_id=target_id,
            voter_value=_voter_vote_value(voter_id),
            incognito=incognito
        )
    except Exception:
        pass

    # Auto-close Day by lynch if any target reached its threshold (base + extras)
    try:
        totals = _tally_votes_simple_plus_boosts()
        winner_id = next((tid for tid, total in totals.items() if total >= _needed_for_target(tid)), None)
        if winner_id:
            game.last_lynch_target = winner_id
            await save_state()
            await phases.end_day(ctx, closed_by_threshold=False, lynch_target_id=int(winner_id))
    except Exception:
        pass


async def unvote(ctx: commands.Context | any):
    voter = str(getattr(getattr(ctx, "author", None), "id", None) or getattr(getattr(ctx, "user", None), "id", None))
    if not isinstance(getattr(game, "votes", None), dict):
        game.votes = {}

    existed = game.votes.pop(voter, None)
    await save_state()

    if existed:
        return await ctx.reply("✅ Your vote has been cleared.", ephemeral=True)
    await ctx.reply("You have no active vote.", ephemeral=True)


async def myvote(ctx: commands.Context | any):
    voter = str(getattr(getattr(ctx, "author", None), "id", None) or getattr(getattr(ctx, "user", None), "id", None))
    target = (getattr(game, "votes", {}) or {}).get(voter)
    if not target:
        return await ctx.reply("You have no active vote.", ephemeral=True)
    await ctx.reply(f"Your current vote: `{_player_name(voter)}` → `{_player_name(target)}`", ephemeral=True)


async def clearvotes(ctx: commands.Context | any):
    if isinstance(getattr(game, "votes", None), dict):
        game.votes.clear()
    await save_state()
    await ctx.reply("🧹 All votes cleared.", ephemeral=True)


# ---------- Embeds ----------

def _remaining_time_str() -> str | None:
    dl = getattr(game, "day_deadline_epoch", None)
    if not dl:
        return None
    try:
        ts = int(dl)
        return f"<t:{ts}:R>"
    except Exception:
        return None

def _format_voter_list(voters: list[str]) -> str:
    labels: list[str] = []
    for uid in voters:
        if _is_hidden_voter(uid):
            labels.append(_glitch_name())
        else:
            labels.append(_player_name(uid))
    return ", ".join(labels) if labels else "—"

async def votes_breakdown(ctx: commands.Context | any):
    """
    UI: for each target shows current votes and its specific threshold (base + extras),
    plus a progress bar. Anonymous votes hide voter identities.
    """
    by_target = _group_votes_by_target()
    totals = _tally_votes_simple_plus_boosts()
    base_needed = _majority_base_needed()
    day_no = getattr(game, "current_day_number", None)
    rt = _remaining_time_str()

    embed = discord.Embed(
        title=f"Vote Tally — Day {day_no}" if day_no else "Vote Tally",
        description=f"Base majority needed: **{base_needed}**" + (f" • Ends {rt}" if rt else ""),
        color=0x3498DB,
    )

    if not getattr(game, "votes", None):
        embed.description += "\n\n*No votes have been cast.*"
    else:
        # Order by relative progress toward each target's own threshold, then by name
        def progress_ratio(tid: str) -> float:
            need = max(1, _needed_for_target(tid))
            return totals.get(tid, 0) / need

        for target_id, voters in sorted(
            by_target.items(),
            key=lambda item: (-progress_ratio(item[0]), _player_name(item[0]).lower()),
        ):
            tname = _player_name(target_id)
            cur = totals.get(target_id, 0)
            need = _needed_for_target(target_id)
            bar = _progress_bar(cur, need)
            voters_fmt = _format_voter_list(voters)
            embed.add_field(
                name=f"{tname} — **{cur} / {need}** {bar}",
                value=voters_fmt,
                inline=False
            )

    # Non-voters
    alive = set(_alive_uids())
    voted = set((getattr(game, "votes", {}) or {}).keys())
    non_voters = [uid for uid in alive if uid not in voted]
    if non_voters:
        embed.add_field(
            name="Non-voters",
            value=", ".join(_player_name(uid) for uid in sorted(non_voters, key=_player_name)),
            inline=False
        )

    embed.set_footer(text="Asdrubot v2.0 — Voting UI")
    await ctx.reply(embed=embed)

async def status(ctx: commands.Context | any):
    """
    Compact UI: one line per target with current total and target-specific threshold.
    """
    by_target = _group_votes_by_target()
    totals = _tally_votes_simple_plus_boosts()
    base_needed = _majority_base_needed()
    day_no = getattr(game, "current_day_number", None)
    rt = _remaining_time_str()

    embed = discord.Embed(
        title=f"Day {day_no} Status" if day_no else "Day Status",
        description=f"Base majority needed: **{base_needed}**" + (f" • Ends {rt}" if rt else ""),
        color=0x2ECC71,
    )

    if not getattr(game, "votes", None):
        embed.add_field(name="Votes", value="No votes have been cast.", inline=False)
    else:
        lines = []

        def progress_ratio(tid: str) -> float:
            need = max(1, _needed_for_target(tid))
            return totals.get(tid, 0) / need

        for target_id, _voters in sorted(
            by_target.items(),
            key=lambda item: (-progress_ratio(item[0]), _player_name(item[0]).lower()),
        ):
            tname = _player_name(target_id)
            cur = totals.get(target_id, 0)
            need = _needed_for_target(target_id)
            lines.append(f"**{tname}** — **{cur} / {need}**")

        embed.add_field(name="Votes", value="\n".join(lines), inline=False)

    embed.set_footer(text="Asdrubot v2.0 — Voting UI")
    await ctx.reply(embed=embed)


# ---------- End-Day by 2/3 requests (kept as you had it) ----------

async def request_end_day(ctx: commands.Context | any):
    """
    A player requests to end the Day early (needs 2/3 of alive players by heads).
    NOTE: This keeps your original simple set in memory; it is not persisted.
    """
    uid = str(getattr(getattr(ctx, "author", None), "id", None) or getattr(getattr(ctx, "user", None), "id", None))
    if uid not in game.players or not game.players[uid].get("alive", True):
        return await ctx.reply("You must be a registered and alive player to request end of Day.", ephemeral=True)

    end_set = getattr(game, "end_day_votes", None)
    if not isinstance(end_set, set):
        end_set = set()
        game.end_day_votes = end_set
    end_set.add(uid)
    await save_state()  # harmless even if set isn't serialized

    alive = _alive_uids()
    need = math.ceil((2 * len(alive)) / 3) if alive else 0
    have = len(end_set)
    await ctx.reply(f"🛎️ End-Day request registered ({have}/{need}).", ephemeral=True)

    if need and have >= need:
        await phases.end_day(ctx, closed_by_threshold=True)
