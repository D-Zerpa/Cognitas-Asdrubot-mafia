# cognitas/bot.py
import os
import logging
import discord
from discord.ext import commands
from cognitas.core import phases
from cognitas.core.storage import load_state

# .env opcional
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ---- Config desde cognitas/config.py (si existe) ----
CONFIG_INTENTS = None
CONFIG_PREFIX = None
try:
    from . import config as cfg  # importa el módulo, no símbolos sueltos
    CONFIG_INTENTS = getattr(cfg, "INTENTS", None)
    CONFIG_PREFIX = getattr(cfg, "PREFIX", None)
except Exception:
    # Si no existe config.py o faltan símbolos, usamos defaults más abajo
    pass

# ---- Logging ----
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("cognitas.bot")

# ---- Intents ----
intents = CONFIG_INTENTS or discord.Intents.default()
# Para comandos de prefijo no hacen falta con slash, pero no molestan:
intents.message_content = True
intents.members = True

# ---- Token / Guild ----
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")  # opcional: registra slash como guild-commands, aparecen al instante

# Aunque ya migramos a slash, mantenemos un prefijo por compatibilidad si quisieras usar alguno
PREFIX = CONFIG_PREFIX or os.getenv("DISCORD_PREFIX", "!")

# ---- Bot (árbol de slash vive en bot.tree) ----
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

INITIAL_EXTENSIONS = [
    "cognitas.cogs.players",
    "cognitas.cogs.voting",
    "cognitas.cogs.moderation",
    "cognitas.cogs.game",
    "cognitas.cogs.actions",
    "cognitas.cogs.help",
    "cognitas.cogs.fun",
]

@bot.event
async def setup_hook():
    # Cargar Cogs
    for ext in INITIAL_EXTENSIONS:
        try:
            await bot.load_extension(ext)
            log.info("Loaded extension: %s", ext)
        except Exception as e:
            log.exception("Failed loading %s: %s", ext, e)

    # Sincronizar slash
    try:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            log.info("Slash synced to guild %s (%d cmds).", GUILD_ID, len(synced))
        else:
            synced = await bot.tree.sync()
            log.info("Global slash synced (%d cmds).", len(synced))
    except Exception as e:
        log.exception("Slash sync failed: %s", e)

    # Load persisted game state (including .bak fallback) BEFORE rehydrating timers
    try:
        load_state("state.json")
        log.info("State loaded from state.json (or .bak).")
    except Exception as e:
        log.exception("Failed to load state: %s", e)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (id={bot.user.id})")
    # Rehydrate timers per guild
    for guild in bot.guilds:
        try:
            await phases.rehydrate_timers(bot, guild)
        except Exception as e:
            print(f"[rehydrate_timers] Error for guild {guild.id}: {e}")

def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN missing. Put it in your environment or .env at repo root.")
    bot.run(TOKEN)

if __name__ == "__main__":
    main()

