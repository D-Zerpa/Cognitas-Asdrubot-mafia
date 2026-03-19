import random
import discord
from discord import app_commands
from discord.ext import commands
from ..core import johnbotjovi

class FunCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="dice", description="Lanzar un dado")
    async def dice(self, interaction, faces: int = 20):
        faces = max(2, min(1000, faces))
        res = random.randint(1, faces)
        await interaction.response.send_message(f"🎲 **{res}** (1–{faces})")

    @app_commands.command(name="coin", description="Lanzar una moneda")
    async def coin(self, interaction):
        res = "Cara" if random.random() < 0.5 else "Cruz"
        await interaction.response.send_message(f"🪙 **{res}**")
        
    @app_commands.command(name="lynch", description="Generar un póster de linchamiento (meme).")
    @app_commands.describe(target="Jugador que aparecerá en el póster")
    async def lynch_cmd(self, interaction: discord.Interaction, target: discord.Member):
        await interaction.response.defer()
        f = await johnbotjovi.lynch(target)
        if f is None:
            return await interaction.followup.send(
                f"¡LINCHADO! {target.mention} — (No se pudo generar la imagen)."
            )
        await interaction.followup.send(f"🪓 **¡LINCHADO!** {target.mention}", file=f)
        
async def setup(bot): await bot.add_cog(FunCog(bot))

