from discord import app_commands
from discord.ext import commands

HELP_TEXT = """
**Player**: /player list, /player register, /player unregister, /player rename, /player alias show|add|del
**Fases/Votos**: /start_day, /end_day, /start_night, /end_night, /vote cast|clear|mine, /votos, /status, /clearvotes, /vote end_day
**Partida**: /game_start, /game_reset, /finish_game, /who, /assign
**Moderación**: /bc, /set_day_channel, /set_admin_channel, /show_channels, /purge
**Diversión**: /dice, /coin
""".strip()

class HelpCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="help", description="Listado de comandos")
    async def help(self, interaction):
        await interaction.response.send_message(HELP_TEXT, ephemeral=True)

async def setup(bot): await bot.add_cog(HelpCog(bot))
