# Asdrubot Audit Code Dump
_(auto-generated for full-code audit)_


-----
## cognitas/core/actions.py

```python
# cognitas/core/actions.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional
from .state import game

PHASE_DAY = "day"
PHASE_NIGHT = "night"
PHASES = {PHASE_DAY, PHASE_NIGHT}


# ------------ Phase helpers ------------

def _normalize_phase(phase: str | None) -> str:
    p = (phase or "").strip().lower()
    return p if p in PHASES else PHASE_NIGHT  # default to night for legacy parity


def current_cycle_number(phase: str | None = None) -> int:
    """
    Returns the logical counter for the given phase.
    Convention:
      - Day N is "current_day_number".
      - Night N follows Day N (same N).
    When phase is omitted: use current game.phase to decide.
    """
    p = _normalize_phase(phase or getattr(game, "phase", PHASE_DAY))
    day_no = int(getattr(game, "current_day_number", 1) or 1)
    if p == PHASE_DAY:
        # During night we still consider "current day" to be the same number.
        return max(1, day_no)
    # night
    return max(1, day_no)


# ------------ Actions storage (per phase) ------------

def _ensure_actions_dict(attr: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Ensures an actions dict exists in game.<attr> and normalizes to:
      { "<N>": { "<uid>": { ...action dict... } } }
    Accepts legacy lists and normalizes them.
    """
    na = getattr(game, attr, None)
    if na is None:
        na = {}
        setattr(game, attr, na)
    if isinstance(na, dict):
        normalized: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for k, v in na.items():
            if isinstance(v, list):
                bucket: Dict[str, Dict[str, Any]] = {}
                for item in v:
                    if isinstance(item, dict):
                        uid = str(item.get("uid") or item.get("user_id") or "")
                        if uid:
                            bucket[uid] = item
                normalized[str(k)] = bucket
            elif isinstance(v, dict):
                inner: Dict[str, Dict[str, Any]] = {}
                for uid, act in v.items():
                    if isinstance(act, dict):
                        inner[str(uid)] = act
                normalized[str(k)] = inner
        setattr(game, attr, normalized)
        return normalized
    setattr(game, attr, {})
    return getattr(game, attr)


def _attr_for_phase(phase: str) -> str:
    p = _normalize_phase(phase)
    return "day_actions" if p == PHASE_DAY else "night_actions"


def _flag_for_phase(phase: str) -> str:
    p = _normalize_phase(phase)
    return "day_act" if p == PHASE_DAY else "night_act"


def get_action_bucket(phase: str, number: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    """
    Returns bucket for given phase & number: mapping uid -> action dict.
    """
    p = _normalize_phase(phase)
    attr = _attr_for_phase(p)
    store = _ensure_actions_dict(attr)
    n = number if number is not None else current_cycle_number(p)
    return store.get(str(n), {})


def get_logs(phase: str, number: Optional[int] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns action dicts for the given phase+number, optionally filtered by user_id.
    """
    bucket = get_action_bucket(phase, number)
    out: List[Dict[str, Any]] = []
    for uid, act in bucket.items():
        if user_id and str(uid) != str(user_id):
            continue
        if isinstance(act, dict):
            row = dict(act)
            row.setdefault("uid", str(uid))
            out.append(row)
    return out


def get_user_logs_all(phase: str, user_id: str) -> List[Tuple[int, Dict[str, Any]]]:
    """
    Returns list of (number, action_dict) for the given user across ALL numbers in the given phase.
    Sorted by number asc.
    """
    p = _normalize_phase(phase)
    attr = _attr_for_phase(p)
    store = _ensure_actions_dict(attr)
    rows: List[Tuple[int, Dict[str, Any]]] = []
    for k, bucket in store.items():
        try:
            n = int(k)
        except Exception:
            continue
        if not isinstance(bucket, dict):
            continue
        act = bucket.get(str(user_id))
        if isinstance(act, dict):
            row = dict(act)
            row.setdefault("uid", str(user_id))
            rows.append((n, row))
    rows.sort(key=lambda t: t[0])
    return rows


# ------------ Who can act / who acted ------------

def actors_for_phase(phase: str) -> List[str]:
    """
    Returns uids of alive players who are allowed to act in the given phase.
    Policy: player.alive == True AND player.flags[day_act/night_act] == True.
    """
    p = _normalize_phase(phase)
    flag_name = _flag_for_phase(p)
    players = getattr(game, "players", {}) or {}
    out: List[str] = []
    for uid, pdata in players.items():
        if not pdata or not pdata.get("alive", True):
            continue
        flags = pdata.get("flags", {}) or {}
        if bool(flags.get(flag_name, False)):
            out.append(uid)
    return out


def acted_uids(phase: str, number: Optional[int] = None) -> List[str]:
    """
    Returns uids with an action recorded for given phase+number.
    """
    bucket = get_action_bucket(phase, number)
    return sorted(bucket.keys())
```

-----
## cognitas/core/game.py

```python
import os
import discord
from .state import game       # tu GameState existente
from .roles import load_roles
from .storage import save_state
from .logs import log_event
import unicodedata


def _norm_key(s: str) -> str:
    """Normalize a key for case-insensitive lookup without accents."""
    if not isinstance(s, str):
        return ""
    # remove surrounding spaces and strip accents
    s = unicodedata.normalize("NFKD", s.strip())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.upper()

def _extract_role_defaults(role_def: dict) -> dict:
    """
    Get profile-aware defaults:
    - SMT:        role_def["flags"]
    - Others:     role_def["defaults"] | role_def["base_flags"] | role_def["abilities"]["defaults"]
    """
    if not isinstance(role_def, dict):
        return {}
    # SMT
    if isinstance(role_def.get("flags"), dict):
        return role_def["flags"]
    # Others
    if isinstance(role_def.get("defaults"), dict):
        return role_def["defaults"]
    if isinstance(role_def.get("base_flags"), dict):
        return role_def["base_flags"]
    abilities = role_def.get("abilities")
    if isinstance(abilities, dict) and isinstance(abilities.get("defaults"), dict):
        return abilities["defaults"]
    return {}

def _build_roles_index(roles_def) -> dict:
    """
    Build a robust index: normalized KEY -> role_def
    Accepts 'code' | 'id' | 'name' plus 'aliases' in any combination.
    """
    roles_list = []
    if isinstance(roles_def, dict):
        roles_list = list(roles_def.get("roles") or [])
    elif isinstance(roles_def, list):
        roles_list = roles_def

    idx = {}
    for r in roles_list:
        if not isinstance(r, dict):
            continue
        keys = []
        for k in (r.get("code"), r.get("id"), r.get("name")):
            if isinstance(k, str) and k.strip():
                keys.append(_norm_key(k))
        for a in (r.get("aliases") or []):
            if isinstance(a, str) and a.strip():
                keys.append(_norm_key(a))
        # register all variants pointing to the same role_def
        for key in keys:
            if key:
                idx[key] = r
    return idx

def _lookup_role(role_name: str, roles_index: dict, roles_def) -> dict | None:
    """Search index first (fast) and fall back to scanning JSON if needed."""
    key = _norm_key(role_name or "")
    role_def = roles_index.get(key)
    if role_def:
        return role_def

    # Defensive fallback (in case the index wasn't built yet)
    roles_list = []
    if isinstance(roles_def, dict):
        roles_list = list(roles_def.get("roles") or [])
    elif isinstance(roles_def, list):
        roles_list = roles_def

    for r in roles_list:
        if not isinstance(r, dict):
            continue
        main_key = _norm_key(r.get("code") or r.get("id") or r.get("name") or "")
        alias_hit = any(_norm_key(a) == key for a in (r.get("aliases") or []) if isinstance(a, str))
        if main_key == key or alias_hit:
            return r
    return None


async def set_channels(*, day: discord.TextChannel | None = None, admin: discord.TextChannel | None = None):
    if day is not None:
        game.day_channel_id = day.id
    if admin is not None:
        game.admin_channel_id = admin.id
    await save_state("state.json")

async def start(ctx, *, profile: str = "default", day_channel: discord.TextChannel | None = None, admin_channel: discord.TextChannel | None = None):
    """
    Start a game with a roles profile (default, smt, ...).
    - Load roles_{profile}.json (or fall back to default)
    - Reset basic counters
    - Set day/admin channels if provided
    """
    
    game.profile = profile.lower()
    game.roles_def = load_roles(game.profile)
    game.roles = _build_roles_index(game.roles_def)
    game.expansion = _load_expansion_for(game.profile)  # new


    # Minimal non-destructive resets of players
    game.votes = {}
    game.end_day_votes = set()
    game.game_over = False
    game.current_day_number = 0
    game.phase = "day"
    game.day_deadline_epoch = None
    game.night_deadline_epoch = None

    set_channels(day=day_channel or ctx.channel, admin=admin_channel)
    await save_state("state.json")

    chan = ctx.guild.get_channel(game.day_channel_id)
    await ctx.reply(
        f"🟢 **Game started** with profile **{game.profile}**.\n"
        f"Day channel: {chan.mention if chan else '#?'} | Roles file loaded."
    )
    await log_event(ctx.bot, ctx.guild.id, "GAME_START", profile=game.profile, day_channel_id=game.day_channel_id)


async def hard_reset(ctx_or_interaction):
    """
    Full reset compatible with:
    - commands.Context (ctx)  -> uses ctx.reply(...)
    - discord.Interaction     -> uses interaction.response / followup
    """
    # 1) clear memory
    game.players = {}
    game.votes = {}
    game.day_channel_id = None
    game.admin_channel_id = None
    game.default_day_channel_id = None
    game.current_day_number = 0
    game.day_deadline_epoch = None
    game.night_deadline_epoch = None
    game.profile = "default"
    game.roles_def = {}
    game.roles = {}
    game.night_actions = {}
    game.game_over = False
    # TODO: cancel timers if they exist

    # 2) delete files
    for path in ("state.json", "state.json.bak", "status.json", "status.json.bak"):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except Exception:
            pass

    # 3) persist empty state
    await save_state("state.json")

    # 4) respond to the user (ctx or interaction)
    try:
        if isinstance(ctx_or_interaction, discord.Interaction):
            interaction = ctx_or_interaction
            if not interaction.response.is_done():
                await interaction.response.send_message("🧹 Game state fully reset.", ephemeral=True)
            else:
                await interaction.followup.send("🧹 Game state fully reset.", ephemeral=True)
        else:
            # commands.Context
            await ctx_or_interaction.reply("🧹 Game state fully reset.")
    except Exception:
        pass

    # 5) log to the log channel (works for both)
    try:
        if isinstance(ctx_or_interaction, discord.Interaction):
            await log_event(ctx_or_interaction.client, ctx_or_interaction.guild.id, "GAME_RESET")
        else:
            await log_event(ctx_or_interaction.bot, ctx_or_interaction.guild.id, "GAME_RESET")
    except Exception:
        pass
 

async def finish(ctx, *, reason: str | None = None):
    game.game_over = True
    await save_state("state.json")
    await ctx.reply(f"🏁 **Game finished.** {('Reason: ' + reason) if reason else ''}".strip())
    await log_event(ctx.bot, ctx.guild.id, "GAME_FINISH", reason=reason or "-")


async def who(ctx, member: discord.Member | None = None):
    """
    Show player info (role if any) or a basic list.
    """
    if member:
        uid = str(member.id)
        pdata = game.players.get(uid)
        if not pdata:
            return await ctx.reply("Player not registered.")
        role = pdata.get("role") or "—"
        alive = "✅" if pdata.get("alive", True) else "☠️"
        return await ctx.reply(f"<@{uid}> — **{pdata.get('name','?')}** | Role: **{role}** | {alive}")
    # quick list if no member is passed
    alive = [u for u, p in game.players.items() if p.get("alive", True)]
    await ctx.reply(f"Alive players: {', '.join(f'<@{u}>' for u in alive) if alive else '—'}")

async def assign_role(ctx, member: discord.Member, role_name: str):
    """
    Assign a role to a player and apply defaults (SMT: 'flags').
    """
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.")

    role_def = _lookup_role(role_name, getattr(game, "roles", {}) or {}, getattr(game, "roles_def", {}))
    if not role_def:
        return await ctx.reply(f"Unknown role: `{role_name}`")

    game.players[uid]["role"] = role_name

    # Merge defaults/flags without overwriting existing values
    defaults = _extract_role_defaults(role_def)
    if defaults:
        flags = game.players[uid].setdefault("flags", {})
        for k, v in defaults.items():
            flags.setdefault(k, v)

    await save_state("state.json")
    await ctx.reply(f"🎭 Role **{role_name}** assigned to <@{uid}>.")
    await log_event(ctx.bot, ctx.guild.id, "ASSIGN", user_id=str(member.id), role=role_name)




def _load_expansion_for(profile: str):
    from ..expansions import get_registered
    cls = get_registered(profile)
    if cls:
        return cls()
    # Fallbacks
    if (profile or "").lower() in ("smt", "persona", "megaten"):
        from ..expansions.smt import SMTExpansion
        return SMTExpansion()
    from ..expansions.philosophers import PhilosophersExpansion
    return PhilosophersExpansion()

```

-----
## cognitas/core/johnbotjovi.py

```python
# cognitas/core/johnbotjovi.py
from __future__ import annotations

import io
import os
import random
from typing import Optional, Tuple

import discord

try:
    from PIL import Image, ImageOps, ImageDraw
    _PIL_OK = True
except Exception:
    _PIL_OK = False


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_IMG_DIR = os.path.join(_BASE_DIR, "img")

# Track used background files to avoid immediate repeats
_USED: set[str] = set()


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _coords_from_filename(fname: str) -> tuple[int | None, int | None]:
    """
    Extract (x, y) from filenames like:
      lynch02-960-240-.png
      whatever-960-240.png
      bg-120-300-extra.jpg
    We split on '-' and only accept tokens that are pure digits,
    so 'lynch02' is ignored but '960' and '240' are taken.
    """
    name, _ext = os.path.splitext(os.path.basename(fname))
    tokens = name.split("-")
    nums = [t for t in tokens if t.isdigit()]
    if len(nums) >= 2:
        try:
            return int(nums[-2]), int(nums[-1])
        except Exception:
            pass
    return None, None


def _pick_bg() -> tuple[str, tuple[int | None, int | None]]:
    """
    Pick a random background from _IMG_DIR and return (full_path, (x, y)).
    Cycles through images without repeating until the set is exhausted.
    """
    if not os.path.isdir(_IMG_DIR):
        raise FileNotFoundError(f"Backgrounds folder not found: {_IMG_DIR}")
    files = [f for f in os.listdir(_IMG_DIR) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    if not files:
        raise FileNotFoundError("No background images found in /core/img.")

    pool = [f for f in files if f not in _USED]
    if not pool:
        _USED.clear()
        pool = files[:]

    fname = random.choice(pool)
    _USED.add(fname)

    x, y = _coords_from_filename(fname)
    return os.path.join(_IMG_DIR, fname), (x, y)


def _make_circle_mask(size: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.ellipse((0, 0, size, size), fill=255)
    return m


async def _read_avatar_bytes(member: discord.Member, size: int = 128) -> bytes | None:
    """
    Robustly fetch the member avatar as PNG bytes across discord.py versions.
    Tries with_size/with_static_format, falls back to replace().
    Returns None if it cannot be read.
    """
    asset = getattr(member, "display_avatar", None) or getattr(member, "avatar", None)
    if asset is None:
        return None
    try:
        a = asset
        if hasattr(a, "with_size"):
            a = a.with_size(size)
        if hasattr(a, "with_static_format"):
            a = a.with_static_format("png")
        data = await a.read()
        if data:
            return data
    except Exception:
        pass
    try:
        a = asset
        if hasattr(a, "replace"):
            a = a.replace(size=size, static_format="png")
        data = await a.read()
        if data:
            return data
    except Exception:
        pass
    try:
        return await asset.read()
    except Exception:
        return None


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

async def lynch(member: discord.Member) -> Optional[discord.File]:
    """
    Create a lynch poster by pasting the user's circular avatar on a random background.
    Avatar placement:
      - Download avatar at 128px
      - Square-crop
      - Make circular (diameter = downloaded size)
      - Paste at (X, Y) from file name *without additional scaling*
    If coords are not present in the file name, avatar is centered.
    Returns a discord.File (PNG) or None if Pillow is not available.
    """
    if not _PIL_OK:
        return None

    # 1) Read avatar bytes (size=128, no extra scaling later)
    avatar_bytes = await _read_avatar_bytes(member, size=128)
    if not avatar_bytes:
        return None

    # 2) Pick background and read coords from filename
    bg_path, (px, py) = _pick_bg()

    # 3) Compose
    base = Image.open(bg_path).convert("RGBA")
    av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")

    # Square-crop avatar (keep the downloaded size)
    s = min(av.size)
    av_sq = ImageOps.fit(av, (s, s), centering=(0.5, 0.5))

    # Circular mask at exact size (no re-scaling)
    mask = _make_circle_mask(s)
    circle = Image.new("RGBA", (s, s))
    circle.paste(av_sq, (0, 0), mask=mask)

    # Default to center if coords not provided
    if px is None or py is None:
        bw, bh = base.size
        px = (bw - s) // 2
        py = (bh - s) // 2

    # Paste onto background
    base.paste(circle, (int(px), int(py)), circle)

    # 4) Output as PNG
    buf = io.BytesIO()
    base.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return discord.File(buf, filename=f"lynch_{member.id}.png")

```

-----
## cognitas/core/logs.py

```python
# cognitas/core/logs.py
from __future__ import annotations
import discord
from .state import game
from .storage import save_state

async def set_log_channel(channel: discord.TextChannel | None):
    """Store or remove the log channel in persistent state."""
    game.admin_log_channel_id = channel.id if channel else None
    await save_state("state.json")

async def log_event(bot: discord.Client, guild_id: int, kind: str, **data):
    """
    Send an embed to the configured log channel (if available).
    kind: 'PHASE_START', 'PHASE_END', 'VOTE_CAST', 'VOTE_CLEAR', 'VOTES_CLEARED',
          'END_DAY_REQUEST', 'LYNCH', 'GAME_START', 'GAME_RESET', 'GAME_FINISH', 'ASSIGN'
    """
    chan_id = getattr(game, "admin_log_channel_id", None)
    if not chan_id:
        return  # logging disabled
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    chan = guild.get_channel(chan_id)
    if not chan:
        return

    color_map = {
        "PHASE_START": 0x2ecc71,
        "PHASE_END": 0xe67e22,
        "VOTE_CAST": 0x3498db,
        "VOTE_CLEAR": 0x95a5a6,
        "VOTES_CLEARED": 0x95a5a6,
        "END_DAY_REQUEST": 0xf1c40f,
        "LYNCH": 0xc0392b,
        "GAME_START": 0x1abc9c,
        "GAME_RESET": 0x9b59b6,
        "GAME_FINISH": 0x7f8c8d,
        "ASSIGN": 0x8e44ad,
    }
    title_map = {
        "PHASE_START": "Phase started",
        "PHASE_END": "Phase ended",
        "VOTE_CAST": "Vote cast",
        "VOTE_CLEAR": "Vote cleared",
        "VOTES_CLEARED": "All votes cleared",
        "END_DAY_REQUEST": "End-day request (2/3)",
        "LYNCH": "Lynch",
        "GAME_START": "Game started",
        "GAME_RESET": "Game reset",
        "GAME_FINISH": "Game finished",
        "ASSIGN": "Role assigned",
    }

    embed = discord.Embed(
        title=title_map.get(kind, kind),
        color=color_map.get(kind, 0x34495e),
    )

    # Useful common fields
    day_no = getattr(game, "current_day_number", None)
    if day_no:
        embed.add_field(name="Day", value=str(day_no), inline=True)

    # Add payload key/value pairs
    for k, v in data.items():
        # Render user IDs as mentions if they look like IDs
        if isinstance(v, str) and v.isdigit() and k.lower().endswith(("id", "uid", "user", "target")):
            v = f"<@{v}>"
        embed.add_field(name=k, value=str(v), inline=True)

    await chan.send(embed=embed)
```

-----
## cognitas/core/lunar.py

```python
from __future__ import annotations

from typing import Tuple

# You can customize these. 8-step cycle by default.
LUNAR_PHASES = [
    ("new", "🌑 New Moon"),
    ("first_quarter", "🌓 First Quarter"),
    ("full", "🌕 Full Moon"),
    ("last_quarter", "🌗 Last Quarter"),
]

DEFAULT_CYCLE_STEPS = len(LUNAR_PHASES)

def announcement(idx: int) -> str:
    """Return a short message announcing the current lunar phase."""
    key, label = get_phase_by_index(idx)
    if key == "new":
        return f"{label} rises..."
    if key == "first_quarter":
        return f"{label} ascends."
    if key == "full":
        return f"{label} shines bright."
    if key == "last_quarter":
        return f"{label} wanes."
    return label

def get_phase_by_index(idx: int) -> Tuple[str, str]:
    phases = LUNAR_PHASES
    if not phases:
        return ("unknown", "○")
    i = idx % len(phases)
    return phases[i]

def advance(game, *, steps: int = 1):
    """
    Advance the lunar index by `steps`. Persisting is up to caller.
    """
    current = int(getattr(game, "lunar_index", 0) or 0)
    setattr(game, "lunar_index", (current + steps) % DEFAULT_CYCLE_STEPS)

def current(game) -> Tuple[str, str]:
    idx = int(getattr(game, "lunar_index", 0) or 0)
    return get_phase_by_index(idx)
```

-----
## cognitas/core/phases.py

```python
from __future__ import annotations

import time
import asyncio
import discord
from typing import Optional

from ..config import REMINDER_CHECKPOINTS
from ..status import engine as SE
from .state import game
from .storage import save_state
from .logs import log_event
from .johnbotjovi import lynch as make_lynch_poster
from .. import config as cfg
from .reminders import (
    parse_duration_to_seconds,
    start_day_timer,
    start_night_timer,
)

# -------------------------
# Checkpoints normalization
# -------------------------

def _minutes_checkpoints_from_config(config_list, *, duration_seconds: int | None = None, minutes_left: int | None = None) -> list[int]:
    """
    Convert REMINDER_CHECKPOINTS into integer minutes.
    - Supports literal integers expressed in seconds (e.g., 4*3600, 15*60) or minutes.
    - Supports the string "half" meaning half the duration (if duration_seconds provided)
      or half the remaining time (if minutes_left provided and duration_seconds is None).
    Only returns values <= minutes_left when minutes_left is provided.
    """
    mins = []
    # Determine a sensible cap to filter by remaining time
    cap = None
    if minutes_left is not None:
        try:
            cap = int(max(0, minutes_left))
        except Exception:
            cap = None

    for item in (config_list or []):
        val_min = None
        if isinstance(item, str) and item.lower() == "half":
            if duration_seconds is not None:
                val_min = max(1, int(round(duration_seconds / 120)))  # half duration in minutes
            elif minutes_left is not None:
                val_min = max(1, int(round(minutes_left / 2)))
        elif isinstance(item, (int, float)):
            # Treat as seconds if >= 60, otherwise as minutes
            if item >= 60:
                val_min = int((int(item) + 59) // 60)  # ceil to minutes
            else:
                val_min = int(item)
        # ignore unsupported types silently

        if val_min is not None:
            if cap is None or val_min <= cap:
                mins.append(val_min)

    # Always include 1-minute if within cap and not present
    if cap is not None and cap >= 1 and 1 not in mins:
        mins.append(1)

    # Deduplicate and sort descending (worker checks equality against minutes_left)
    mins = sorted(set(int(m) for m in mins if m > 0), reverse=True)
    return mins


def _get_channel_or_none(guild: discord.Guild, chan_id: int | None) -> discord.abc.GuildChannel | discord.Thread | None:
    if not chan_id:
        return None
    try:
        ch = guild.get_channel_or_thread(chan_id)
    except AttributeError:
        ch = guild.get_channel(chan_id)
    return ch if isinstance(ch, (discord.abc.GuildChannel, discord.Thread)) else None


def _ensure_day_channel(ctx) -> discord.TextChannel:
    """Ensure day channel is configured and exists; raise RuntimeError if not."""
    guild: discord.Guild = ctx.guild
    ch = _get_channel_or_none(guild, getattr(game, "day_channel_id", None))
    if not ch:
        raise RuntimeError("Day channel is not configured or no longer exists. Set it with `/set_day_channel`.")
    return ch


async def start_day(
    ctx,
    *,
    duration_str: str = "24h",
    target_channel: Optional[discord.TextChannel] = None,
    force: bool = False,
    ):
    """
    Start the Day phase:
    - Resolve Day channel (explicit > configured default) and validate it
    - Compute & store deadline
    - Open channel for @everyone messages
    - Launch configured reminders
    - Reset /vote end_day (2/3) requests
    """

    guild: discord.Guild = ctx.guild

    # Resolve the target channel
    ch = target_channel or _get_channel_or_none(guild, getattr(game, "day_channel_id", None)) or ctx.channel
    if not isinstance(ch, (discord.TextChannel, discord.Thread)):
        return await ctx.reply("Day channel must be a text channel or a thread.")

    # Parse duration
    seconds = parse_duration_to_seconds(duration_str or "24h") or 24 * 3600

    # If there's an active Day and not forcing, inform and exit
    if hasattr(game, "day_deadline_epoch") and game.day_deadline_epoch and not force:
        chan = ctx.guild.get_channel(getattr(game, "day_channel_id", None))
        when = f"<t:{game.day_deadline_epoch}:R>"
        return await ctx.reply(
            f"There is already an active Day in {chan.mention if chan else '#?'} (ends {when}). "
            f"Use `force` to restart it."
        )

    # If forcing, cancel previous Day timer (if any)
    if force and getattr(game, "day_timer_task", None) and not game.day_timer_task.done():
        game.day_timer_task.cancel()
        game.day_timer_task = None

    try:
        # Cancel Night reminders worker
        if getattr(game, "night_timer_task", None) and not game.night_timer_task.done():
            game.night_timer_task.cancel()
    except Exception:
        pass
    game.night_timer_task = None
    game.night_deadline_epoch = None

    # Check the Day number, then add one.
    
    curr = int(getattr(game, "current_day_number", 0) or 0)
    phase_now = (getattr(game, "phase", "day") or "day").lower()

    if phase_now != "day" or force:
        # starting a new day cycle
        game.current_day_number = (curr + 1) if curr >= 0 else 1
        # optional: reset per-day data here if you keep some
    else:
        # staying in the same day (restart timers only)
        game.current_day_number = max(1, curr)  
        
    game.phase = "day"


    try:
        if hasattr(game, "votes"):
            game.votes.clear()
        else:
            game.votes = {}
    except Exception:
        game.votes = {}


        # Notify expansion about phase change into Day
    try:
        game.expansion.on_phase_change(game, "day")

    except Exception:
        pass


    await save_state()
    # Decide Day channel (explicit > configured > current)
    target: discord.abc.Messageable = ch
    game.day_channel_id = ch.id

    
    # Compute and store deadline
    now = int(time.time())
    game.day_deadline_epoch = now + seconds

    # Open channel for @everyone
    try:
        everyone = ch.guild.default_role
        ow = ch.overwrites_for(everyone)
        ow.send_messages = True
        await ch.set_permissions(everyone, overwrite=ow)
    except Exception:
        pass

    # Expansion may provide a Day banner (e.g., lunar announcement)
    try:
        banner = getattr(game, "expansion", None) and game.expansion.banner_for_day(game)
        if banner:
            await ch.send(str(banner))
    except Exception:
        pass

        # --- Status engine: 1 tick at Day start (announce day banners publicly) ---
    try:
        banners = SE.tick(game, "day")
        for uid, text in banners:
            if not text:
                continue
            member = None
            try:
                member = guild.get_member(int(uid)) or await guild.fetch_member(int(uid))
            except Exception:
                member = None
            # Day: announce in Day channel by default (your spec says day messages are public)
            try:
                await ch.send(text if isinstance(text, str) else str(text))
            except Exception:
                # fallback to DM if channel send fails
                if member:
                    try:
                        await member.send(text if isinstance(text, str) else str(text))
                    except Exception:
                        pass
        await save_state()
    except Exception:
        pass

    # Announce
    abs_ts = f"<t:{game.day_deadline_epoch}:F>"
    rel_ts = f"<t:{game.day_deadline_epoch}:R>"
    try:
        await ch.send(f"🌞 **Day started.** Deadline: {rel_ts} ({abs_ts}).")
    except Exception:
        pass

    # Persist state
    await save_state()

    # Launch Day reminders (normalized checkpoints)
    total_minutes = max(1, seconds // 60)
    cp = _minutes_checkpoints_from_config(cfg.REMINDER_CHECKPOINTS, minutes_left=total_minutes)
    await start_day_timer(ctx.bot, ctx.guild.id, target.id, checkpoints=cp)
    asyncio.create_task(_autoclose_after(ctx.bot, ctx.guild.id, "day", game.day_deadline_epoch))

    # Log event
    await log_event(ctx.bot, ctx.guild.id, "PHASE_START", phase="Day", deadline=game.day_deadline_epoch)

    # Clean up the invoking message (if any; slash interactions may not have a message)
    try:
        if getattr(ctx, "message", None):
            await ctx.message.delete(delay=2)
    except Exception:
        pass


async def end_day(
    ctx,
    *,
    closed_by_threshold: bool = False,
    lynch_target_id: Optional[int] = None,
    ):
    """
    Close the Day phase:
    - Close channel for @everyone messages
    - Announce result (with or without lynch)
    - If lynch: mark player dead and post lynch poster (core/jonbotjovi.lynch)
    - Clear deadline and cancel timer
    """
    guild: discord.Guild = ctx.guild
    ch = _get_channel_or_none(guild, getattr(game, "day_channel_id", None))
    if not ch:
        return await ctx.reply("No Day channel configured.")

    lynch_member: Optional[discord.Member] = None

    # Announce end (with or without lynch)
    if lynch_target_id:
        # Try to resolve the member object for poster + mention
        try:
            lynch_member = guild.get_member(lynch_target_id) or await guild.fetch_member(lynch_target_id)
        except Exception:
            lynch_member = None

        try:
            await ch.send(f"⚖️ **Day has ended.** Lynched: <@{lynch_target_id}>.")
        except Exception:
            pass

        # Mark player as dead if tracked
        try:
            uid = str(lynch_target_id)
            if hasattr(game, "players") and uid in game.players:
                game.players[uid]["alive"] = False
        except Exception:
            pass

        # Try to generate and send lynch poster
        if lynch_member is not None:
            try:
                poster = await make_lynch_poster(lynch_member)
            except Exception:
                poster = None

            if poster is not None:
                try:
                    await ch.send(content=f"🪓 **LYNCH!** {lynch_member.mention}", file=poster)
                except Exception:
                    pass


    elif closed_by_threshold:
        try:
            await ch.send("⛔ **Day has ended** due to /vote end_day threshold.")
        except Exception:
            pass
    else:
        try:
            await ch.send("🌇 **Day has ended.**")
        except Exception:
            pass

    # Close messages for @everyone
    try:
        everyone = ch.guild.default_role
        ow = ch.overwrites_for(everyone)
        ow.send_messages = False
        await ch.set_permissions(everyone, overwrite=ow)
    except Exception:
        pass

    # Cancel timer & clear deadline
    try:
        if getattr(game, "day_timer_task", None) and not game.day_timer_task.done():
            game.day_timer_task.cancel()
    except Exception:
        pass
    game.day_timer_task = None
    game.day_deadline_epoch = None
    
    # Clear votes at day end to avoid stale tallies carrying over 
    try:
        if hasattr(game, "votes"):
            game.votes.clear()
        else:
            game.votes = {}
    except Exception:
        game.votes = {}



    # Persist & log
    await save_state()
    await log_event(ctx.bot, ctx.guild.id, "PHASE_END", phase="Day", lynch_target_id=lynch_target_id or None)

    # Acknowledge
    try:
        await ctx.reply("Day closed.")
    except Exception:
        pass

async def start_night(
    ctx,
    *,
    duration_str: str = "12h",
    target_channel: Optional[discord.TextChannel] = None,
    force: bool = False,
    ):
    """
    Start the Night phase:
    - Resolve Night channel (explicit > configured default) and validate it
    - Compute & store deadline
    - (Optionally) close channel to @everyone if you want a silent Night
    - Launch configured reminders
    """
    guild: discord.Guild = ctx.guild

    # Resolve channel
    ch = target_channel or _get_channel_or_none(guild, getattr(game, "night_channel_id", None)) or ctx.channel
    game.night_channel_id = ch.id
    if not isinstance(ch, (discord.TextChannel, discord.Thread)):
        return await ctx.reply("Night channel must be a text channel or a thread.")

    # Parse duration
    seconds = parse_duration_to_seconds(duration_str or "12h") or 12 * 3600

    # Prevent overlapping Nights unless forced
    if hasattr(game, "night_deadline_epoch") and game.night_deadline_epoch and not force:
        chan = ctx.guild.get_channel(getattr(game, "night_channel_id", None))
        when = f"<t:{game.night_deadline_epoch}:R>"
        return await ctx.reply(
            f"There is already an active Night in {chan.mention if chan else '#?'} (ends {when}). "
            f"Use `force` to restart it."
        )

    # If forcing, cancel previous Night timer
    if force and getattr(game, "night_timer_task", None) and not game.night_timer_task.done():
        game.night_timer_task.cancel()
        game.night_timer_task = None

    try:
        if getattr(game, "day_timer_task", None) and not game.day_timer_task.done():
            game.day_timer_task.cancel()
    except Exception:
        pass
    game.day_timer_task = None
    game.day_deadline_epoch = None

    # Store channel & phase
    game.night_channel_id = ch.id
    game.phase = "night"

    # Notify expansion about phase change into Night
    try:
        game.expansion.on_phase_change(game, "night")
    except Exception:
        pass


        # --- Status engine: 1 tick at Night start (night messages via DM) ---
    try:
        banners = SE.tick(game, "night")
        for uid, text in banners:
            if not text:
                continue
            try:
                member = guild.get_member(int(uid)) or await guild.fetch_member(int(uid))
            except Exception:
                member = None
            if member:
                try:
                    # Night: DM only (your spec)
                    await member.send(text if isinstance(text, str) else str(text))
                except Exception:
                    pass
        await save_state()
    except Exception:
        pass


    # Compute and store deadline
    now = int(time.time())
    game.night_deadline_epoch = now + seconds

    # Optionally close @everyone for a silent night
    try:
        everyone = ch.guild.default_role
        ow = ch.overwrites_for(everyone)
        ow.send_messages = False
        await ch.set_permissions(everyone, overwrite=ow)
    except Exception:
        pass

    # Announce
    abs_ts = f"<t:{game.night_deadline_epoch}:F>"
    rel_ts = f"<t:{game.night_deadline_epoch}:R>"
    try:
        await ch.send(f"🌙 **Night started.** Deadline: {rel_ts} ({abs_ts}).")
    except Exception:
        pass

    await save_state()

    # Launch Night reminders (normalized checkpoints)
    total_minutes = max(1, seconds // 60)
    cp = _minutes_checkpoints_from_config(cfg.REMINDER_CHECKPOINTS, minutes_left=total_minutes)
    await start_night_timer(ctx.bot, ctx.guild.id, ch.id, checkpoints=cp)
    asyncio.create_task(_autoclose_after(ctx.bot, ctx.guild.id, "night", game.night_deadline_epoch))

    await log_event(ctx.bot, ctx.guild.id, "PHASE_START", phase="Night", deadline=game.night_deadline_epoch)

    try:
        if getattr(ctx, "message", None):
            await ctx.message.delete(delay=2)
    except Exception:
        pass


async def end_night(ctx):
    """
    Close the Night phase:
    - Announce end
    - Clear deadline and cancel timer
    """
    guild: discord.Guild = ctx.guild
    ch = _get_channel_or_none(guild, getattr(game, "night_channel_id", None))
    if not ch:
        return await ctx.reply("No Night channel configured.")

    try:
        await ch.send("🌅 **Night has ended.**")
    except Exception:
        pass

    # Cancel timer
    try:
        if getattr(game, "night_timer_task", None) and not game.night_timer_task.done():
            game.night_timer_task.cancel()
    except Exception:
        pass
    game.night_timer_task = None
    game.night_deadline_epoch = None

    await save_state()
    await log_event(ctx.bot, ctx.guild.id, "PHASE_END", phase="Night")

    try:
        await ctx.reply("Night closed.")
    except Exception:
        pass


async def _autoclose_after(bot: discord.Client, guild_id: int, phase: str, unix_deadline: int):
    """Wait until deadline and then automatically announce and close the phase if it is still active."""
    try:
        now = int(time.time())
        delay = max(0, unix_deadline - now)
        await asyncio.sleep(delay)
        guild = bot.get_guild(guild_id)
        if not guild:
            return
        # If the phase changed, abort
        if getattr(game, "phase", None) != phase:
            return

        # Resolve channel by phase
        chan_id = getattr(game, f"{phase}_channel_id", None)
        channel = guild.get_channel(chan_id) if chan_id else None

        # Send timeout message
        if channel:
            try:
                when_abs = f"<t:{unix_deadline}:F>"
                await channel.send(f"⏳ **{phase.capitalize()}** has ended by time ({when_abs}).")
            except Exception:
                pass

        # Auto close by invoking the corresponding end function
        try:
            if phase == "day":
                from .phases import end_day
                class _Ctx:
                    def __init__(self, guild): self.guild = guild
                    async def reply(self, *a, **k): pass
                await end_day(_Ctx(guild), closed_by_threshold=False, lynch_target_id=None)
            elif phase == "night":
                from .phases import end_night
                class _Ctx:
                    def __init__(self, guild): self.guild = guild
                    async def reply(self, *a, **k): pass
                await end_night(_Ctx(guild))
        except Exception as e:
            print(f"[phases] autoclose error for {phase}: {e!r}")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[phases] autoclose crash for {phase}: {e!r}")


async def rehydrate_timers(bot: discord.Client, guild: discord.Guild):
    """
    Restore ongoing Day/Night awareness from stored deadlines.
    - If the deadline is in the future → announce remaining time, relaunch reminders based on remaining time, and arm autoclose.
    - If the deadline has passed → announce and immediately autoclose.
    """
    try:
        phase = getattr(game, "phase", None)
        if phase not in ("day", "night"):
            return

        deadline = getattr(game, f"{phase}_deadline_epoch", None)
        if not deadline:
            return

        # Resolve channel for this phase
        chan_id = getattr(game, f"{phase}_channel_id", None)
        if not chan_id:
            # If Night has no dedicated channel id, fallback to Day channel id
            chan_id = getattr(game, "day_channel_id", None)
        try:
            ch = guild.get_channel_or_thread(chan_id) if chan_id else None
        except AttributeError:
            ch = guild.get_channel(chan_id) if chan_id else None
        if not ch:
            return

        now = int(time.time())
        ts = int(deadline)
        if ts > now:
            # Announce restore
            await ch.send(f"🔄 Restored **{phase}**. Deadline <t:{ts}:R>.")
            # Relaunch reminders using remaining time
            minutes_left = max(0, (ts - now + 59) // 60)
            cp = _minutes_checkpoints_from_config(cfg.REMINDER_CHECKPOINTS, minutes_left=minutes_left)
            if phase == "day":
                await start_day_timer(bot, guild.id, chan_id, checkpoints=cp)
            else:
                await start_night_timer(bot, guild.id, checkpoints=cp)
            # Arm autoclose
            asyncio.create_task(_autoclose_after(bot, guild.id, phase, ts))
        else:
            # Deadline already passed — announce and close
            await ch.send(f"⏰ Stored deadline for **{phase}** has already passed (<t:{ts}:R>). Closing automatically.")
            try:
                if phase == "day":
                    from .phases import end_day
                    class _Ctx:
                        def __init__(self, guild): self.guild = guild
                        async def reply(self, *a, **k): pass
                    await end_day(_Ctx(guild), closed_by_threshold=False, lynch_target_id=None)
                else:
                    from .phases import end_night
                    class _Ctx:
                        def __init__(self, guild): self.guild = guild
                        async def reply(self, *a, **k): pass
                    await end_night(_Ctx(guild))
            except Exception as e:
                print(f"[phases] rehydrate autoclose error for {phase}: {e!r}")
    except Exception as e:
        print(f"[phases] rehydrate_timers error: {e!r}")
```

-----
## cognitas/core/players.py

```python
from __future__ import annotations

import re
import discord
from discord.ext import commands
from typing import Any, Dict
from enum import Enum

from .state import game
from .storage import save_state

NAME_RX = re.compile(r"\s+")


def _norm(name: str) -> str:
    return NAME_RX.sub(" ", (name or "").strip())


def _slug(name: str) -> str:
    s = _norm(name).lower()
    return re.sub(r"[^a-z0-9\-]+", "-", s.replace(" ", "-")).strip("-") or "player"


def _ensure_player(uid: str, display_name: str | None = None):
    game.players.setdefault(uid, {
        "uid": uid,
        "name": display_name or f"User-{uid}",
        "alive": True,
        "aliases": [],
        "flags": {},
        "effects": [],
    })


def _is_admin(ctx: commands.Context | Any) -> bool:
    try:
        # Also works with our InteractionCtx adapter
        author = getattr(ctx, "author", None) or getattr(ctx, "user", None)
        return bool(getattr(getattr(author, "guild_permissions", None), "administrator", False))
    except Exception:
        return False


async def _sanitize_votes_for_uid(uid: str):
    """
    Remove the player's active vote and end-day request when they die.
    Best-effort; ignores errors.
    """
    try:
        # Remove active vote
        if isinstance(getattr(game, "votes", None), dict) and uid in game.votes:
            del game.votes[uid]
        # Remove end-day request (supports legacy list/tuple)
        end_set = getattr(game, "end_day_votes", None)
        if isinstance(end_set, set) and uid in end_set:
            end_set.remove(uid)
        elif isinstance(end_set, (list, tuple)) and uid in end_set:
            s = set(end_set)
            s.discard(uid)
            game.end_day_votes = s
        await save_state()
    except Exception:
        # keep going; this is best-effort hygiene
        pass


def get_player_snapshot(user_id: str) -> dict:
    """
    Return a readonly snapshot of the player's state for display.
    Keys: uid, name, alive, role, voting_boost, vote_weight_field, hidden_vote,
          aliases, effects, flags, vote_weight_computed (if available).
    """
    p = (getattr(game, "players", {}) or {}).get(user_id)
    if not p:
        return {}

    # Stored fields (safe defaults)
    name = p.get("name", f"User-{user_id}")
    alive = bool(p.get("alive", True))
    role = p.get("role")
    voting_boost = p.get("voting_boost")
    vote_weight_field = p.get("vote_weight")
    hidden_vote = bool(flags.get("hidden_vote", False))
    aliases = list(p.get("aliases", []))
    effects = list(p.get("effects", []))
    flags = dict(p.get("flags", {}))

    #Role private channel id
    role_channel_id = p.get("role_channel_id")

    # Computed vote weight (if GameState exposes a helper)
    vote_weight_computed = None
    try:
        vote_weight_computed = game.vote_weight(user_id)  # may not exist in all builds
    except Exception:
        pass

    return {
        "uid": user_id,
        "name": name,
        "alive": alive,
        "role": role,
        "voting_boost": voting_boost,
        "vote_weight_field": vote_weight_field,
        "hidden_vote": hidden_vote,
        "aliases": aliases,
        "effects": effects,
        "flags": flags,
        "vote_weight_computed": vote_weight_computed,
        "role_channel_id": role_channel_id,
    }


# ----------------------------
# List & basic registration
# ----------------------------

async def list_players(ctx):
    players = getattr(game, "players", {}) or {}
    if not players:
        return await ctx.reply("No players registered.")
    alive = [p for p in players.values() if p.get("alive", True)]
    dead = [p for p in players.values() if not p.get("alive", True)]

    def fmt(pl):
        return ", ".join(f"<@{p['uid']}> ({p.get('name','?')})" for p in pl) if pl else "—"

    await ctx.reply(
        f"**Alive**: {fmt(alive)}\n"
        f"**Dead**: {fmt(dead)}\n"
        f"**Total**: {len(players)}"
    )


async def register(ctx, member: discord.Member | None = None, *, name: str | None = None):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    guild = getattr(ctx, "guild", None)
    if not guild:
        return await ctx.reply("Guild context required.", ephemeral=True)

    target = member or getattr(ctx, "author", None) or getattr(ctx, "user", None)
    if not target:
        return await ctx.reply("No target user provided.", ephemeral=True)

    uid = str(target.id)
    display = (name or getattr(target, "display_name", None) or f"User-{uid}").strip()

    _ensure_player(uid, display)
    game.players[uid]["name"] = display
    game.players[uid]["alive"] = True

    # --- Create or reuse player's private role channel ---
    # If already has one and channel exists, keep it. Else create.
    existing_ch_id = game.players[uid].get("role_channel_id")
    existing_ch = guild.get_channel(existing_ch_id) if existing_ch_id else None

    if existing_ch is None:
        # Build overwrites: @everyone = no view, player+bot = view/send
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            target: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True),
        }

        # Optional: place under the same category as the Day channel if you want grouping
        parent = None
        try:
            day_id = getattr(game, "day_channel_id", None)
            if day_id:
                day_ch = guild.get_channel(day_id)
                parent = getattr(day_ch, "category", None)
        except Exception:
            parent = None

        ch_name = f"role-{_slug(display)}"
        try:
            role_ch = await guild.create_text_channel(
                ch_name, overwrites=overwrites, category=parent, reason="Asdrubot: player role channel"
            )
            game.players[uid]["role_channel_id"] = role_ch.id
        except Exception as e:
            # Soft fail: just skip channel creation
            game.players[uid]["role_channel_id"] = None
    else:
        # Keep existing
        game.players[uid]["role_channel_id"] = existing_ch.id

    await save_state()

    # Friendly confirmation (ephemeral)
    ch_mention = ""
    try:
        rcid = game.players[uid].get("role_channel_id")
        rch = guild.get_channel(rcid) if rcid else None
        if rch:
            ch_mention = f" — channel: {rch.mention}"
    except Exception:
        pass

    await ctx.reply(f"✅ Registered: <@{uid}> as **{display}** (alive){ch_mention}.", ephemeral=True)

    # Optional: greet in private role channel
    try:
        rcid = game.players[uid].get("role_channel_id")
        rch = guild.get_channel(rcid) if rcid else None
        if rch:
            await rch.send(f"Welcome, <@{uid}>! This is your private role channel. Use `/act` here to perform your actions.")
    except Exception:
        pass



async def unregister(ctx, member: discord.Member):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid in game.players:
        del game.players[uid]
        await save_state()
        return await ctx.reply(f"🗑️ Unregistered <@{uid}>.", ephemeral=True)
    await ctx.reply("Player was not registered.", ephemeral=True)


async def rename(ctx, member: discord.Member, *, new_name: str):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    game.players[uid]["name"] = _norm(new_name)
    await save_state()
    await ctx.reply(f"✏️ <@{uid}> is now **{new_name}**.", ephemeral=True)


# ----------------------------
# Aliases
# ----------------------------

async def alias_show(ctx, member: discord.Member):
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    aliases = game.players[uid].get("aliases", [])
    if not aliases:
        return await ctx.reply(f"<@{uid}> has no aliases.", ephemeral=True)
    await ctx.reply(f"Aliases for <@{uid}>: {', '.join('`'+a+'`' for a in aliases)}", ephemeral=True)


async def alias_add(ctx, member: discord.Member, *, alias: str):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    alias_n = _norm(alias)
    arr = game.players[uid].setdefault("aliases", [])
    if alias_n in arr:
        return await ctx.reply("Alias already exists.", ephemeral=True)
    arr.append(alias_n)
    await save_state()
    await ctx.reply(f"➕ Added alias to <@{uid}>: `{alias_n}`", ephemeral=True)


async def alias_del(ctx, member: discord.Member, *, alias: str):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    alias_n = _norm(alias)
    arr = game.players[uid].get("aliases", [])
    if alias_n not in arr:
        return await ctx.reply("Alias not found.", ephemeral=True)
    arr.remove(alias_n)
    await save_state()
    await ctx.reply(f"➖ Removed alias from <@{uid}>: `{alias_n}`", ephemeral=True)


# ----------------------------
# Edit API (replaces set_player_field)
# ----------------------------

class PlayerField(str, Enum):
    alive = "alive"
    name = "name"
    role = "role"
    # Left here for compatibility in snapshots; editing them must go via flags:
    voting_boost = "voting_boost"
    vote_weight = "vote_weight"
    hidden_vote = "hidden_vote"


# Fields that /player edit may suggest (safe), but we still accept custom ones.
SAFE_EDIT_FIELDS: Dict[str, type] = {
    "alive": bool,
    "name": str,
    "role": str,
    "effects": list,   # CSV → list[str]
    "notes": str,
    "alias": str,      # single alias field if you use it
}

# Fields that MUST be managed via flags (set_flag), not via edit.
PROTECTED_VOTE_FIELDS = {
    "hidden_vote", "voting_boost", "vote_weight", "no_vote", "silenced",
    "lynch_plus", "lynch_resistance", "needs_extra_votes",
}


def _parse_bool(s: str) -> bool:
    s = (s or "").strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    raise ValueError("Expected boolean (true/false).")


def _coerce_basic(value: str) -> Any:
    s = (value or "").strip()
    # boolean literals
    if re.fullmatch(r"(?i)(true|on|yes|y|1)", s):
        return True
    if re.fullmatch(r"(?i)(false|off|no|n|0)", s):
        return False
    # integer
    if re.fullmatch(r"[-+]?\d+", s):
        try:
            return int(s)
        except Exception:
            pass
    # default str
    return value


async def edit_player(ctx, member: discord.Member, field: str, value: str):
    """
    Safe, typed edit:
      - Redirects voting/lynch-specific fields to /player set_flag.
      - Coerces bool/int where reasonable; special cases for common fields.
    """
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    players = getattr(game, "players", {}) or {}
    if uid not in players:
        return await ctx.reply("Player not registered.", ephemeral=True)

    f = (field or "").strip()
    if not f:
        return await ctx.reply("Field name is required.", ephemeral=True)
    f_l = f.lower()

    # Guard rails: enforce flags path for voting/lynch
    if f_l in PROTECTED_VOTE_FIELDS:
        return await ctx.reply("Use **/player set_flag** for voting/lynch related fields.", ephemeral=True)

    p = players[uid]
    # Friendly typed edits
    if f_l in ("name", "display_name"):
        p["name"] = _norm(value)
    elif f_l == "alias":
        # if you use a single alias field
        p["alias"] = _norm(value)
    elif f_l == "role":
        p["role"] = _norm(value)
    elif f_l == "alive":
        try:
            alive_val = _parse_bool(value)
        except Exception as e:
            return await ctx.reply(f"Invalid boolean for `alive`: {e}", ephemeral=True)
        p["alive"] = bool(alive_val)
        if not alive_val:
            await _sanitize_votes_for_uid(uid)
    elif f_l == "effects":
        arr = [seg.strip() for seg in str(value).split(",") if seg.strip()]
        p["effects"] = arr
    elif f_l in ("notes", "note"):
        p["notes"] = str(value)
    else:
        # Generic best-effort coercion
        p[f] = _coerce_basic(value)

    await save_state()
    return await ctx.reply(f"✅ Set `{f}` = `{p.get(f_l, p.get(f, value))}` for <@{uid}>.", ephemeral=True)


# ----------------------------
# Flags API
# ----------------------------

async def set_flag(ctx, member: discord.Member, key: str, value: Any):
    """
    Set or update a flag key on a player (value already parsed/typed by the cog).
    """
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    key = (key or "").strip()
    if not key:
        return await ctx.reply("Flag key is required.", ephemeral=True)

    flags = game.players[uid].setdefault("flags", {})
    flags[key] = value
    await save_state()
    await ctx.reply(f"✅ Flag `{key}` set to `{value}` for <@{uid}>.", ephemeral=True)


async def del_flag(ctx, member: discord.Member, key: str):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    flags = game.players[uid].get("flags", {})
    if key not in flags:
        return await ctx.reply("Flag not found.", ephemeral=True)
    del flags[key]
    await save_state()
    await ctx.reply(f"🗑️ Flag `{key}` removed for <@{uid}>.", ephemeral=True)


# ----------------------------
# Effects
# ----------------------------

async def add_effect(ctx, member: discord.Member, effect: str):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    arr = game.players[uid].setdefault("effects", [])
    if effect in arr:
        return await ctx.reply("Effect already present.", ephemeral=True)
    arr.append(effect)
    await save_state()
    await ctx.reply(f"✨ Effect `{effect}` added to <@{uid}>.", ephemeral=True)


async def remove_effect(ctx, member: discord.Member, effect: str):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    arr = game.players[uid].get("effects", [])
    if effect not in arr:
        return await ctx.reply("Effect not found.", ephemeral=True)
    arr.remove(effect)
    await save_state()
    await ctx.reply(f"🧹 Effect `{effect}` removed from <@{uid}>.", ephemeral=True)


# ----------------------------
# Alive / Kill / Revive
# ----------------------------

async def set_alive(ctx, member: discord.Member, alive: bool):
    if not _is_admin(ctx):
        return await ctx.reply("Admins only.", ephemeral=True)
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.", ephemeral=True)
    game.players[uid]["alive"] = bool(alive)
    if not alive:
        await _sanitize_votes_for_uid(uid)
    await save_state()
    emoji = "☠️" if not alive else "💚"
    await ctx.reply(f"{emoji} Set `alive` = `{alive}` for <@{uid}>.", ephemeral=True)


async def kill(ctx, member: discord.Member):
    await set_alive(ctx, member, False)


async def revive(ctx, member: discord.Member):
    await set_alive(ctx, member, True)```

-----
## cognitas/core/reminders.py

```python
# cognitas/core/reminders.py
from __future__ import annotations

import re
import time
import asyncio
from typing import List, Optional

import discord

from .state import game

_DURATION_RX = re.compile(r"^\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*$", re.I)

def parse_duration_to_seconds(s: str) -> int:
    if not s:
        return 0
    s = s.strip().lower().replace(" ", "")
    if not s:
        return 0
    if s.endswith("m") and s[:-1].isdigit():
        return int(s[:-1]) * 60
    if s.endswith("h") and s[:-1].isdigit():
        return int(s[:-1]) * 3600
    m = _DURATION_RX.match(s)
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mm = int(m.group(2) or 0)
    return h * 3600 + mm * 60

async def _safe_send(chan: discord.abc.Messageable, content: str):
    try:
        await chan.send(content)
    except Exception as e:
        print(f"[reminders] send error in #{getattr(chan, 'id', '?')}: {e!r}")

def _cancel_task_safe(task: Optional[asyncio.Task]):
    try:
        if task and not task.done():
            task.cancel()
    except Exception:
        pass

async def _timer_worker(
    bot: discord.Client,
    *,
    guild_id: int,
    channel_id: int,
    checkpoints_minutes_desc: List[int],
    deadline_epoch: int,
    phase_label: str,  # "Day" or "Night"
):
    try:
        cps = sorted({int(m) for m in checkpoints_minutes_desc if int(m) > 0}, reverse=True)
        sent = set()

        while True:
            now = int(time.time())
            secs_left = deadline_epoch - now
            if secs_left <= 0:
                break

            minutes_left = secs_left // 60
            for m in list(cps):
                if minutes_left <= m and m not in sent:
                    try:
                        guild = bot.get_guild(guild_id)
                        if not guild:
                            break
                        try:
                            chan = guild.get_channel_or_thread(channel_id)
                        except AttributeError:
                            chan = guild.get_channel(channel_id)
                        if not chan:
                            break
                        abs_ts = f"<t:{deadline_epoch}:F>"
                        rel_ts = f"<t:{deadline_epoch}:R>"
                        await _safe_send(
                            chan,
                            f"⏰ **{phase_label}** — **{m} min** remaining (ends {rel_ts}, {abs_ts})."
                        )
                        sent.add(m)
                    except Exception as e:
                        print(f"[reminders] checkpoint error {m}m ({phase_label}): {e!r}")

            sleep_for = min(20, max(5, secs_left / 6))
            await asyncio.sleep(sleep_for)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[reminders] worker crash ({phase_label}): {e!r}")

async def start_day_timer(
    bot: discord.Client,
    guild_id: int,
    channel_id: int,
    *,
    checkpoints: List[int],
):
    try:
        _cancel_task_safe(getattr(game, "day_timer_task", None))
        deadline = getattr(game, "day_deadline_epoch", None)
        if not deadline:
            return
        task = bot.loop.create_task(
            _timer_worker(
                bot,
                guild_id=guild_id,
                channel_id=channel_id,
                checkpoints_minutes_desc=checkpoints,
                deadline_epoch=deadline,
                phase_label="Day",
            )
        )
        game.day_timer_task = task
        print(f"[reminders] Day timer started (guild={guild_id}, channel={channel_id}, deadline={deadline}).")
    except Exception as e:
        print(f"[reminders] start_day_timer error: {e!r}")

async def start_night_timer(
    bot: discord.Client,
    guild_id: int,
    channel_id: int,
    *,
    checkpoints: List[int],
):
    """
    Night timer now receives channel_id explicitly (works fine for a single shared channel).
    """
    try:
        _cancel_task_safe(getattr(game, "night_timer_task", None))
        deadline = getattr(game, "night_deadline_epoch", None)
        if not deadline:
            return
        task = bot.loop.create_task(
            _timer_worker(
                bot,
                guild_id=guild_id,
                channel_id=channel_id,
                checkpoints_minutes_desc=checkpoints,
                deadline_epoch=deadline,
                phase_label="Night",
            )
        )
        game.night_timer_task = task
        print(f"[reminders] Night timer started (guild={guild_id}, channel={channel_id}, deadline={deadline}).")
    except Exception as e:
        print(f"[reminders] start_night_timer error: {e!r}")

def cancel_all_timers():
    _cancel_task_safe(getattr(game, "day_timer_task", None))
    _cancel_task_safe(getattr(game, "night_timer_task", None))
    game.day_timer_task = None
    game.night_timer_task = None


```

-----
## cognitas/core/roles.py

```python
# cognitas/core/roles.py
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def _roles_path_for(profile: str | None) -> Path:
    profile = (profile or "default").lower()
    candidate = DATA_DIR / f"roles_{profile}.json"
    return candidate if candidate.exists() else (DATA_DIR / "roles_default.json")

def validate_roles(defn: dict) -> dict:
    if not isinstance(defn, dict) or "roles" not in defn or not isinstance(defn["roles"], list):
        raise ValueError("Invalid roles file: missing 'roles' array.")
    for r in defn["roles"]:
        r.setdefault("alignment", "Neutral")
        r.setdefault("notes", "")
    return defn

def load_roles(profile: str | None = None) -> dict:
    path = _roles_path_for(profile)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return validate_roles(data)


```

-----
## cognitas/core/state.py

```python
import time
from math import ceil

class GameState:
    def __init__(self):
        # --- Core runtime state ---
        self.players = {}               # { uid: {nick, role, channel_id, alive, flags, effects} }
        self.votes = {}                 # { voter_uid: target_uid }
        self.roles = {}                 # loaded from roles.json
        self.phase: str = "day"
        # --- Day phase ---
        self.day_channel_id = None      # int | None
        self.current_day_number = 1     # int
        self.day_deadline_epoch = None  # int | None (epoch seconds)
        self.day_timer_task = None      # asyncio.Task | None
        self.end_day_votes = set()   # uids (str) of living players who requested to end the day
        
        # --- Night phase ---
        self.night_channel_id = None        # where !act is allowed (optional)
        self.night_deadline_epoch = None    # epoch seconds
        self.night_timer_task = None        # asyncio.Task | None
        self.next_day_channel_id = None     # which channel to open at dawn

        # --- Night action log (append-only) ---
        # list of dicts: {day, ts_epoch, actor_uid, target_uid, note}
        self.night_actions = []
        self.day_actions = []
        
        # --- Server-configurable channels (set via admin cmds) ---
        self.admin_log_channel_id = None    # where admin logs go
        self.default_day_channel_id = None  # default Day channel
        self.log_channel_id = None          # where the game logs go
        self.moon_phase = "New"             # lunar phase

        # --- Game lifecycle ---
        self.game_over = False              # block new phases when True

    # -------------- Helpers  --------------
    def role_of(self, uid: str) -> dict:
        code = self.players[uid]["role"]
        return self.roles.get(code, {})

    def role_defaults(self, uid: str) -> dict:
        return self.role_of(uid).get("defaults", {})

    def effects_of(self, uid: str) -> list:
        return self.players[uid].get("effects", [])

    def flags_of(self, uid: str) -> dict:
        return self.players[uid].get("flags", {})

    def alive_ids(self):
        return [uid for uid, p in self.players.items() if p.get("alive", True)]

    def base_threshold(self):
        return ceil(len(self.alive_ids()) / 2)

    # ----- voting math -----
    def _expired(self, eff: dict) -> bool:
        exp = eff.get("expires_day")
        return exp is not None and exp < self.current_day_number

    def vote_weight(self, uid: str) -> int:
        p = self.players.get(uid, {})
        if not p or not p.get("alive", True):
            return 0
        fl = self.flags_of(uid)
        if fl.get("silenced", False) or fl.get("absent", False):
            return 0
        base = int(self.role_defaults(uid).get("vote_weight_base", 1))
        boosts = [
            int(e.get("value", 0))
            for e in self.effects_of(uid)
            if e.get("type") == "vote_boost" and not self._expired(e)
        ]
        return max([base] + boosts) if boosts else base

    def lynch_delta(self, uid: str) -> int:
        d = 0
        dfl = self.role_defaults(uid)
        # Zeno (+1 once)
        if dfl.get("lynch_bonus_once", 0) == 1:
            consumed = any(e.get("type") == "zenon_bonus_consumed" for e in self.effects_of(uid))
            if not consumed:
                d += 1
        # Plotinus (-1 while marked)
        marked = any(e.get("type") == "plotino_mark" and not self._expired(e) for e in self.effects_of(uid))
        if marked:
            d -= 1
        return d

    def required_for_target(self, obj_uid: str) -> int:
        o = self.players.get(obj_uid, {})
        if not o or not o.get("alive", True):
            return 9999
        if self.flags_of(obj_uid).get("absent", False):
            return 9999
        req = self.base_threshold() + self.lynch_delta(obj_uid)
        return max(1, req)

    def totals_per_target(self) -> dict:
        totals = {}
        for voter_uid, target_uid in self.votes.items():
            if not target_uid or target_uid not in self.players:
                continue
            if not self.players[target_uid].get("alive", True):
                continue
            if self.flags_of(target_uid).get("absent", False):
                continue
            w = self.vote_weight(voter_uid)
            if w <= 0:
                continue
            totals[target_uid] = totals.get(target_uid, 0) + w
        return totals

    def add_unique_effect(self, uid: str, effect_type: str, *, value: int = 0, expires_day: int | None = None) -> bool:
        """Add an effect if not already present. Returns True if added."""
        p = self.players.get(uid)
        if not p:
            return False
        effs = p.setdefault("effects", [])
        for e in effs:
            if e.get("type") == effect_type and (e.get("expires_day") == expires_day):
                return False
        effs.append({"type": effect_type, "value": value, "expires_day": expires_day})
        return True

    def remove_effect(self, uid: str, effect_type: str) -> bool:
        """Remove all effects of given type. Returns True if any removed."""
        p = self.players.get(uid)
        if not p:
            return False
        before = len(p.get("effects", []))
        p["effects"] = [e for e in p.get("effects", []) if e.get("type") != effect_type]
        return len(p["effects"]) != before

# Singleton game state
game = GameState()
```

-----
## cognitas/core/storage.py

```python
# cognitas/core/storage.py
from __future__ import annotations

import json
import os
import tempfile
import asyncio
from pathlib import Path
from typing import Any, Dict

from .. import config as cfg
from .state import game


# -------------------------------------------------------------------
# Atomic JSON writer (kept from your original, great for integrity)
# -------------------------------------------------------------------
def _atomic_write_json(path: str, data: dict, *, make_backup: bool = True):
    dirpath = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(dirpath, exist_ok=True)

    if make_backup and os.path.exists(path):
        try:
            bak = path + ".bak"
            if os.path.exists(bak):
                os.remove(bak)
            os.replace(path, bak)
        except Exception:
            pass

    fd, tmp_path = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=dirpath)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _effective_path(path: str | Path | None) -> str:
    """
    Resolve to an absolute path.
    If not provided, use cfg.STATE_PATH (which is already absolute in our config).
    """
    p = Path(path) if path else Path(cfg.STATE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def _ensure_defaults():
    """
    Make sure required attributes exist on 'game' to avoid AttributeError.
    """
    defaults = {
        "players": {},
        "votes": {},
        "day_channel_id": None,
        "night_channel_id": None,
        "next_day_channel_id": None,
        "admin_channel_id": None,
        "admin_log_channel_id": None,
        "default_day_channel_id": None,
        "game_over": False,
        "current_day_number": 1,
        "day_deadline_epoch": None,
        "night_deadline_epoch": None,
        "profile": "default",
        "roles_def": {},
        # Non-serializable runtime attrs (timers) should exist but won't be saved
        "day_timer_task": None,
        "night_timer_task": None,
        # Night actions container if you use it
        "night_actions": {},
    }
    for k, v in defaults.items():
        if not hasattr(game, k):
            setattr(game, k, v)

    # Ensure a concrete expansion object exists (safe fallback to base)
    try:
        if not hasattr(game, "expansion") or game.expansion is None:
            from .game import _load_expansion_for
            game.expansion = _load_expansion_for(getattr(game, "profile", "default"))

        # Status system containers
        if not hasattr(game, "status_map"): game.status_map = {}
        if not hasattr(game, "status_log"): game.status_log = []

    except Exception:
        # Avoid breaking load paths if expansion resolution fails
        pass


def _rehydrate_roles_index():
    """
    Re-index roles if roles_def exists (compatible with your original logic).
    """
    try:
        from .game import _build_roles_index
        game.roles = _build_roles_index(getattr(game, "roles_def", {}) or {})
    except Exception:
        game.roles = {}


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------
def load_state(path: str | Path | None = None) -> Dict[str, Any]:
    """
    Synchronous load. Safe to call without await (e.g., in bot.setup_hook()).
    Will fall back to reading *.bak if main file is corrupt/missing.
    """
    _ensure_defaults()
    eff_path = _effective_path(path)

    data: Dict[str, Any] = {}
    try:
        with open(eff_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        # Try backup
        try:
            with open(eff_path + ".bak", "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    # --- Hydrate 'game' from data (keep keys consistent with save_state) ---
    game.players = data.get("players", {})
    game.votes = data.get("votes", {})

    game.day_channel_id = data.get("day_channel_id")
    # If you use a single channel for both phases, fall back Night to Day
    game.night_channel_id = data.get("night_channel_id", data.get("day_channel_id"))

    game.next_day_channel_id = data.get("next_day_channel_id")

    # Keep both keys supported; prefer admin_log_channel_id if present
    game.admin_log_channel_id = data.get("admin_log_channel_id", data.get("admin_channel_id"))
    game.admin_channel_id = data.get("admin_channel_id")
    game.phase = data.get("phase","day")
    game.default_day_channel_id = data.get("default_day_channel_id")
    game.game_over = data.get("game_over", False)
    game.current_day_number = data.get("current_day_number", 1)
    game.lunar_index = data.get("lunar_index", 0)

    game.day_deadline_epoch = data.get("day_deadline_epoch")
    game.night_deadline_epoch = data.get("night_deadline_epoch")

    game.profile = data.get("profile", "default")
    game.roles_def = data.get("roles_def", {})

    game.night_actions = data.get("night_actions", {})
    game.day_actions = data.get("day_actions", {})

    # Status engine persistence
    game.status_map = data.get("status_map", {})
    game.status_log = data.get("status_log", [])

    # Re-index roles (compatible with SMT origin files)
    _rehydrate_roles_index()

    return data


async def save_state(path: str | Path | None = None):
    """
    Async save to avoid blocking the event loop. Uses the same absolute path
    resolution as load_state. Writes atomically and keeps a .bak.
    """
    _ensure_defaults()
    eff_path = _effective_path(path)

    # Build serializable snapshot
    payload = {
        "players": game.players,
        "votes": game.votes,
        "day_channel_id": game.day_channel_id,
        "night_channel_id": game.night_channel_id,
        "next_day_channel_id": game.next_day_channel_id,
        "admin_log_channel_id": game.admin_log_channel_id,
        "admin_channel_id": game.admin_channel_id,
        "default_day_channel_id": game.default_day_channel_id,
        "game_over": game.game_over,
        "current_day_number": game.current_day_number,
        "day_deadline_epoch": game.day_deadline_epoch,
        "night_deadline_epoch": game.night_deadline_epoch,
        "phase": getattr(game, "phase", "day"),
        "profile": getattr(game, "profile", "default"),
        "roles_def": getattr(game, "roles_def", {}),
        "night_actions": getattr(game, "night_actions", {}),
        "day_actions": getattr(game, "day_actions", {}),
        "lunar_index": getattr(game, "lunar_index", 0),
        "status_map": getattr(game, "status_map", {}),
        "status_log": getattr(game, "status_log", []),
    }

    # Do the write off-thread to keep the loop snappy
    def _write():
        _atomic_write_json(eff_path, payload, make_backup=True)

    try:
        await asyncio.to_thread(_write)
    except Exception as e:
        print(f"[storage] Failed to write state to {eff_path}: {e!r}")```

-----
## cognitas/core/votes.py

```python
from __future__ import annotations

import math
import random
import time
from typing import Dict, Tuple

import discord
from discord.ext import commands

from .state import game
from .storage import save_state  # async
from .logs import log_event
from . import phases
from . import lunar
from ..status import engine as SE


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

    embed.set_footer(text="Asdrubot v2.0 — Voting UI")
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

    # Lunar
    _, lunar_label = lunar.current(game)

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
    embed = discord.Embed(
        title="Game Status",
        description="\n".join([
            f"**Phase:** {'🌞 Day' if phase == 'day' else '🌙 Night'}",
            f"**Counter:** {('Day' if phase == 'day' else 'Night')} {day_no}",
            f"**Lunar:** {lunar_label}",
            f"**Time left:** {time_left}",
        ]),
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
```

-----
## cognitas/cogs/__init__.py

```python
```

-----
## cognitas/cogs/actions.py

```python
from __future__ import annotations

import time
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..core.state import game
from ..core.storage import save_state
from ..core.logs import log_event  
from ..core import actions as act_core 
from ..status import engine as SE



def _label_from_uid(uid: str | None) -> str:
    if not uid:
        return "—"
    p = game.players.get(str(uid), {})
    return p.get("name") or p.get("alias") or f"<@{uid}>"

def _fmt_action_line(a: dict) -> str:
    act = a.get("action") or "act"
    tgt = _label_from_uid(a.get("target"))
    note = a.get("note") or "—"
    at = a.get("at")
    when = f"<t:{int(at)}:R>" if at else "—"
    return f"• action=`{act}` target={tgt} note=`{note}` at={when}"


# ---------- Small adapter to safely reply after defer ----------
class InteractionCtx:
    def __init__(self, interaction: discord.Interaction):
        self._i = interaction
        self.guild = interaction.guild
        self.bot = interaction.client  # type: ignore
        self.channel = interaction.channel
        self.author = interaction.user
        self.message = None

    async def reply(self, content: str = None, **kwargs):
        try:
            if self._i.response.is_done():
                return await self._i.followup.send(content or "\u200b", **kwargs)
            else:
                return await self._i.response.send_message(content or "\u200b", **kwargs)
        except Exception:
            # Fallback to channel if needed
            if self.channel:
                try:
                    return await self.channel.send(content or "\u200b", **kwargs)
                except Exception:
                    pass

    async def send(self, content: str = None, **kwargs):
        return await self.reply(content, **kwargs)


# =================================================================
#  A) USER COMMAND: /act   (phase-aware: day or night)
# =================================================================
class ActionsCog(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot

    @app_commands.command(name="act", description="Register your action for the current phase (day or night).")
    @app_commands.describe(
        target="Target player (optional)",
        note="Free text note about your action (optional)",
        public="Post a public acknowledgement instead of ephemeral (default: false)",
    )
    async def act(
        self, 
        interaction: discord.Interaction, 
        target: discord.Member | None = None, 
        note: str = "", 
        public: bool = False
    ):
        # Defer first to avoid Unknown interaction if anything takes long
        await interaction.response.defer(ephemeral=not public)
        ctx = InteractionCtx(interaction)

        # Resolve phase automatically from game.phase
        phase = (getattr(game, "phase", "day") or "day").lower()
        if phase not in ("day", "night"):
            phase = "day"

        # Check we actually are in a timed phase that accepts actions
        if phase == "night" and not getattr(game, "night_deadline_epoch", None):
            return await ctx.reply("It is not **Night** phase.", ephemeral=not public)
        if phase == "day" and not getattr(game, "day_deadline_epoch", None):
            # Allow you to tighten this policy to only certain day windows if desired
            return await ctx.reply("It is not **Day** phase.", ephemeral=not public)

        actor_uid = str(interaction.user.id)
        players = getattr(game, "players", {}) or {}
        actor = players.get(actor_uid)
        if not actor or not actor.get("alive", True):
            return await ctx.reply("You are not registered or you are not alive.", ephemeral=not public)

        # Require users to run /act from their own role channel, if set
        role_ch_id = (actor.get("role_channel_id") if isinstance(actor, dict) else None)
        if role_ch_id and interaction.channel and interaction.channel.id != role_ch_id:
            return await ctx.reply("Use your role’s private channel to /act.", ephemeral=not public)

        # Permission to act in this phase comes from flags: day_act / night_act
        flags = actor.get("flags", {}) or {}
        needed_flag = "day_act" if phase == "day" else "night_act"
        if not bool(flags.get(needed_flag, False)):
            return await ctx.reply(f"You are not allowed to act during **{phase.title()}**.", ephemeral=not public)

        # Validate target if provided
        target_uid = str(target.id) if target else None
        if target_uid:
            t = players.get(target_uid)
            if not t:
                return await ctx.reply("Target is not registered.", ephemeral=not public)
            if not t.get("alive", True):
                return await ctx.reply("Target is not alive.", ephemeral=not public)


        # Decide action kind for this phase (day/night)
        action_kind = "day_action" if phase == "day" else "night_action"

        # Status engine gate (blocks like Paralyzed/Drowsiness/Jailed; Confusion may redirect)
        check = SE.check_action(game, actor_uid, action_kind, target_uid)
        if not check.get("allowed", True):
            # You can customize this message further if you want per-status flavor.
            # check["reason"] can be "blocked_by:<StatusName>"
            return await ctx.reply("You're affected and can't use your abilities right now.", ephemeral=not public)

        # Confusion: action may be redirected to a random alive player
        if check.get("redirect_to"):
            target_uid = check["redirect_to"]
            # Optional flavor (the coin toss message). Comment out if you prefer silent redirect.
            try:
                await ctx.reply(f"🌀 You're Confused... your action was redirected.", ephemeral=True)
            except Exception:
                pass

        # Determine logical number for the phase (Day N / Night N)
        phase_norm = "day" if phase == "day" else "night"
        number = act_core.current_cycle_number(phase_norm)

        # Build action record (schema is flexible; these fields are common)
        action_record = {
            "uid": actor_uid,
            "action": "act",
            "target": target_uid,
            "note": (note or "").strip(),
            "at": int(time.time()),
        }

        # Persist into the correct bucket
        store_attr = "day_actions" if phase_norm == "day" else "night_actions"
        store = getattr(game, store_attr, None)
        if not isinstance(store, dict):
            store = {}
            setattr(game, store_attr, store)
        bucket = store.setdefault(str(number), {})
        bucket[actor_uid] = action_record

        # Save state
        await save_state()

        # Optional audit log
        try:
            await log_event(
                self.bot,
                interaction.guild.id if interaction.guild else None,
                f"{phase_norm.upper()}_ACTION",
                actor_id=actor_uid,
                target_id=(target_uid or "None"),
                note=(note or "")
            )
        except Exception:
            pass

        await ctx.reply(f"✅ Action registered for **{phase_norm.title()} {number}**.", ephemeral=not public)


# =================================================================
#  B) ADMIN GROUP: /actions logs | /actions breakdown
# =================================================================
PHASE_CHOICES = [
    app_commands.Choice(name="auto", value="auto"),
    app_commands.Choice(name="day", value="day"),
    app_commands.Choice(name="night", value="night"),
]

def _resolve_phase(phase: Optional[str]) -> str:
    if (phase or "").lower() == "auto" or not phase:
        return (getattr(game, "phase", "day") or "day").lower()
    p = (phase or "").lower()
    return p if p in ("day", "night") else "night"


class ActionsAdminCog(commands.GroupCog, name="actions", description="Day/Night actions utilities (admin)"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # /actions logs
    @app_commands.command(
        name="logs",
        description="Phase logs: user=all numbers; number=specific Day/Night."
    )
    @app_commands.describe(
        phase="Which phase to inspect (auto/day/night)",
        number="Day/Night number; omit to use current for that phase",
        user="Filter by user (if provided WITHOUT number -> all numbers for that phase)",
        public="Post publicly instead of ephemeral (default: false)",
    )
    @app_commands.choices(phase=PHASE_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def logs_cmd(
        self,
        interaction: discord.Interaction,
        phase: Optional[app_commands.Choice[str]] = None,
        number: Optional[int] = None,
        user: Optional[discord.Member] = None,
        public: bool = False,
    ):
        await interaction.response.defer(ephemeral=not public)
        ctx = InteractionCtx(interaction)

        p = _resolve_phase(phase.value if phase else None)

        # Case A: user given + number omitted => ALL numbers for that phase
        if user is not None and number is None:
            uid = str(user.id)
            rows = act_core.get_user_logs_all(p, uid)

            title = f"{p.title()} Actions — {user.display_name} (ALL {p}s)"
            embed = discord.Embed(title=title, color=0x8E44AD)

            if not rows:
                embed.description = "No actions recorded for this user."
                return await ctx.reply(embed=embed, ephemeral=not public)

            # Group by number
            by_num: dict[int, list[dict]] = {}
            for n, act in rows:
                by_num.setdefault(n, []).append(act)

            for n in sorted(by_num.keys()):
                acts = by_num[n]
                lines = [_fmt_action_line(a) for a in acts]
                embed.add_field(name=f"{p.title()} {n}", value=("\n".join(lines)[:1024] or "—"), inline=False)

            return await ctx.reply(embed=embed, ephemeral=not public)

        # Case B: specific number (with or without user) OR default current
        n = number if number is not None else act_core.current_cycle_number(p)
        uid = str(user.id) if user else None
        rows = act_core.get_logs(p, n, uid)

        title = f"{p.title()} {n} — Action Logs" + (f" (user: {user.display_name})" if user else "")
        embed = discord.Embed(title=title, color=0x8E44AD)

        if not rows:
            embed.description = "No actions recorded."
            return await ctx.reply(embed=embed, ephemeral=not public)

        # Group by user
        by_user: dict[str, list[dict]] = {}
        for r in rows:
            u = str(r.get("uid"))
            by_user.setdefault(u, []).append(r)

        for u, acts in by_user.items():
            lines = [_fmt_action_line(a) for a in acts]
            name = _label_from_uid(u)
            embed.add_field(name=f"{name} ({u})", value=("\n".join(lines)[:1024] or "—"), inline=False)


        await ctx.reply(embed=embed, ephemeral=not public)

    # /actions breakdown
    @app_commands.command(
        name="breakdown",
        description="Who can act, who acted, who is missing (for the chosen phase)."
    )
    @app_commands.describe(
        phase="Which phase to inspect (auto/day/night)",
        number="Day/Night number; omit to use current for that phase",
        public="Post publicly instead of ephemeral (default: false)",
    )
    @app_commands.choices(phase=PHASE_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def breakdown_cmd(
        self,
        interaction: discord.Interaction,
        phase: Optional[app_commands.Choice[str]] = None,
        number: Optional[int] = None,
        public: bool = False,
    ):
        await interaction.response.defer(ephemeral=not public)
        ctx = InteractionCtx(interaction)

        p = _resolve_phase(phase.value if phase else None)
        n = number if number is not None else act_core.current_cycle_number(p)

        can_act = set(act_core.actors_for_phase(p))               # alive + flags.day_act/night_act == True
        acted = set(act_core.acted_uids(p, n))                    # those who recorded an action for that number

        missing = sorted(can_act - acted)
        acted_sorted = sorted(acted & can_act)

        def fmt_names(uids: List[str]) -> str:
            if not uids:
                return "—"
            names = []
            for uid in uids[:24]:
                pdata = game.players.get(uid, {})
                label = pdata.get("name") or pdata.get("alias") or f"<@{uid}>"
                names.append(f"`{label}`")
            extra = len(uids) - min(len(uids), 24)
            if extra > 0:
                names.append(f"… (+{extra} more)")
            return ", ".join(names)

        color = 0x2C3E50 if p == "night" else 0x3498DB
        embed = discord.Embed(
            title=f"{p.title()} {n} — Act Breakdown",
            description="\n".join([
                f"**Can act:** {len(can_act)}",
                f"**Acted:** {len(acted_sorted)}",
                f"**Missing:** {len(missing)}",
            ]),
            color=color
        )
        embed.add_field(name="Acted", value=fmt_names(acted_sorted), inline=False)
        embed.add_field(name="Missing", value=fmt_names(missing), inline=False)

        await ctx.reply(embed=embed, ephemeral=not public)


# Setup: load both cogs
async def setup(bot: commands.Bot):
    await bot.add_cog(ActionsCog(bot))          # /act
    await bot.add_cog(ActionsAdminCog(bot))     # /actions logs, /actions breakdown```

-----
## cognitas/cogs/fun.py

```python
import random
import discord
from discord import app_commands
from discord.ext import commands
from ..core import johnbotjovi

class FunCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="dice", description="Roll a die")
    async def dice(self, interaction, faces: int = 20):
        faces = max(2, min(1000, faces))
        await interaction.response.send_message(f"🎲 {random.randint(1, faces)} (1–{faces})")

    @app_commands.command(name="coin", description="Toss a coin")
    async def coin(self, interaction):
        await interaction.response.send_message("🪙 Heads" if random.random() < 0.5 else "🪙 Tails")
        
    @app_commands.command(name="lynch", description="Generate a lynch poster using the target's avatar.")
    @app_commands.describe(target="Target player to feature on the poster")
    async def lynch_cmd(self, interaction: discord.Interaction, target: discord.Member):
        await interaction.response.defer()
        f = await johnbotjovi.lynch(target)
        if f is None:
            return await interaction.followup.send(
                f"LYNCH! {target.mention} — (Pillow not available or no backgrounds found)"
            )
        await interaction.followup.send(f"LYNCH! {target.mention}", file=f)
        
async def setup(bot): await bot.add_cog(FunCog(bot))

```

-----
## cognitas/cogs/game.py

```python
import discord
from discord import app_commands
from discord.ext import commands
from ..core import game as game_core
from .. import config as cfg


class GameCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="game_start", description="Iniciar partida con profile (admin)")
    @app_commands.describe(profile="default | smt | ...")
    @app_commands.default_permissions(administrator=True)
    async def game_start(self, interaction: discord.Interaction, profile: str | None = None):
        ctx = await commands.Context.from_interaction(interaction)
        await game_core.start(ctx, profile=(profile or cfg.DEFAULT_PROFILE), day_channel=interaction.channel, admin_channel=None)
        
    @app_commands.command(name="game_reset", description="Hard reset of game state")
    @app_commands.default_permissions(administrator=True)
    async def game_reset(self, interaction: discord.Interaction):
        await game_core.hard_reset(interaction)

    @app_commands.command(name="finish_game", description="Terminar partida (admin)")
    @app_commands.default_permissions(administrator=True)
    async def finish_game(self, interaction: discord.Interaction, reason: str | None = None):
        ctx = await commands.Context.from_interaction(interaction)
        await game_core.finish(ctx, reason=reason)
        
    @app_commands.command(name="who", description="Info de jugador (admin)")
    @app_commands.default_permissions(administrator=True)
    async def who(self, interaction: discord.Interaction, member: discord.Member | None = None):
        ctx = await commands.Context.from_interaction(interaction)
        await game_core.who(ctx, member)
        
    @app_commands.command(name="assign", description="Asignar rol a jugador (admin)")
    @app_commands.default_permissions(administrator=True)
    async def assign(self, interaction: discord.Interaction, member: discord.Member, role_name: str):
        ctx = await commands.Context.from_interaction(interaction)
        await game_core.assign_role(ctx, member, role_name)
        
async def setup(bot): await bot.add_cog(GameCog(bot))

```

-----
## cognitas/cogs/help.py

```python
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from ..core.state import game

class HelpCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="help", description="Show available commands")
    async def help(self, interaction: discord.Interaction):
        user = interaction.user
        is_admin = user.guild_permissions.administrator
        can_purge = user.guild_permissions.manage_messages
        phase = getattr(game, "moon_phase", None)

        embed = discord.Embed(
            title="Asdrubot — Commands",
            description="Slash command index. You will only see admin/mod sections if you have permissions.",
            color=0x2ecc71
        )
        if phase:
            embed.set_footer(text=f"Asdrubot v2.0 — Moon: {phase}")
        else:
            embed.set_footer(text="Asdrubot v2.0 — Slash Edition")

        # Players
        embed.add_field(
            name="👥 Players",
            value="\n".join([
                "`/player list`",
                "`/player register @user [name]` *(admin)*",
                "`/player unregister @user` *(admin)*",
                "`/player rename @user <new_name>` *(admin)*",
                "`/player alias_show @user`",
                "`/player alias_add @user <alias>` *(admin)*",
                "`/player alias_del @user <alias>` *(admin)*",
            ]),
            inline=False
        )





        # Voting & Phases (user/admin mixed)
        embed.add_field(
            name="🗳️ Voting & Phases",
            value="\n".join([
                "`/vote cast @user`",
                "`/vote clear`",
                "`/vote mine`",
                "`/vote end_day` *(2/3 of alive)*",
                "`/votes`",
                "`/status`",
                "`/start_day [duration] [channel] [force]` *(admin)*",
                "`/end_day` *(admin)*",
                "`/start_night [duration]` *(admin)*",
                "`/end_night` *(admin)*",
            ]),
            inline=False
        )

        # Game (admin)
        if is_admin:
            embed.add_field(
                name="🎮 Game (admin)",
                value="\n".join([
                    "`/game_start [profile]`",
                    "`/game_reset`",
                    "`/finish_game [reason]`",
                    "`/who [@user]`",
                    "`/assign @user <role>`",
                ]),
                inline=False
            )

        # Moderation (admin/mod)
        if is_admin or can_purge:
            embed.add_field(
                name="🛡️ Moderation",
                value="\n".join([
                    "`/bc <text>` *(admin)*",
                    "`/set_day_channel [#channel]` *(admin)*",
                    "`/set_admin_channel [#channel]` *(admin)*",
                    "`/set_log_channel [#channel]` *(admin)*",
                    "`/show_channels` *(admin)*",
                    "`/purge N` *(manage_messages)*",
                ]),
                inline=False
            )

        # Utilities (everyone)
        embed.add_field(
            name="🎲 Utilities",
            value="`/dice [faces]`, `/coin`",
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot): await bot.add_cog(HelpCog(bot))

```

-----
## cognitas/cogs/maintenance.py

```python
from __future__ import annotations
from typing import List, Optional
import discord
from discord import app_commands
from discord.ext import commands

def _local_has_subs(bot: commands.Bot, name: str) -> bool:
    try:
        for c in bot.tree.get_commands():
            if c.name == name:
                return bool(getattr(c, "options", None))
    except Exception:
        pass
    return False

class Maintenance(commands.Cog):
    """Admin utilities for slash commands maintenance."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="sync_here", description="Sync slash commands for THIS server (instant).")
    @app_commands.default_permissions(administrator=True)
    async def sync_here(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        # Optional: bring global commands to this guild so they appear immediately
        try:
            self.bot.tree.copy_global_to(guild=interaction.guild)
        except Exception:
            pass
        synced = await self.bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send(f"✅ Synced {len(synced)} commands for this server.", ephemeral=True)

    @app_commands.command(name="list_commands", description="List remote slash commands (global or this guild).")
    @app_commands.describe(scope="Where to inspect: 'global' or 'guild'")
    @app_commands.choices(scope=[
        app_commands.Choice(name="global", value="global"),
        app_commands.Choice(name="guild", value="guild"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def list_commands(
        self,
        interaction: discord.Interaction,
        scope: app_commands.Choice[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if scope is None or scope.value == "global":
            remote = await self.bot.tree.fetch_commands()
            title = "Global commands (remote)"
            gid = None
        else:
            if not interaction.guild:
                return await interaction.followup.send("Use this in a server.", ephemeral=True)
            remote = await self.bot.tree.fetch_commands(guild=interaction.guild)
            title = f"Guild commands (remote) — {interaction.guild.name}"
            gid = interaction.guild.id

        lines: List[str] = []
        for cmd in remote:
            kind = "slash"
            if cmd.type is discord.AppCommandType.user:
                kind = "user"
            elif cmd.type is discord.AppCommandType.message:
                kind = "message"
            has_opts = bool(getattr(cmd, "options", None))
            lines.append(f"- /{cmd.name}  ({kind})  {'with subs' if has_opts else 'no subs'}")

        local_names = sorted(c.qualified_name for c in self.bot.tree.get_commands())
        await interaction.followup.send(
            f"**{title}**\n" +
            ("\n".join(lines) if lines else "_none_") +
            "\n\n**Local (in-process) commands:**\n" +
            ("\n".join(f"- /{n}" for n in local_names) if local_names else "_none_"),
            ephemeral=True,
        )

    @app_commands.command(name="clean_commands", description="Remove stray slash commands then sync (global or this guild).")
    @app_commands.describe(
        scope="Where to clean: 'global' or 'guild'",
        nuke="Delete ALL in chosen scope before syncing (dangerous)",
        prune_empty_roots="Remove chat-input roots with NO subcommands when local has a grouped version",
        also_remove="Extra names to remove (comma-separated), e.g. 'vote, help'",
    )
    @app_commands.choices(scope=[
        app_commands.Choice(name="global", value="global"),
        app_commands.Choice(name="guild", value="guild"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def clean_commands(
        self,
        interaction: discord.Interaction,
        scope: app_commands.Choice[str] = None,
        nuke: bool = False,
        prune_empty_roots: bool = True,
        also_remove: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)

        guild_obj: discord.abc.Snowflake | None
        if scope is None or scope.value == "global":
            guild_obj = None
            remote = await self.bot.tree.fetch_commands()
            scope_label = "global"
        else:
            if not interaction.guild:
                return await interaction.followup.send("Use this in a server.", ephemeral=True)
            guild_obj = interaction.guild
            remote = await self.bot.tree.fetch_commands(guild=guild_obj)
            scope_label = f"guild:{interaction.guild.id}"

        removed = []
        if nuke:
            self.bot.tree.clear_commands(guild=guild_obj)
            await self.bot.tree.sync(guild=guild_obj)
            return await interaction.followup.send(
                f"🧨 Nuked and re-synced **{scope_label}** commands.", ephemeral=True
            )

        extra_names = set(n.strip().lower() for n in (also_remove or "").split(",") if n.strip())
        for cmd in remote:
            try:
                if cmd.type is not discord.AppCommandType.chat_input:
                    continue
                name = cmd.name.lower()
                opts = getattr(cmd, "options", None)

                if name in extra_names:
                    await self.bot.tree.remove_command(name, type=discord.AppCommandType.chat_input, guild=guild_obj)
                    removed.append(name)
                    continue

                if prune_empty_roots and (not opts) and _local_has_subs(self.bot, name):
                    await self.bot.tree.remove_command(name, type=discord.AppCommandType.chat_input, guild=guild_obj)
                    removed.append(name)
            except Exception as e:
                removed.append(f"{cmd.name} (error: {e})")

        await self.bot.tree.sync(guild=guild_obj)

        if removed:
            await interaction.followup.send(
                f"🧹 Removed from **{scope_label}**: {', '.join(sorted(set(removed)))}\n✔️ Synced.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(f"Nothing to remove in **{scope_label}**. ✔️ Synced.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Maintenance(bot))
```

-----
## cognitas/cogs/moderation.py

```python
import discord
import asyncio
from discord import app_commands
from discord.ext import commands
from ..core.state import game
from ..core.game import set_channels
from ..core.logs import set_log_channel as set_log_channel_core

from ..core.storage import save_state
from ..core.game import _load_expansion_for
from typing import Literal
from .. import config as cfg

class ModerationCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="bc", description="Broadcast to the Day channel (admin)")
    @app_commands.default_permissions(administrator=True)
    async def bc(self, interaction: discord.Interaction, text: str):
        if not game.day_channel_id:
            return await interaction.response.send_message("No Day channel configured.", ephemeral=True)
        chan = interaction.guild.get_channel(game.day_channel_id)
        if not chan:
            return await interaction.response.send_message("Day channel not found.", ephemeral=True)
        await chan.send(text)
        await interaction.response.send_message("✅ Broadcast sent.", ephemeral=True)

    @app_commands.command(name="set_channels", description="Bind Day/Night/Admin channels for the game.")
    @app_commands.describe(
        day="Day channel",
        night="Night channel",
        admin="Admin control channel",
    )
    @app_commands.default_permissions(administrator=True)
    async def set_channels_cmd(
        self,
        interaction: discord.Interaction,
        day: discord.TextChannel | None = None,
        night: discord.TextChannel | None = None,
        admin: discord.TextChannel | None = None,
    ):
        await set_channels(day or interaction.channel, night, admin)
        await interaction.response.send_message("✅ Channels configured.", ephemeral=True)

    @app_commands.command(name="set_log_channel", description="Set the logs channel.")
    @app_commands.describe(channel="Logs channel (defaults to current if omitted).")
    @app_commands.default_permissions(administrator=True)
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        target = channel or interaction.channel
        await set_log_channel_core(target)
        await interaction.response.send_message(f"🧾 Logs channel set to {target.mention}", ephemeral=True)

    # ------------------------------
    # Admin: expansion & phase tools
    # ------------------------------
    @app_commands.command(name="set_expansion", description="Set the active expansion (preferably before starting).")
    @app_commands.describe(
        profile="Profile name, e.g. 'default' or 'smt'.",
        force="Allow switching after game start (dangerous)."
    )
    @app_commands.default_permissions(administrator=True)
    async def set_expansion(self, interaction: discord.Interaction, profile: str, force: bool = False):
        phase = getattr(game, "phase", "setup")
        if phase != "setup" and not force:
            return await interaction.response.send_message(
                f"⚠️ Game phase is `{phase}`. Use `force:true` to override (not recommended mid-game).",
                ephemeral=True
            )
        prof = (profile or "").strip().lower() or "default"
        try:
            exp = _load_expansion_for(prof)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Could not resolve expansion `{profile}`: {e}", ephemeral=True)
        game.profile = prof
        game.expansion = exp
        await save_state()
        await interaction.response.send_message(
            f"✅ Expansion set to **{exp.name}** (profile=`{prof}`).",
            ephemeral=True
        )

    @app_commands.command(name="set_phase", description="Force the game phase to day or night (no side-effects).")
    @app_commands.describe(phase="Target phase: 'day' or 'night'.")
    @app_commands.default_permissions(administrator=True)
    async def set_phase(self, interaction: discord.Interaction, phase: Literal["day", "night"]):
        game.phase = phase
        await save_state()
        await interaction.response.send_message(f"✅ Phase set to **{phase}** (forced).", ephemeral=True)

    @app_commands.command(name="set_day", description="Set the current Day number explicitly.")
    @app_commands.describe(number="New current day number (integer ≥ 1).")
    @app_commands.default_permissions(administrator=True)
    async def set_day(self, interaction: discord.Interaction, number: int):
        if number < 1:
            return await interaction.response.send_message("❌ Day must be ≥ 1.", ephemeral=True)
        game.current_day_number = int(number)
        await save_state()
        await interaction.response.send_message(f"✅ Current day set to **{number}**.", ephemeral=True)

    @app_commands.command(name="bump_day", description="Increment or decrement the current Day number.")
    @app_commands.describe(delta="Positive to increment, negative to decrement (e.g., -1).")
    @app_commands.default_permissions(administrator=True)
    async def bump_day(self, interaction: discord.Interaction, delta: int):
        current = int(getattr(game, "current_day_number", 1) or 1)
        new_val = current + int(delta)
        if new_val < 1:
            return await interaction.response.send_message(
                f"❌ Resulting day would be {new_val} (< 1). Aborting.", ephemeral=True
            )
        game.current_day_number = new_val
        await save_state()
        sign = f"+{delta}" if delta >= 0 else f"{delta}"
        await interaction.response.send_message(
            f"✅ Day bumped {sign} → **{new_val}**.", ephemeral=True
        )
    @app_commands.command(name="get_state", description="Show a compact snapshot of the current game state.")
    @app_commands.default_permissions(administrator=True)
    async def get_state(self, interaction: discord.Interaction):
        guild = interaction.guild
        def _m(ch_id):
            if not ch_id or not guild: return "—"
            ch = guild.get_channel(ch_id)
            return ch.mention if ch else f"(missing:{ch_id})"

        profile = getattr(game, "profile", "default")
        exp = getattr(getattr(game, "expansion", None), "name", "base")
        phase = getattr(game, "phase", "setup")
        day_no = int(getattr(game, "current_day_number", 1) or 1)

        # If expansion provides a banner, preview it without posting to public channels
        try:
            banner_preview = (game.expansion.banner_for_day(game) if getattr(game, "expansion", None) else None)
        except Exception:
            banner_preview = None

        msg = (
            f"**Profile:** `{profile}`  •  **Expansion:** `{exp}`\n"
            f"**Phase:** `{phase}`  •  **Day #:** `{day_no}`\n"
            f"**Channels:** Day={_m(getattr(game,'day_channel_id',None))}  •  "
            f"Night={_m(getattr(game,'night_channel_id',None))}  •  "
            f"Admin={_m(getattr(game,'admin_channel_id',None))}  •  "
            f"Logs={_m(getattr(game,'admin_log_channel_id',None))}\n"
            f"{('**Banner preview:** ' + str(banner_preview)) if banner_preview else ''}"
        )
        await interaction.response.send_message(msg, ephemeral=True)




    @app_commands.command(name="purge", description="Delete recent messages in this channel.")
    @app_commands.describe(
        amount="Amount of messages to consider (max 2000).",
        only_bots="If true, only delete messages sent by bots.",
        only_me="If true, only delete messages sent by me (the bot).",
        include_pins="If true, also delete pinned messages.",
        older_than_seconds="Keep messages newer than this many seconds.",
        newer_than_seconds="Keep messages older than this many seconds.",
        reason="A short note for why you are purging (for logs).",
    )
    @app_commands.default_permissions(manage_messages=True)
    async def purge(
        self,
        interaction: discord.Interaction,
        amount: int = 100,
        only_bots: bool = False,
        only_me: bool = False,
        include_pins: bool = False,
        older_than_seconds: int | None = None,
        newer_than_seconds: int | None = None,
        reason: str | None = None,
    ):
        # 1) Basic validation
        if amount < 1 or amount > 2000:
            return await interaction.response.send_message("Amount must be between 1 and 2000.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        # 2) Build checks
        def _check(msg: discord.Message) -> bool:
            if msg.type != discord.MessageType.default:
                return False
            if not include_pins and msg.pinned:
                return False
            if only_bots and not msg.author.bot:
                return False
            if only_me and msg.author.id != interaction.client.user.id:
                return False
            return True

        # 3) Time windows
        now_ts = discord.utils.utcnow().timestamp()
        min_ts = now_ts - older_than_seconds if older_than_seconds else None
        max_ts = now_ts - newer_than_seconds if newer_than_seconds else None

        # 4) Do the purge
        deleted_count = 0
        try:
            async for m in interaction.channel.history(limit=amount, oldest_first=False):
                if not _check(m):
                    continue
                created_ts = m.created_at.timestamp()
                if min_ts and created_ts > min_ts:
                    continue  # too new
                if max_ts and created_ts < max_ts:
                    continue  # too old
                # Prefer bulk delete when possible (Discord API only allows bulk for <14 days)
                if (discord.utils.utcnow() - m.created_at).total_seconds() <= (14 * 24 * 3600):
                    # Bulk delete needs a list; we collect singles if necessary
                    try:
                        await m.delete(reason=reason or "purge")
                        deleted_count += 1
                    except (discord.Forbidden, discord.HTTPException):
                        continue
                else:
                    # Too old for bulk — delete individually
                    try:
                        await m.delete()
                        deleted_count += 1
                        # Be polite with rate limits if many single deletes
                        await asyncio.sleep(0.2)
                    except (discord.Forbidden, discord.HTTPException):
                        continue
        except Exception as e:
            return await interaction.followup.send(f"Failed to fetch history: {e}", ephemeral=True)

        # 6) Single, safe follow-up (no double replies)
        await interaction.followup.send(f"🧹 Purged **{deleted_count}** message(s).", ephemeral=True)

async def setup(bot): await bot.add_cog(ModerationCog(bot))
```

-----
## cognitas/cogs/players.py

```python
from __future__ import annotations

import re
import discord
from discord import app_commands
from discord.ext import commands

from ..core import players as players_core
from ..core.players import get_player_snapshot

# ------------------------------------------------------------
# Interaction -> ctx adapter (uses followup if interaction already responded/deferred)
# ------------------------------------------------------------
class InteractionCtx:
    def __init__(self, interaction: discord.Interaction):
        self._i = interaction
        self.guild = interaction.guild
        self.bot = interaction.client  # type: ignore
        self.channel = interaction.channel
        self.author = interaction.user
        self.message = None  # compat

    async def reply(self, content: str = None, **kwargs):
        try:
            if self._i.response.is_done():
                return await self._i.followup.send(content or "\u200b", **kwargs)
            else:
                return await self._i.response.send_message(content or "\u200b", **kwargs)
        except Exception:
            if self.channel:
                try:
                    return await self.channel.send(content or "\u200b", **kwargs)
                except Exception:
                    pass

    async def send(self, content: str = None, **kwargs):
        return await self.reply(content, **kwargs)


# ------------------------------------------------------------
# Canonical game flags (name -> {type, desc, aliases})
# Used for autocomplete and parsing in /player set_flag
# ------------------------------------------------------------
# types: "bool" | "int" | "str"
FLAG_DEFS: dict[str, dict] = {
    # Voting-related flags
    "hidden_vote": {
        "type": "bool",
        "desc": "Vote remains anonymous in public lists.",
        "aliases": ["incognito", "hidden"],
    },
    "voting_boost": {
        "type": "int",
        "desc": "Adds to the player's ballot weight (1+boost).",
        "aliases": ["vote_boost", "vote_bonus"],
    },
    "no_vote": {
        "type": "bool",
        "desc": "Player cannot cast votes (0 weight).",
        "aliases": ["silenced_vote", "mute_vote"],
    },
    "silenced": {
        "type": "bool",
        "desc": "Player is silenced (treated as 0 voting power).",
        "aliases": [],
    },

    # Lynch threshold modifiers (target extras)
    "lynch_plus": {
        "type": "int",
        "desc": "Extra votes required to lynch this target.",
        "aliases": ["lynch_resistance", "needs_extra_votes"],
    },

    # Night/action examples
    "immune_night": {
        "type": "bool",
        "desc": "Immune to night eliminations.",
        "aliases": ["night_immune"],
    },
    "action_blocked": {
        "type": "bool",
        "desc": "Night action is blocked for this player.",
        "aliases": ["blocked", "role_blocked"],
    },
    "protected": {
        "type": "bool",
        "desc": "Temporarily protected from kills.",
        "aliases": [],
    },
}

# Safe edit field suggestions — NO voting fields
EDIT_FIELD_SUGGESTIONS = [
    "name",
    "alias",
    "role",
    "alive",
    "effects",
    "notes",
]
# Other custom fields still accepted, but not suggested.


# ------------------------------------------------------------
# Autocomplete helpers
# ------------------------------------------------------------
def _all_flag_keys_with_aliases() -> dict[str, str]:
    """
    Returns a map normalized_name -> canonical_key to support aliases.
    """
    out = {}
    for key, meta in FLAG_DEFS.items():
        out[key.lower()] = key
        for a in meta.get("aliases", []):
            out[a.lower()] = key
    return out

def _canonical_flag_name(s: str) -> str | None:
    if not s:
        return None
    return _all_flag_keys_with_aliases().get(s.lower())

async def _flag_name_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    cur = (current or "").lower()
    items: list[tuple[str, str]] = []
    for key, meta in FLAG_DEFS.items():
        label = f"{key} — {meta.get('desc','')}"
        if cur in key.lower() or cur in label.lower():
            items.append((label, key))
        else:
            for a in meta.get("aliases", []):
                if cur in a.lower():
                    items.append((f"{key} (alias: {a}) — {meta.get('desc','')}", key))
                    break
    return [app_commands.Choice(name=lbl[:100], value=val) for lbl, val in items[:25]]

async def _field_name_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    cur = (current or "").lower()
    res = [f for f in EDIT_FIELD_SUGGESTIONS if cur in f.lower()]
    return [app_commands.Choice(name=f, value=f) for f in res[:25]]

async def _flag_value_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    ns = interaction.namespace
    flag_key = _canonical_flag_name(getattr(ns, "flag", "") or "")
    if not flag_key:
        return [app_commands.Choice(name="(select a flag first)", value=current or "")]
    ftype = FLAG_DEFS[flag_key]["type"]
    out: list[app_commands.Choice[str]] = []
    if ftype == "bool":
        for v in ["true", "false", "on", "off", "yes", "no", "1", "0"]:
            if current.lower() in v:
                out.append(app_commands.Choice(name=v, value=v))
    elif ftype == "int":
        for v in ["0", "1", "2", "3", "5", "10"]:
            if current.lower() in v:
                out.append(app_commands.Choice(name=v, value=v))
    else:  # str
        samples = ["note", "tag", "value"]
        for v in samples:
            if current.lower() in v:
                out.append(app_commands.Choice(name=v, value=v))
    return out[:25]

def _parse_flag_value(flag_key: str, raw: str):
    """Parses string into bool/int/str depending on FLAG_DEFS."""
    meta = FLAG_DEFS.get(flag_key) or {}
    ftype = meta.get("type", "str")
    s = (raw or "").strip()

    if ftype == "bool":
        if re.fullmatch(r"(?i)(true|on|yes|y|1)", s):
            return True
        if re.fullmatch(r"(?i)(false|off|no|n|0)", s):
            return False
        return bool(s)
    if ftype == "int":
        try:
            return int(s)
        except Exception:
            return 0
    return s


# ------------------------------------------------------------
# Cog
# ------------------------------------------------------------
class PlayersCog(commands.GroupCog, name="player", description="Manage players"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------
    # List / View
    # -------------------------
    @app_commands.command(name="list", description="List alive and dead players")
    async def list_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.list_players(ctx)

    @app_commands.command(name="view", description="View a player's full state (admin)")
    @app_commands.default_permissions(administrator=True)
    async def view_cmd(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)

        data = get_player_snapshot(str(member.id))
        if not data:
            return await interaction.followup.send("Player not registered.", ephemeral=True)

        def fmt_bool(b: bool | None):
            if b is None:
                return "—"
            return "✅ True" if b else "❌ False"

        def fmt_list(arr):
            return ", ".join(f"`{x}`" for x in arr) if arr else "—"

        def fmt_flags(d):
            if not d:
                return "—"
            parts = [f"`{k}`: `{v}`" for k, v in d.items()]
            if len(parts) > 10:
                parts = parts[:10] + ["…"]
            return "\n".join(parts)

        embed = discord.Embed(
            title=f"Player: {data.get('name') or data.get('alias') or member.display_name}",
            description=f"User: <@{data['uid']}>",
            color=0x3498DB if data.get("alive", True) else 0xC0392B,
        )
        embed.add_field(name="Alive", value=fmt_bool(data.get("alive")), inline=True)
        embed.add_field(name="Role", value=data.get("role") or "—", inline=True)
        embed.add_field(name="Aliases", value=fmt_list(data.get("aliases", [])), inline=False)
        embed.add_field(name="Effects", value=fmt_list(data.get("effects", [])), inline=False)
        embed.add_field(name="Flags", value=fmt_flags(data.get("flags", {})), inline=False)
        embed.set_footer(text="Asdrubot — Player inspector")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # -------------------------
    # Register / Unregister / Rename
    # -------------------------
    @app_commands.command(name="register", description="Register a player (admin)")
    @app_commands.describe(member="Target user to register", name="Optional display name/alias")
    @app_commands.default_permissions(administrator=True)
    async def register_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        name: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.register(ctx, member, name=name)

    @app_commands.command(name="unregister", description="Unregister a player (admin)")
    @app_commands.default_permissions(administrator=True)
    async def unregister_cmd(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.unregister(ctx, member)

    @app_commands.command(name="rename", description="Rename a player (admin)")
    @app_commands.describe(new_name="New display name")
    @app_commands.default_permissions(administrator=True)
    async def rename_cmd(self, interaction: discord.Interaction, member: discord.Member, new_name: str):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.rename(ctx, member, new_name=new_name)

    # -------------------------
    # Aliases
    # -------------------------
    @app_commands.command(name="alias_show", description="Show a player's aliases")
    async def alias_show_cmd(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.alias_show(ctx, member)

    @app_commands.command(name="alias_add", description="Add an alias (admin)")
    @app_commands.default_permissions(administrator=True)
    async def alias_add_cmd(self, interaction: discord.Interaction, member: discord.Member, alias: str):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.alias_add(ctx, member, alias=alias)

    @app_commands.command(name="alias_del", description="Remove an alias (admin)")
    @app_commands.default_permissions(administrator=True)
    async def alias_del_cmd(self, interaction: discord.Interaction, member: discord.Member, alias: str):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.alias_del(ctx, member, alias=alias)

    # -------------------------
    # Generic edit (NO voting fields suggested)
    # -------------------------
    @app_commands.command(name="edit", description="Edit stored player fields (safe suggestions)")
    @app_commands.describe(field="Field name", value="New value")
    @app_commands.autocomplete(field=_field_name_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def edit_cmd(self, interaction: discord.Interaction, member: discord.Member, field: str, value: str):
        """
        Suggests only safe fields (no voting_* / hidden_vote / etc).
        If admin writes a custom field manually, we still pass it to the helper.
        """
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.edit_player(ctx, member, field, value)

    # -------------------------
    # Flags (autocomplete + parsing)
    # -------------------------
    @app_commands.command(name="set_flag", description="Set a flag on a player (with suggestions)")
    @app_commands.describe(flag="Flag key", value="Value (typed: bool/int/str)")
    @app_commands.autocomplete(flag=_flag_name_autocomplete, value=_flag_value_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def set_flag_cmd(self, interaction: discord.Interaction, member: discord.Member, flag: str, value: str):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        canonical = _canonical_flag_name(flag) or flag
        parsed = _parse_flag_value(canonical, value)

        await players_core.set_flag(ctx, member, canonical, parsed)

    @app_commands.command(name="del_flag", description="Remove a flag from a player")
    @app_commands.describe(flag="Flag key to remove")
    @app_commands.autocomplete(flag=_flag_name_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def del_flag_cmd(self, interaction: discord.Interaction, member: discord.Member, flag: str):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        canonical = _canonical_flag_name(flag) or flag
        await players_core.del_flag(ctx, member, canonical)

    # -------------------------
    # Effects
    # -------------------------
    @app_commands.command(name="add_effect", description="Add an effect to a player (admin)")
    @app_commands.default_permissions(administrator=True)
    async def add_effect_cmd(self, interaction: discord.Interaction, member: discord.Member, effect: str):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.add_effect(ctx, member, effect)

    @app_commands.command(name="remove_effect", description="Remove an effect from a player (admin)")
    @app_commands.default_permissions(administrator=True)
    async def remove_effect_cmd(self, interaction: discord.Interaction, member: discord.Member, effect: str):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.remove_effect(ctx, member, effect)

    # -------------------------
    # Kill / Revive
    # -------------------------
    @app_commands.command(name="kill", description="Mark a player as dead (admin)")
    @app_commands.default_permissions(administrator=True)
    async def kill_cmd(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.kill(ctx, member)

    @app_commands.command(name="revive", description="Mark a player as alive (admin)")
    @app_commands.default_permissions(administrator=True)
    async def revive_cmd(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)
        await players_core.revive(ctx, member)


async def setup(bot: commands.Bot):
    await bot.add_cog(PlayersCog(bot))


```

-----
## cognitas/cogs/role_debug.py

```python
from discord import app_commands
from discord.ext import commands
from ..core.state import game

class DebugRoles(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="debug_roles", description="List role keys loaded (admin)")
    @app_commands.default_permissions(administrator=True)
    async def debug_roles(self, interaction):
        idx = getattr(game, "roles", {}) or {}
        keys = sorted(list(idx.keys()))
        # Show the first N to avoid hitting the limit
        sample = keys[:80]
        text = "Loaded roles (keys):\n" + ", ".join(sample) + (", ..." if len(keys) > 80 else "")
        await interaction.response.send_message(text[:1900], ephemeral=True)

async def setup(bot): await bot.add_cog(DebugRoles(bot))
```

-----
## cognitas/cogs/status.py

```python
from __future__ import annotations
import json
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from ..core.state import game
from ..core.storage import save_state
from .. import config as cfg
from ..status import list_registered, get_state_cls
from ..status import engine as SE

class StatusCog(commands.Cog, name="Status"):
    def __init__(self, bot): self.bot = bot

    # autocomplete for status names
    async def _status_autocomplete(self, interaction: discord.Interaction, current: str):
        names = list(list_registered().keys())
        current_l = (current or "").lower()
        return [app_commands.Choice(name=n, value=n)
                for n in names if current_l in n.lower()][:20]

    group = app_commands.Group(name="status", description="Altered states tools (GM)")

    @group.command(name="apply", description="Apply a status to a player (GM only).")
    @app_commands.autocomplete(name=_status_autocomplete)
    @app_commands.describe(
        user="Target player",
        name="Status name",
        duration="Override default duration (ticks); leave empty for default",
        source="Optional source tag (GM/system/uid)",
        meta_json="Optional JSON payload (magnitude, notes...)"
    )
    @app_commands.default_permissions(administrator=True)
    async def apply(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        name: str,
        duration: Optional[int] = None,
        source: Optional[str] = "GM",
        meta_json: Optional[str] = None,
    ):
        meta = {}
        if meta_json:
            try: meta = json.loads(meta_json)
            except Exception: pass

        ok, banner = SE.apply(game, str(user.id), name, source=source, duration=duration, meta=meta)
        await save_state()

        if not ok:
            return await interaction.response.send_message(f"❌ Unknown status `{name}`.", ephemeral=True)

        # deliver banner per visibility (night -> DM; day -> public) is handled by your policy;
        # here: send DM to user always; you can also post public depending on status.
        if banner:
            try:
                await user.send(banner)
            except Exception:
                pass

        await interaction.response.send_message(f"✅ Applied **{name}** to {user.mention}.", ephemeral=True)

    @group.command(name="heal", description="Cleanse statuses from a player (GM only).")
    @app_commands.autocomplete(name=_status_autocomplete)
    @app_commands.describe(
        user="Target player",
        name="Specific status to cleanse (leave empty to cleanse all)",
        all="If true, cleanses all statuses"
    )
    @app_commands.default_permissions(administrator=True)
    async def heal(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        name: Optional[str] = None,
        all: Optional[bool] = False,
    ):
        banners = SE.heal(game, str(user.id), name=name, all_=bool(all))
        await save_state()

        # DM banners to the user
        for b in banners:
            try: await user.send(b)
            except Exception: pass

        detail = f"all statuses" if all else (f"`{name}`" if name else "nothing")
        await interaction.response.send_message(f"✅ Cleansed {detail} from {user.mention}.", ephemeral=True)

    @group.command(name="list", description="List statuses; if user omitted, shows totals.")
    @app_commands.default_permissions(administrator=True)
    async def list_(
        self, interaction: discord.Interaction, user: Optional[discord.Member] = None
    ):
        if user:
            m = SE.list_active(game, str(user.id))
            if not m:
                return await interaction.response.send_message(f"{user.mention} has no active statuses.", ephemeral=True)
            lines = [f"- **{k}**: {v.get('remaining',0)}t, stacks={v.get('stacks',1)}" for k, v in m.items()]
            return await interaction.response.send_message("\n".join(lines), ephemeral=True)
        else:
            total = sum(len(v) for v in getattr(game, "status_map", {}).values()) if hasattr(game, "status_map") else 0
            return await interaction.response.send_message(f"Total active statuses: **{total}**", ephemeral=True)

    @group.command(name="inspect", description="Show docs for a status type.")
    @app_commands.autocomplete(name=_status_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def inspect(self, interaction: discord.Interaction, name: str):
        cls = get_state_cls(name)
        if not cls:
            return await interaction.response.send_message("Unknown status.", ephemeral=True)
        s = cls()
        doc = (cls.__doc__ or "").strip()
        blocks = ", ".join(k for k, v in getattr(s, "blocks", {}).items() if v) or "—"
        msg = (f"**{s.name}** ({s.type}) vis={s.visibility} policy={s.stack_policy} "
               f"default_dur={s.default_duration}\nBlocks: {blocks}\n{doc}")
        await interaction.response.send_message(msg, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(StatusCog(bot))
```

-----
## cognitas/cogs/timezones.py

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

# Prefer Python's stdlib zoneinfo (py3.9+). Fall back to pytz if needed.
try:
    from zoneinfo import ZoneInfo  # type: ignore
    _HAS_ZONEINFO = True
except Exception:  # pragma: no cover
    _HAS_ZONEINFO = False
    import pytz  # type: ignore

# Persist using your existing storage
from ..core.state import game
from ..core.storage import save_state


# -----------------------------
# Data model (persisted in state)
# -----------------------------
@dataclass
class TZEntry:
    channel_id: int                # Voice channel to rename
    tz: str                        # IANA tz like "Europe/Madrid"
    label: str                     # Short name shown in the channel
    fmt: str = "{HH}:{MM} {abbr}"  # Formatting template

@dataclass
class GuildTZConfig:
    enabled: bool = True
    interval_minutes: int = 10
    entries: List[TZEntry] = None  # filled at runtime

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "interval_minutes": self.interval_minutes,
            "entries": [asdict(e) for e in (self.entries or [])],
        }

    @staticmethod
    def from_dict(d: dict) -> "GuildTZConfig":
        if not d:
            return GuildTZConfig(enabled=True, interval_minutes=10, entries=[])
        return GuildTZConfig(
            enabled=bool(d.get("enabled", True)),
            interval_minutes=int(d.get("interval_minutes", 10) or 10),
            entries=[TZEntry(**x) for x in d.get("entries", [])],
        )


# -----------------------------
# Helpers
# -----------------------------
def _state_get_all() -> Dict[str, dict]:
    """Fetch root dict for tzclocks from game state."""
    root = getattr(game, "tzclocks", None)
    if not isinstance(root, dict):
        root = {}
        game.tzclocks = root
    return root

def _state_get_guild(guild_id: int) -> GuildTZConfig:
    root = _state_get_all()
    raw = root.get(str(guild_id), {})
    return GuildTZConfig.from_dict(raw)

def _state_save_guild(guild_id: int, cfg: GuildTZConfig) -> None:
    root = _state_get_all()
    root[str(guild_id)] = cfg.to_dict()

async def _persist():
    try:
        await save_state()
    except Exception:
        pass

def _now_in_tz(tzname: str) -> datetime:
    if _HAS_ZONEINFO:
        try:
            tz = ZoneInfo(tzname)
        except Exception:
            tz = ZoneInfo("UTC")
        return datetime.now(tz)
    else:  # pytz fallback
        try:
            tz = pytz.timezone(tzname)
        except Exception:
            tz = pytz.UTC
        return datetime.now(tz)

def _format_time(dt: datetime, fmt: str) -> str:
    # tokens: {HH} 24h, {MM} zero-padded, {abbr} TZ short name
    HH = f"{dt.hour:02d}"
    MM = f"{dt.minute:02d}"
    try:
        abbr = dt.tzname() or ""
    except Exception:
        abbr = ""
    return fmt.replace("{HH}", HH).replace("{MM}", MM).replace("{abbr}", abbr).strip()


# -----------------------------
# Cog
# -----------------------------
class TimezonesCog(commands.Cog, name="Timezones"):
    """
    Periodically renames selected voice channels to show the current time in given timezones.
    Safe by default: only updates when the name actually changes (reduces rate-limit pressure).
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # A single background loop handles all guilds
        self._loop_task: Optional[asyncio.Task] = None
        self._loop_running = False

    # ------------- Lifecycle -------------
    async def cog_load(self):
        # Start loop once the cog is loaded
        if not self._loop_running:
            self._loop_running = True
            self._loop_task = asyncio.create_task(self._main_loop(), name="tzclocks_loop")

    async def cog_unload(self):
        # Stop loop gracefully
        self._loop_running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except Exception:
                pass

    # ------------- Background Loop -------------
    async def _main_loop(self):
        """
        A dynamic loop: checks min interval across all guild configs, sleeps that much,
        then applies updates. This keeps changes reasonably frequent without spamming.
        """
        # Initial small delay to let the bot fully connect
        await asyncio.sleep(5)

        while self._loop_running:
            try:
                min_interval = self._compute_min_interval()  # in minutes
                await self._tick_all_guilds()
            except Exception:
                # Never crash the loop
                pass

            # Sleep with a sane default if nothing configured
            sleep_min = min_interval if min_interval > 0 else 10
            await asyncio.sleep(sleep_min * 60)

    def _compute_min_interval(self) -> int:
        root = _state_get_all()
        if not root:
            return 10
        mins = []
        for raw in root.values():
            try:
                mins.append(int(raw.get("interval_minutes", 10) or 10))
            except Exception:
                continue
        return min(mins) if mins else 10

    async def _tick_all_guilds(self):
        for guild in list(self.bot.guilds):
            cfg = _state_get_guild(guild.id)
            if not cfg.enabled or not cfg.entries:
                continue
            await self._update_guild(guild, cfg)

    async def _update_guild(self, guild: discord.Guild, cfg: GuildTZConfig):
        for entry in list(cfg.entries or []):
            ch = guild.get_channel(entry.channel_id)
            if not isinstance(ch, discord.VoiceChannel):
                continue  # ignore missing or wrong type

            now_dt = _now_in_tz(entry.tz)
            time_str = _format_time(now_dt, entry.fmt)
            new_name = f"{entry.label}: {time_str}"

            # Only rename if changed (saves rate limit)
            if ch.name != new_name:
                try:
                    await ch.edit(name=new_name, reason="Timezone clock update")
                except (discord.Forbidden, discord.HTTPException):
                    continue  # skip silently if no perms

    # ------------- Commands -------------
    # Group under /tz for cleanliness
    tz = app_commands.Group(name="tz", description="Timezone clock tools")

    @tz.command(name="add", description="Add a timezone clock on a voice channel.")
    @app_commands.describe(
        channel="Voice channel to rename periodically",
        tz="IANA timezone, e.g., 'Europe/Madrid', 'America/New_York'",
        label="Short label to show (e.g., 'Madrid', 'NYC')",
        fmt="Optional format: tokens {HH} {MM} {abbr}. Default: '{HH}:{MM} {abbr}'"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def tz_add(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        tz: str,
        label: str,
        fmt: Optional[str] = None,
    ):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Guild context required.", ephemeral=True)

        cfg = _state_get_guild(guild.id)
        if cfg.entries is None:
            cfg.entries = []

        # Prevent duplicates for the same channel
        for e in cfg.entries:
            if e.channel_id == channel.id:
                return await interaction.response.send_message(
                    "This channel already has a timezone clock configured. Use `/tz edit` or `/tz remove`.",
                    ephemeral=True
                )

        cfg.entries.append(TZEntry(channel_id=channel.id, tz=tz, label=label, fmt=fmt or "{HH}:{MM} {abbr}"))
        _state_save_guild(guild.id, cfg)
        await _persist()
        await interaction.response.send_message(
            f"✅ Added TZ clock on {channel.mention}: `{label}` @ `{tz}`.", ephemeral=True
        )

    @tz.command(name="remove", description="Remove a timezone clock from a voice channel.")
    @app_commands.describe(channel="Voice channel previously configured for TZ clock")
    @app_commands.default_permissions(manage_guild=True)
    async def tz_remove(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Guild context required.", ephemeral=True)

        cfg = _state_get_guild(guild.id)
        before = len(cfg.entries or [])
        cfg.entries = [e for e in (cfg.entries or []) if e.channel_id != channel.id]
        _state_save_guild(guild.id, cfg)
        await _persist()

        if len(cfg.entries or []) < before:
            await interaction.response.send_message(f"✅ Removed TZ clock from {channel.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message("No TZ clock was set for that channel.", ephemeral=True)

    @tz.command(name="list", description="List all timezone clocks for this server.")
    @app_commands.default_permissions(manage_guild=True)
    async def tz_list(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Guild context required.", ephemeral=True)

        cfg = _state_get_guild(guild.id)
        if not cfg.entries:
            return await interaction.response.send_message("No timezone clocks configured.", ephemeral=True)

        def _mention(cid: int) -> str:
            ch = guild.get_channel(cid)
            return ch.mention if ch else f"(missing:{cid})"

        lines = [
            f"- { _mention(e.channel_id) } — **{e.label}** @ `{e.tz}`  (fmt: `{e.fmt}`)"
            for e in cfg.entries
        ]
        await interaction.response.send_message(
            f"**Enabled:** `{cfg.enabled}` • **Interval:** `{cfg.interval_minutes}m`\n" + "\n".join(lines),
            ephemeral=True
        )

    @tz.command(name="interval", description="Set global update interval (minutes) for this server.")
    @app_commands.describe(minutes="How often to update channel names (recommended ≥ 5).")
    @app_commands.default_permissions(manage_guild=True)
    async def tz_interval(self, interaction: discord.Interaction, minutes: int):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Guild context required.", ephemeral=True)

        if minutes < 2:
            return await interaction.response.send_message("Please choose an interval ≥ 2 minutes.", ephemeral=True)

        cfg = _state_get_guild(guild.id)
        cfg.interval_minutes = int(minutes)
        _state_save_guild(guild.id, cfg)
        await _persist()
        await interaction.response.send_message(f"✅ Interval set to `{minutes}m`.", ephemeral=True)

    @tz.command(name="toggle", description="Enable or disable timezone updates for this server.")
    @app_commands.describe(enabled="True to enable, False to disable.")
    @app_commands.default_permissions(manage_guild=True)
    async def tz_toggle(self, interaction: discord.Interaction, enabled: bool):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Guild context required.", ephemeral=True)

        cfg = _state_get_guild(guild.id)
        cfg.enabled = bool(enabled)
        _state_save_guild(guild.id, cfg)
        await _persist()
        await interaction.response.send_message(f"✅ Timezone updates {'enabled' if enabled else 'disabled'}.", ephemeral=True)

    @tz.command(name="edit", description="Edit an existing timezone clock entry.")
    @app_commands.describe(
        channel="Target voice channel",
        tz="New IANA timezone (leave empty to keep current)",
        label="New label (leave empty to keep current)",
        fmt="New format (leave empty to keep current)"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def tz_edit(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        tz: Optional[str] = None,
        label: Optional[str] = None,
        fmt: Optional[str] = None,
    ):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Guild context required.", ephemeral=True)

        cfg = _state_get_guild(guild.id)
        found = None
        for e in (cfg.entries or []):
            if e.channel_id == channel.id:
                found = e
                break

        if not found:
            return await interaction.response.send_message("No TZ clock configured for that channel.", ephemeral=True)

        if tz:    found.tz = tz
        if label: found.label = label
        if fmt:   found.fmt = fmt

        _state_save_guild(guild.id, cfg)
        await _persist()
        await interaction.response.send_message("✅ Entry updated.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TimezonesCog(bot))
```

-----
## cognitas/cogs/voting.py

```python
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..core import phases, votes as votes_core
from ..core.logs import log_event


# --- Adapter to bridge slash Interaction <-> legacy ctx-style calls ---
class InteractionCtx:
    """
    Minimal context adapter so core functions that expect a 'ctx' with
    .reply(), .send(), .guild, .bot, .channel, .author keep working.

    - First response is handled with interaction.response if not done.
    - After defer (which we do in commands), followups are used automatically.
    - Falls back to channel.send if something goes wrong.
    """
    def __init__(self, interaction: discord.Interaction):
        self._i = interaction
        self.guild: discord.Guild | None = interaction.guild
        self.bot: discord.Client = interaction.client  # type: ignore
        self.channel = interaction.channel
        self.author = interaction.user
        self.message = None  # for compatibility (some code checks existence)

    async def reply(self, content: str = None, **kwargs):
        # Prefer followup if we've already responded or deferred
        try:
            if self._i.response.is_done():
                return await self._i.followup.send(content or "\u200b", **kwargs)
            else:
                return await self._i.response.send_message(content or "\u200b", **kwargs)
        except Exception:
            # Fallback to channel send
            try:
                if self.channel:
                    return await self.channel.send(content or "\u200b", **kwargs)
            except Exception:
                pass

    # Some legacy code may call ctx.send(...)
    async def send(self, content: str = None, **kwargs):
        return await self.reply(content, **kwargs)

    # Some legacy code may call ctx.reply then delete ctx.message; keep no-ops
    async def delete(self, *args, **kwargs):
        return


class VotingAdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -----------------------
    # Phase controls (admin)
    # -----------------------

    @app_commands.command(name="start_day", description="Starts day (admin)")
    @app_commands.describe(duration="Ex: 24h, 90m, 1h30m", channel="Day channel", force="Restart if a day is already active")
    @app_commands.default_permissions(administrator=True)
    async def start_day(self, interaction: discord.Interaction, duration: str = "24h", channel: discord.TextChannel | None = None, force: bool = False):
        # Defer once to avoid InteractionResponded errors
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        await phases.start_day(ctx, duration_str=duration, target_channel=channel, force=force)
        # Optional admin ack
        await interaction.followup.send("✅ Day started", ephemeral=True)

    @app_commands.command(name="end_day", description="Ends day (admin)")
    @app_commands.default_permissions(administrator=True)
    async def end_day(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        await phases.end_day(ctx)
        await interaction.followup.send("☑️ Day finished", ephemeral=True)

    @app_commands.command(name="start_night", description="Starts night (admin)")
    @app_commands.describe(duration="Ex: 12h, 8h, 45m")
    @app_commands.default_permissions(administrator=True)
    async def start_night(self, interaction: discord.Interaction, duration: str = "12h"):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        await phases.start_night(ctx, duration_str=duration)
        await interaction.followup.send("✅ Night started", ephemeral=True)

    @app_commands.command(name="end_night", description="Ends night (admin)")
    @app_commands.default_permissions(administrator=True)
    async def end_night(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        await phases.end_night(ctx)
        await interaction.followup.send("☑️ Night ended", ephemeral=True)

    # -----------------------
    # Status & votes (public)
    # -----------------------

    @app_commands.command(name="votes", description="Vote breakdown (embed)")
    async def votes(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = InteractionCtx(interaction)

        await votes_core.votes_breakdown(ctx)

    @app_commands.command(name="status", description="Day status (embed)")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = InteractionCtx(interaction)

        await votes_core.status(ctx)

    @app_commands.command(name="clearvotes", description="Clean votes(admin)")
    @app_commands.default_permissions(administrator=True)
    async def clearvotes(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        await votes_core.clearvotes(ctx)
        await interaction.followup.send("🧹 Votes cleared.", ephemeral=False)


class VoteCog(commands.GroupCog, name="vote", description="Votes"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="cast", description="Vote for a player")
    async def cast(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=False)
        ctx = InteractionCtx(interaction)

        await votes_core.vote(ctx, member)
        await interaction.followup.send(f"🗳️ Vote cast for {member.mention}.", ephemeral=False)

    @app_commands.command(name="clear", description="Unvote")
    async def clear(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        ctx = InteractionCtx(interaction)

        await votes_core.unvote(ctx)
        await interaction.followup.send("🗑️ Vote cleared.", ephemeral=False)

    @app_commands.command(name="mine", description="See your current vote")
    async def mine(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        await votes_core.myvote(ctx)
        # No extra ack; core should output your current vote.

    @app_commands.command(name="end_day", description="Ask for finish the day early (2/3 of alive players)")
    async def end_day(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ctx = InteractionCtx(interaction)

        await votes_core.request_end_day(ctx)
        await interaction.followup.send("📣 Your request to end day has been registered.")


async def setup(bot: commands.Bot):
    await bot.add_cog(VotingAdminCog(bot))
    await bot.add_cog(VoteCog(bot))  # /vote …

```

-----
## cognitas/status/__init__.py

```python
from __future__ import annotations
from typing import Dict, Type, Optional, Callable, Any

# ---- registry ----
_REGISTRY: Dict[str, "Type[Status]"] = {}

def register(name: str) -> Callable[[Type["Status"]], Type["Status"]]:
    key = name.lower().strip()
    def _wrap(cls: Type["Status"]) -> Type["Status"]:
        _REGISTRY[key] = cls
        return cls
    return _wrap

def get_state_cls(name: str) -> Optional["Type[Status]"]:
    return _REGISTRY.get((name or "").lower().strip())

def list_registered() -> Dict[str, "Type[Status]"]:
    return dict(_REGISTRY)

# ---- exported base ----
class Status:
    """
    Base class for a status effect. Subclasses override what they need.
    """
    name: str = "Status"
    type: str = "debuff"            # debuff|buff|neutral
    visibility: str = "public"      # public|private|hidden
    stack_policy: str = "refresh"   # none|refresh|add|multiple
    default_duration: int = 1       # ticks (phases)
    blocks: Dict[str, bool] = {}    # e.g. {"vote": True, "day_action": True}
    # vote_weight_delta: used by buffs/debuffs that modify voting (Sanctioned/DoubleVote)
    # If set, engine will compute weight from all active statuses
    # Example: +1 for DoubleVote (base 1 -> 2), -0.5 for Sanctioned
    vote_weight_delta: float = 0.0

    # lifecycle hooks
    def on_apply(self, game, uid: str, entry: dict) -> Optional[str]: return None
    def on_tick(self, game, uid: str, entry: dict, phase: str) -> Optional[str]: return None
    def on_expire(self, game, uid: str, entry: dict) -> Optional[str]: return None

    # action hook (optional redirection etc.)
    # return dict(action_allowed: bool, reason: Optional[str], redirect_to: Optional[str])
    def on_action(self, game, uid: str, entry: dict, action_kind: str, target_uid: Optional[str]) -> dict:
        return {"action_allowed": True, "reason": None, "redirect_to": None}
```

-----
## cognitas/status/builtin.py

```python
from __future__ import annotations
from . import Status, register
from .engine import pick_random_alive

# ---------- Paralyzed ----------
@register("Paralyzed")
class Paralyzed(Status):
    name = "Paralyzed"; type = "debuff"; visibility = "private"
    stack_policy = "refresh"; default_duration = 2
    # blocks day ability; your /act can pass action_kind="day_action"
    blocks = {"day_action": True}

    def on_apply(self, game, uid, entry): return f"<@{uid}> You've been Paralyzed!"
    def on_expire(self, game, uid, entry): return f"<@{uid}> You recovered from paralysis."

# ---------- Drowsiness ----------
@register("Drowsiness")
class Drowsiness(Status):
    name = "Drowsiness"; type = "debuff"; visibility = "private"
    stack_policy = "refresh"; default_duration = 2
    blocks = {"night_action": True}

    def on_apply(self, game, uid, entry): return f"<@{uid}> You've been affected by Drowsiness!"
    def on_expire(self, game, uid, entry): return f"<@{uid}> You recovered from drowsiness."

# ---------- Confusion ----------
@register("Confusion")
class Confusion(Status):
    name = "Confusion"; type = "debuff"; visibility = "private"
    stack_policy = "refresh"; default_duration = 2

    def on_apply(self, game, uid, entry): return f"<@{uid}> You've been Confused!"
    def on_expire(self, game, uid, entry): return f"<@{uid}> You recovered from confusion."

    def on_action(self, game, uid, entry, action_kind, target_uid):
        # Only affects abilities; not voting
        if action_kind not in ("day_action", "night_action"):
            return {"action_allowed": True, "reason": None, "redirect_to": None}
        # coin toss: True=heads (ok), False=tails (redirect)
        import random
        if random.random() < 0.5:
            # tails -> redirect to random alive (not self)
            new_tgt = pick_random_alive(game, exclude=uid)
            if new_tgt:
                return {"action_allowed": True, "reason": None, "redirect_to": new_tgt}
        # heads -> proceed as chosen
        return {"action_allowed": True, "reason": None, "redirect_to": None}

# ---------- Jailed ----------
@register("Jailed")
class Jailed(Status):
    name = "Jailed"; type = "debuff"; visibility = "private"
    stack_policy = "refresh"; default_duration = 1
    blocks = {"day_action": True, "night_action": True}

    def on_apply(self, game, uid, entry): return f"<@{uid}> You've been Jailed!"
    def on_expire(self, game, uid, entry): return f"<@{uid}> You're free again!"

# ---------- Silenced ----------
@register("Silenced")
class Silenced(Status):
    name = "Silenced"; type = "debuff"; visibility = "private"
    stack_policy = "refresh"; default_duration = 2
    # talking in day channel is policy-enforced in your cog; we flag a block here:
    blocks = {"day_talk": True}

    def on_apply(self, game, uid, entry): return f"<@{uid}> You've been Silenced!"
    def on_expire(self, game, uid, entry): return f"<@{uid}> You can speak again."

# ---------- Double vote (stacking adds weight) ----------
@register("Double vote")
class DoubleVote(Status):
    name = "Double vote"; type = "buff"; visibility = "private"
    stack_policy = "add"; default_duration = 2
    vote_weight_delta = +1.0  # base 1 -> 2; stacking adds more

    def on_apply(self, game, uid, entry): return f"<@{uid}> You've been blessed with double vote!"
    def on_expire(self, game, uid, entry): return f"<@{uid}> Your double vote expired."

# ---------- Sanctioned (stacking halves, then blocks) ----------
@register("Sanctioned")
class Sanctioned(Status):
    name = "Sanctioned"; type = "deb uff"; visibility = "private"
    stack_policy = "add"; default_duration = 2
    vote_weight_delta = -0.5  # first time halves (1.0 -> 0.5). two stacks -> 0.0 (blocked by votes layer)

    def on_apply(self, game, uid, entry):
        stacks = entry.get("stacks", 1)
        if stacks >= 2:
            return f"<@{uid}> Your Sanction got worse, you can't vote!"
        return f"<@{uid}> You're Sanctioned, your vote counts as half!"

    def on_expire(self, game, uid, entry): return f"<@{uid}> Your Sanction was removed."

# ---------- Wounded ----------
@register("Wounded")
class Wounded(Status):
    name = "Wounded"; type = "debuff"; visibility = "private"
    stack_policy = "add"; default_duration = 2
    # Policy from spec:
    #  - one stack: can't vote
    #  - two stacks: die immediately
    #  - if not healed by next day start: die
    blocks = {"vote": True}  # at least one stack blocks voting

    def on_apply(self, game, uid, entry):
        stacks = entry.get("stacks", 1)
        if stacks >= 2:
            _kill_player(game, uid, reason="Wounded x2")
            return f"<@{uid}> Your Wound got worse, you died!"
        return f"<@{uid}> You're Wounded, you can't vote. Find a healer."

    def on_tick(self, game, uid, entry, phase):
        # If this tick is day-start and still wounded -> die
        if phase == "day" and entry.get("remaining", 1) <= 1:
            _kill_player(game, uid, reason="Wounded (not healed by dawn)")
            return f"<@{uid}> succumbed to their wounds."
        return None

    def on_expire(self, game, uid, entry): return f"<@{uid}> You're healthy again!"

# ---------- Poisoned ----------
@register("Poisoned")
class Poisoned(Status):
    name = "Poisoned"; type = "debuff"; visibility = "private"
    stack_policy = "add"; default_duration = 1

    def on_apply(self, game, uid, entry):
        stacks = entry.get("stacks", 1)
        if stacks >= 2:
            _kill_player(game, uid, reason="Poisoned x2")
            return f"<@{uid}> You died by poison. RIP."
        return f"<@{uid}> You're Poisoned. Find a healer."

    def on_tick(self, game, uid, entry, phase):
        # end of day (after one tick) -> die if still poisoned
        if phase == "day" and entry.get("remaining", 1) <= 1:
            _kill_player(game, uid, reason="Poisoned (not healed by end of day)")
            return f"<@{uid}> You died by poison. RIP."
        return None

    def on_expire(self, game, uid, entry): return f"<@{uid}> You're healthy again!"

# ---- helpers ----
def _kill_player(game, uid: str, *, reason: str):
    p = game.players.get(uid, {})
    p["alive"] = False
    p["death_reason"] = reason
```

-----
## cognitas/status/engine.py

```python
from __future__ import annotations
import random
from typing import Optional, Dict, Any, List, Tuple
from . import get_state_cls, list_registered, Status

# game.status_map structure:
# { uid: { state_name: {"remaining": int, "stacks": int, "source": str|"system"|"GM",
#                       "meta": {...}, "visibility": "public|private|hidden"} } }

def _ensure_maps(game):
    if not hasattr(game, "status_map") or not isinstance(game.status_map, dict):
        game.status_map = {}
    if not hasattr(game, "status_log") or not isinstance(game.status_log, list):
        game.status_log = []

def list_active(game, uid: str) -> Dict[str, dict]:
    _ensure_maps(game)
    return game.status_map.get(uid, {}).copy()

def has(game, uid: str, name: str) -> bool:
    return name.lower().strip() in (game.status_map.get(uid, {}) if hasattr(game, "status_map") else {})

def apply(game, uid: str, name: str, *, source: Optional[str] = "GM",
          duration: Optional[int] = None, meta: Optional[dict] = None) -> Tuple[bool, Optional[str]]:
    """
    Returns (applied: bool, banner_text: Optional[str for DM/public depending on visibility])
    """
    _ensure_maps(game)
    cls = get_state_cls(name)
    if not cls:
        return False, None
    state = cls()
    dur = int(duration if duration is not None else state.default_duration)
    if dur <= 0:
        dur = 1

    per_user = game.status_map.setdefault(uid, {})
    key = state.name.lower()

    # stacking policy (global default: refresh)
    if key in per_user:
        entry = per_user[key]
        if state.stack_policy == "refresh":
            entry["remaining"] = dur
            entry["stacks"] = 1
        elif state.stack_policy == "add":
            entry["remaining"] += dur
        elif state.stack_policy == "multiple":
            entry["stacks"] += 1
            entry["remaining"] = max(entry["remaining"], dur)
        else:  # none -> ignore
            pass
    else:
        per_user[key] = entry = {
            "remaining": dur,
            "stacks": 1,
            "source": source or "GM",
            "meta": meta or {},
            "visibility": getattr(state, "visibility", "public"),
            "type": getattr(state, "type", "debuff"),
        }

    banner = state.on_apply(game, uid, per_user[key]) or None
    _audit(game, f"APPLY {state.name} to {uid} (dur={per_user[key]['remaining']}, stacks={per_user[key]['stacks']})")
    return True, banner

def heal(game, uid: str, name: Optional[str] = None, *, all_: bool = False) -> List[str]:
    """
    Removes status(es). Returns list of banners to announce (expire messages).
    If all_=True remove all; otherwise remove only given name.
    """
    _ensure_maps(game)
    banners: List[str] = []
    if uid not in game.status_map:
        return banners
    if all_:
        to_remove = list(game.status_map[uid].keys())
    else:
        if not name:
            return banners
        to_remove = [name.lower().strip()]
    for key in to_remove:
        entry = game.status_map[uid].get(key)
        if not entry:
            continue
        st_cls = get_state_cls(key)
        st = st_cls() if st_cls else None
        if st:
            b = st.on_expire(game, uid, entry)
            if b:
                banners.append(b)
        del game.status_map[uid][key]
        _audit(game, f"HEAL {key} from {uid}")
    if not game.status_map[uid]:
        del game.status_map[uid]
    return banners

def tick(game, phase: str) -> List[Tuple[str, str]]:
    """
    Decrement remaining and resolve per-phase. Returns list of (uid, banner_text) to announce.
    Phase values: "day" or "night".
    """
    _ensure_maps(game)
    banners: List[Tuple[str, str]] = []
    # collect expirations & on_tick banners
    expirations: List[Tuple[str, str]] = []
    for uid, effects in list(game.status_map.items()):
        for key, entry in list(effects.items()):
            st_cls = get_state_cls(key)
            state = st_cls() if st_cls else None
            # Resolution timing: fire on_tick first
            if state:
                tb = state.on_tick(game, uid, entry, phase)
                if tb:
                    banners.append((uid, tb))
            # decrement
            entry["remaining"] = max(0, int(entry.get("remaining", 0)) - 1)
            if entry["remaining"] == 0:
                # expire
                eb = state.on_expire(game, uid, entry) if state else None
                if eb:
                    expirations.append((uid, eb))
                del effects[key]
                _audit(game, f"EXPIRE {key} on {uid}")
        if not effects:
            del game.status_map[uid]
    banners.extend(expirations)
    return banners

def check_action(game, uid: str, action_kind: str, target_uid: Optional[str] = None) -> dict:
    """
    Returns {"allowed": bool, "reason": Optional[str], "redirect_to": Optional[str]}
    Combines all active statuses; any block wins.
    """
    _ensure_maps(game)
    entry_map = game.status_map.get(uid, {})
    # init result
    res = {"allowed": True, "reason": None, "redirect_to": None}
    # blocks & on_action
    for key, entry in entry_map.items():
        st_cls = get_state_cls(key)
        state = st_cls() if st_cls else None
        if not state:
            continue
        # static blocks by action_kind
        if state.blocks.get(action_kind, False):
            res["allowed"] = False
            res["reason"] = f"blocked_by:{state.name}"
            return res
        # dynamic hook (confusion may redirect)
        hook = state.on_action(game, uid, entry, action_kind, target_uid)
        if not hook.get("action_allowed", True):
            res["allowed"] = False
            res["reason"] = hook.get("reason")
            return res
        if hook.get("redirect_to"):
            res["redirect_to"] = hook["redirect_to"]
    return res

def compute_vote_weight(game, uid: str, base: float = 1.0) -> float:
    """
    Adds up vote deltas from active statuses (e.g., +1 for DoubleVote, -0.5 per Sanction).
    Clamp at 0..max reasonable (e.g., 4).
    """
    _ensure_maps(game)
    weight = base
    for key, entry in game.status_map.get(uid, {}).items():
        st_cls = get_state_cls(key)
        st = st_cls() if st_cls else None
        if not st:
            continue
        # stacking: apply per stack
        delta = getattr(st, "vote_weight_delta", 0.0) * max(1, int(entry.get("stacks", 1)))
        weight += delta
    if weight < 0: weight = 0.0
    if weight > 4: weight = 4.0
    return weight

def _audit(game, text: str):
    log = getattr(game, "status_log", None)
    if isinstance(log, list):
        log.append(text)
        if len(log) > 200:
            del log[:len(log)-200]

# utility for Confusion
def pick_random_alive(game, *, exclude: Optional[str] = None) -> Optional[str]:
    players = [uid for uid, info in getattr(game, "players", {}).items()
               if info.get("alive", True)]
    if exclude and exclude in players:
        players.remove(exclude)
    return random.choice(players) if players else None
```
