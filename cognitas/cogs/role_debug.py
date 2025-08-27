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
        # Muestra las primeras N para no romper el límite
        sample = keys[:80]
        text = "Loaded roles (keys):\n" + ", ".join(sample) + (", ..." if len(keys) > 80 else "")
        await interaction.response.send_message(text[:1900], ephemeral=True)

async def setup(bot): await bot.add_cog(DebugRoles(bot))
