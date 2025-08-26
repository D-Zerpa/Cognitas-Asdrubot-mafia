import random
from discord import app_commands
from discord.ext import commands

class FunCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="dice", description="Tirar un dado")
    async def dice(self, interaction, faces: int = 20):
        faces = max(2, min(1000, faces))
        await interaction.response.send_message(f"🎲 {random.randint(1, faces)} (1–{faces})")

    @app_commands.command(name="coin", description="Tirar una moneda")
    async def coin(self, interaction):
        await interaction.response.send_message("🪙 Cara" if random.random() < 0.5 else "🪙 Cruz")

async def setup(bot): await bot.add_cog(FunCog(bot))

