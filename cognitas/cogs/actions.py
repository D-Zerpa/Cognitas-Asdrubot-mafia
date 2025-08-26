import discord
from discord import app_commands
from discord.ext import commands
from ..core.state import game
from ..core.storage import save_state
from ..core.logs import log_event

class ActionsCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="act", description="Registrar acción nocturna")
    async def act(self, interaction: discord.Interaction, target: discord.Member | None = None, note: str = ""):
        if not getattr(game, "night_deadline_epoch", None):
            return await interaction.response.send_message("It is not **Night** phase.", ephemeral=True)

        actor_uid = str(interaction.user.id)
        target_uid = str(target.id) if target else None
        if actor_uid not in game.players or not game.players[actor_uid].get("alive", True):
            return await interaction.response.send_message("You are not registered or you are not alive.", ephemeral=True)
        if target_uid:
            if target_uid not in game.players: return await interaction.response.send_message("Target is not registered.", ephemeral=True)
            if not game.players[target_uid].get("alive", True): return await interaction.response.send_message("Target is not alive.", ephemeral=True)

        game.night_actions = getattr(game, "night_actions", [])
        game.night_actions.append({"actor": actor_uid, "target": target_uid, "note": note.strip(), "day": int(getattr(game, "current_day_number", 1))})
        save_state("state.json")
        await interaction.response.send_message("✅ Acción registrada.", ephemeral=True)
        try:
            await log_event(self.bot, interaction.guild.id, "NIGHT_ACTION", actor_id=actor_uid, target_id=(target_uid or "None"), note=(note or ""))
        except Exception:
            pass

async def setup(bot): await bot.add_cog(ActionsCog(bot))
