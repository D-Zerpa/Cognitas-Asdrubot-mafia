from __future__ import annotations

import math
import random

import discord
from discord.ext import commands

from .state import game
from .storage import save_state  # async
from .logs import log_event
from . import phases
from ..status import engine as SE
import importlib

# Optional lunar provider (expansion-defined)
try:
    # Import 'cognitas.core.lunar' if present; otherwise disable gracefully.
    lunar = importlib.import_module(f"{__package__}.lunar")
except Exception:
    lunar = None

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

def _alive_display_names(uids: list[str], *, max_names: int = 24) -> str:
    """
    Returns a human-friendly list of alive player names (or mentions).
    Truncates if too long and appends '… (+N more)'.
    """
    players = getattr(game, "players", {}) or {}
    names: list[str] = []
    for uid in uids[:max_names]:
        p = players.get(uid) or {}
        label = p.get("name") or p.get("alias") or f"<@{uid}>"
        names.append(f"`{label}`")
    extra = len(uids) - len(names)
    if extra > 0:
        names.append(f"… (+{extra} more)")
    return ", ".join(names) if names else "—"

# ---------- Voting logic (simple majority + boosts & target extras) ----------

def _voter_vote_value(voter_id: str) -> float:
    """
    Status-aware vote value:
      - 0 if dead or any status blocks voting (e.g., Wounded)
      - base 1.0 modified by active statuses (e.g., Double vote +1.0, Sanctioned -0.5 per stack)
    """
    pdata = _player_record(voter_id)
    if not pdata.get("alive", True):
        return 0.0

    # If any status blocks vote, or computed weight == 0, ballot is invalid
    chk = SE.check_action(game, voter_id, "vote")
    if not chk.get("allowed", True):
        return 0.0

    weight = SE.compute_vote_weight(game, voter_id, base=1.0)
    return max(0.0, float(weight))


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

def _tally_votes_simple_plus_boosts() -> dict[str, float]:
    """
    Totals by target, summing each voter's status-aware value (can be fractional).
    """
    totals: dict[str, float] = {}
    for voter_id, target_id in (getattr(game, "votes", {}) or {}).items():
        val = _voter_vote_value(voter_id)
        if val <= 0.0:
            continue
        totals[target_id] = totals.get(target_id, 0.0) + val
    return totals

def _fmt_num(x: float) -> str:
    s = f"{x:.1f}"
    return s[:-2] if s.endswith(".0") else s

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

        # Status check: can this user vote right now?
    chk = SE.check_action(game, voter_id, "vote")
    if not chk.get("allowed", True):
        return await ctx.reply("You can't vote right now.", ephemeral=True)

    # Weight must be > 0 (e.g., Sanctioned x2 -> 0)
    if _voter_vote_value(voter_id) <= 0.0:
        return await ctx.reply("You can't vote right now.", ephemeral=True)

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
                name=f"{tname} — **{_fmt_num(cur)} / {need}** {bar}",
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

    embed.set_footer(text="Asdrubot v3.0 — Voting UI")
    await ctx.reply(embed=embed)

async def status(ctx):
    """
    Global game status:
      - Current phase (Day/Night) and number
      - Lunar phase (emoji + name)
      - Time remaining (relative)
      - Alive players (count + list)
    """
    phase = (getattr(game, "phase", "day") or "day").lower()
    day_no = int(getattr(game, "current_day_number", 1) or 1)

    # Lunar (optional)
    if lunar and hasattr(lunar, "current"):
        try:
            _, lunar_label = lunar.current(game)
        except Exception:
            lunar_label = "—"
    else:
        lunar_label = "—"

    # Deadline
    if phase == "day":
        deadline = getattr(game, "day_deadline_epoch", None)
    else:
        deadline = getattr(game, "night_deadline_epoch", None)
    time_left = f"<t:{int(deadline)}:R>" if deadline else "—"

    # Alive players
    alive_uids = _alive_uids()
    alive_count = len(alive_uids)
    alive_list = _alive_display_names(sorted(alive_uids))  # sorted by uid; change if you prefer by name

    # Embed
    color = 0xF1C40F if phase == "day" else 0x2C3E50
    lines = [
        f"**Phase:** {'🌞 Day' if phase == 'day' else '🌙 Night'}",
        f"**Counter:** {('Day' if phase == 'day' else 'Night')} {day_no}",
        f"**Time left:** {time_left}",
    ]
    if lunar_label and lunar_label != "—":
        lines.insert(2, f"**Lunar:** {lunar_label}")  # insert after Counter

    embed = discord.Embed(
        title="Game Status",
        description="\n".join(lines),
        color=color,
    )
    embed.add_field(name=f"Alive players ({alive_count})", value=alive_list, inline=False)

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

    # Keep a local set for operations, persist as list for JSON safety
    raw = getattr(game, "end_day_votes", [])
    end_set = set(raw if isinstance(raw, (list, set, tuple)) else [])
    end_set.add(uid)
    game.end_day_votes = list(end_set)
    await save_state()


    alive = _alive_uids()
    need = math.ceil((2 * len(alive)) / 3) if alive else 0
    have = len(end_set)
    await ctx.reply(f"🛎️ End-Day request registered ({have}/{need}).", ephemeral=True)

    if need and have >= need:
        await phases.end_day(ctx, closed_by_threshold=True)
