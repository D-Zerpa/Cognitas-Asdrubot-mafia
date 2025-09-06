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
        await interaction.response.send_message("🪙 Cara" if random.random() < 0.5 else "🪙 Cruz")
        
    @app_commands.command(name="lynch", description="Generate a lynch poster using the target's avatar.")
    @app_commands.describe(target="Target player to feature on the poster")
    async def lynch_cmd(self, interaction: discord.Interaction, target: discord.Member):
        await interaction.response.defer()
        f = await johnbotjovi.linchar(target)
        if f is None:
            return await interaction.followup.send(
                f"LYNCH! {target.mention} — (Pillow not available or no backgrounds found)"
            )
        await interaction.followup.send(f"LYNCH! {target.mention}", file=f)
        
async def setup(bot): await bot.add_cog(FunCog(bot))

