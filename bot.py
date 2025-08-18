import os, asyncio
from dotenv import load_dotenv
import discord
from discord.ext import commands

from cognitas.config import INTENTS_KWARGS
from cognitas.core.state import game
from cognitas.core.roles import load_roles
from cognitas.core.storage import load_state, save_state
from cognitas.core.timer import resume_day_timer

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in .env")

intents = discord.Intents.default()
for k, v in INTENTS_KWARGS.items():
    setattr(intents, k, v)

bot = commands.Bot(command_prefix="!", intents=intents)

# Load roles & state before cogs
game.roles = load_roles("roles.json")
load_state("players.json")

# Load cogs
async def setup_cogs():
    await bot.add_cog(__import__("concilio.cogs.admin", fromlist=["AdminCog"]).AdminCog(bot))
    await bot.add_cog(__import__("concilio.cogs.voting", fromlist=["VotingCog"]).VotingCog(bot))

@bot.event
async def on_ready():
    print(f"Connected as {bot.user} (id: {bot.user.id})")
    print(f"Loaded roles: {len(game.roles)}")
    # Resume an active Day timer (if any)
    await resume_day_timer(bot)

@bot.command()
async def ping(ctx):
    await ctx.reply("pong 🏓")

@bot.command()
@commands.is_owner()
async def shutdown(ctx):
    await ctx.send("👋 Shutting down…")
    save_state("players.json")
    await bot.close()

async def main():
    async with bot:
        await setup_cogs()
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())