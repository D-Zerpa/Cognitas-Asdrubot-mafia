# cognitas/core/jonbotjovi.py
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
      linchar02-960-240-.png
      whatever-960-240.png
      bg-120-300-extra.jpg
    We split on '-' and only accept tokens that are pure digits,
    so 'linchar02' is ignored but '960' and '240' are taken.
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

async def linchar(member: discord.Member) -> Optional[discord.File]:
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

