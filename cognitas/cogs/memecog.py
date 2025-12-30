import discord
from discord.ext import commands
import random
from discord import app_commands
from ..core.state import game 

class MemesCog(commands.Cog, name="Memes"):
    def __init__(self, bot):
        self.bot = bot
        
        # Kill switch, just in case.
        self.is_enabled = True

        # Memes GLOBALES (Funcionan en cualquier expansión)
        self.global_memes = {
            "asdrubot": "👀 Estoy observando...",
            "gracias, asdru": "Bzbzbz.",
            "los jueves": "Hasta los Domingos."
        }

    @app_commands.command(name="toggle_memes", description="Activar/Desactivar Easter Eggs")
    @app_commands.describe(state="True para activar, False para desactivar")
    @app_commands.default_permissions(administrator=True)
    async def toggle_memes(self, interaction: discord.Interaction, state: bool):
        self.is_enabled = state
        
        status_text = "✅ **ACTIVADOS**" if state else "zzz **DESACTIVADOS**"
        await interaction.response.send_message(
            f"Los Easter Eggs han sido {status_text}.",
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.content.startswith(("/", "!")):
            return

        content = message.content.lower()

        # 1. Load expansion memes.
        active_memes = self.global_memes.copy()
        
        expansion = getattr(game, "expansion", None)
        if expansion and hasattr(expansion, "memes"):
            # Add the expansion memes to the list.
            active_memes.update(expansion.memes)

        # 2. Look for coincidences.
        for trigger, response in active_memes.items():
            if trigger in content:
                if isinstance(response, list):
                    reply_text = random.choice(response)
                else:
                    reply_text = response
                
                try:
                    # Usamos reply=False para ser menos intrusivos, o True si prefieres
                    await message.channel.send(reply_text, reply= True)
                except Exception:
                    pass
                
                return

async def setup(bot: commands.Bot):
    await bot.add_cog(MemesCog(bot))