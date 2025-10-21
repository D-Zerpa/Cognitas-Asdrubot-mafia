from __future__ import annotations
import os
from pathlib import Path

# -------------------------------------------------------------------
# Intents configuration (adjust as needed)
# -------------------------------------------------------------------
INTENTS_KWARGS = {
    "guilds": True,
    "members": True,
    "message_content": True,
}

# -------------------------------------------------------------------
# State file location
# -------------------------------------------------------------------

# Base directory = repository root (where bot.py, README, etc. live)
BASE_DIR = Path(__file__).resolve().parents[1]  # ascend from cognitas/ to root
# Absolute path to state.json at root
STATE_PATH = Path(os.getenv("STATE_PATH", str(BASE_DIR / "state.json")))
DEFAULT_PROFILE = os.getenv("ASDRUBOT_DEFAULT_PROFILE", "default")

# Reminder mentions
MENTION_EVERYONE = True          # set False to disable @everyone
MENTION_ROLE_ID = None           # set an int role id to ping that role instead
REMINDER_CHECKPOINTS = ["half", 4*3600, 15*60, 5*60]
START_AT_DAY = 1
