from __future__ import annotations
import os
from pathlib import Path

# -------------------------------------------------------------------
# Intents config (ajústalo como lo tenías)
# -------------------------------------------------------------------
INTENTS_KWARGS = {
    "guilds": True,
    "members": True,
    "message_content": True,
}

# -------------------------------------------------------------------
# State file location
# -------------------------------------------------------------------

# Base dir = raíz del repo (donde está bot.py, README, etc.)
BASE_DIR = Path(__file__).resolve().parents[1]  # sube de cognitas/ a raíz
# Path absoluto al state.json en raíz
STATE_PATH = Path(os.getenv("STATE_PATH", str(BASE_DIR / "state.json")))

# Reminder mentions
MENTION_EVERYONE = True          # set False to disable @everyone
MENTION_ROLE_ID = None           # set an int role id to ping that role instead
REMINDER_CHECKPOINTS = ["half", 4*3600, 15*60, 5*60]
START_AT_DAY = 1