# cognitas/bot.py
from __future__ import annotations

import os
import sys
import logging
import discord
from discord.ext import commands

from cognitas.core.storage import load_state
from cognitas.core import phases
from cognitas.config import INTENTS_KWARGS
from dotenv import load_dotenv

load_dotenv()  

# -------------------------------------------------
# Logging
# -------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("asdrubot")

# -------------------------------------------------
# Discord intents from config
# -------------------------------------------------
def _make_intents() -> discord.Intents:
    intents = discord.Intents.default()
    # Safely apply toggles from config
    for k, v in (INTENTS_KWARGS or {}).items():
        if hasattr(intents, k):
            setattr(intents, k, bool(v))
    # Always enable guilds (required for slash commands & rehydrate)
    intents.guilds = True
    return intents

# List of cog modules to load
COG_MODULES = [
    "cognitas.cogs.game",
    "cognitas.cogs.moderation",
    "cognitas.cogs.voting",
    "cognitas.cogs.players",
    "cognitas.cogs.actions",
    "cognitas.cogs.role_debug",
    "cognitas.cogs.fun",
    "cognitas.cogs.help",
]

class AsdruBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=_make_intents())
        self._state_loaded = False

    async def setup_hook(self):
        # 1) Load persistent state
        try:
            load_state()  # your storage.load_state is synchronous
            self._state_loaded = True
            log.info("[startup] State loaded.")
        except Exception:
            log.exception("[startup] Failed to load state")

        # 2) Load cogs (all commands live there)
        for mod in COG_MODULES:
            try:
                await self.load_extension(mod)
                log.info(f"[cogs] Loaded: {mod}")
            except Exception:
                log.exception(f"[cogs] Failed to load: {mod}")

        # 3) Sync slash commands (global)
        try:
            await self.tree.sync()
            log.info("[startup] Slash commands synced.")
        except Exception:
            log.exception("[startup] Failed to sync slash commands")

    async def on_ready(self):
        try:
            user = self.user
            log.info(f"Logged in as {user} (id={user.id})")  # type: ignore
        except Exception:
            log.info("Logged in.")

        # Rehydrate timers for all connected guilds (or a stored one if usas state.guild_id)
        try:
            if getattr(phases, "rehydrate_timers", None):
                for guild in self.guilds:
                    try:
                        await phases.rehydrate_timers(self, guild)
                    except Exception as e:
                        log.warning(f"[rehydrate] Error for guild {getattr(guild,'id','?')}: {e}")
                log.info("[rehydrate] Timers rehydration attempted for all guilds.")
        except Exception:
            log.exception("[rehydrate] Unexpected failure")

def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError(
            "DISCORD_TOKEN (or ASDRUBOT_TOKEN) missing. "
            "Set it in your environment or a .env at repo root."
        )

    bot = AsdruBot()
    bot.run(token)

if __name__ == "__main__":
    main()

