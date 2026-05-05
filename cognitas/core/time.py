import logging
import abc
from enum import Enum
from typing import TYPE_CHECKING, Optional, Any
import time
import discord
from discord.ext import commands


if TYPE_CHECKING:
    from cognitas.core.state import GameState

logger = logging.getLogger("cognitas.time")

class Phase(str, Enum):
    """Strict definitions for game phases."""
    SETUP = "setup"
    DAY = "day"
    NIGHT = "night"

class ExpansionGimmick(abc.ABC):
    """
    Abstract base class for all expansion-specific daily events.
    """
    @abc.abstractmethod
    def process_phase_change(self, state: "GameState") -> Optional[str]:
        """
        Triggered precisely after the phase or cycle has advanced.
        Should return an announcement string (e.g., "🌕 Luna Llena") if needed,
        or None if the expansion stays silent this phase.
        """
        pass

class PhaseState(abc.ABC):
    """Abstract base class representing the logical rules of a specific phase."""
    can_speak: bool = False

    def __init__(self, state: "GameState"):
        self.state = state

    def evaluate_lynch(self, voting_manager) -> dict:
        return {"resolved": False}

    def evaluate_end_day(self, voting_manager) -> dict:
        return {"resolved": False}

    async def on_end(self, bot: commands.Bot, guild: discord.Guild):
        """Handles end of phase condition processing and cleanup."""
        # Safe inner imports to prevent circular dependencies
        from cognitas.conditions.engine import ConditionManager
        from cognitas.utils.discord_sync import process_player_death

        # 1. Process conditions
        cond_manager = ConditionManager(self.state)
        cond_manager.process_phase_end()

        # 2. Process deaths safely
        alive_role_id = self.state.discord_setup.get("alive_role_id")
        for player in self.state.players.values():
            if not player.is_alive:
                member = guild.get_member(player.user_id)
                if member and alive_role_id and any(r.id == alive_role_id for r in member.roles):
                    await process_player_death(bot, guild, player, reason="Efectos al final de la fase")

        # 3. Stop timer
        self.state.discord_setup["phase_end_time"] = None

        # 4. Clear generic queues
        if hasattr(bot, "action_manager"):
            bot.action_manager.clear_queue(self.state)

    async def on_start(self, bot: commands.Bot, guild: discord.Guild, duration: int = 0):
        """Handles channel renaming, opening, and starting the clock."""
        if duration > 0:
            self.state.discord_setup["phase_end_time"] = int(time.time()) + (duration * 60)
        else:
            self.state.discord_setup["phase_end_time"] = None

        game_channel_id = self.state.discord_setup.get("game_channel_id")
        if game_channel_id:
            game_channel = guild.get_channel(game_channel_id)
            if game_channel:
                alive_role_id = self.state.discord_setup.get("alive_role_id")
                target_role = guild.get_role(alive_role_id) if alive_role_id else guild.default_role
                
                await game_channel.set_permissions(target_role, send_messages=self.can_speak)

                fase_url_name = "día" if self.state.phase == Phase.DAY else "noche"
                new_channel_name = f"{fase_url_name}-{self.state.cycle}"
                try:
                    if game_channel.name != new_channel_name:
                        await game_channel.edit(name=new_channel_name, reason="Phase transition rename")
                        logger.info(f"Game channel renamed to {new_channel_name}")
                except discord.RateLimited:
                    logger.warning("Rate limit hit while trying to rename the game channel.")
                except discord.Forbidden:
                    logger.error("Missing permissions to rename the game channel.")

    async def lock_channel(self, guild: discord.Guild):
        """Stops the clock and locks the channel immediately."""
        self.state.discord_setup["phase_end_time"] = None
        game_channel_id = self.state.discord_setup.get("game_channel_id")
        if game_channel_id:
            game_channel = guild.get_channel(game_channel_id)
            if game_channel:
                alive_role_id = self.state.discord_setup.get("alive_role_id")
                target_role = guild.get_role(alive_role_id) if alive_role_id else guild.default_role
                await game_channel.set_permissions(target_role, send_messages=False)


class DayPhaseState(PhaseState):
    """Specific rules and evaluations for the Day phase."""
    can_speak: bool = True

    def evaluate_lynch(self, voting_manager) -> dict:
        alive_players = self.state.get_alive_players()
        vote_modifiers = {}
        for p in alive_players:
            if p.role:
                try:
                    extra = float(p.role.flags.get("lynch_weight", 0))
                    if extra != 0:
                        vote_modifiers[p.user_id] = extra
                except (ValueError, TypeError):
                    pass

        majority_target = voting_manager.check_majority(self.state, len(alive_players), extra_thresholds=vote_modifiers)
        if majority_target:
            return {"resolved": True, "target": majority_target}
        return {"resolved": False}

    def evaluate_end_day(self, voting_manager) -> dict:
        if voting_manager.check_end_day_majority(self.state, len(self.state.get_alive_players())):
            return {"resolved": True}
        return {"resolved": False}

    async def on_end(self, bot: commands.Bot, guild: discord.Guild):
        await super().on_end(bot, guild)
        # Day specific cleanup
        if hasattr(bot, "voting_manager"):
            bot.voting_manager.clear_all_votes(self.state)

class TimeManager:
    """
    Handles the raw flow of time. Completely decoupled from specific expansions.
    """
    def __init__(self, state: "GameState", gimmick: Optional[ExpansionGimmick] = None):
        self.state = state
        self.gimmick = gimmick  # The injected expansion logic

    def advance_phase(self) -> Optional[str]:
        """
        Transitions the game to the next logical phase.
        Returns the expansion's announcement string, if any exists.
        """
        if self.state.phase == Phase.SETUP:
            self.state.phase = Phase.DAY
            self.state.cycle = 1
            logger.info("Game started. Moved to Day 1.")
            
        elif self.state.phase == Phase.DAY:
            self.state.phase = Phase.NIGHT
            logger.info(f"Transitioned to Night {self.state.cycle}.")
            
        elif self.state.phase == Phase.NIGHT:
            self.state.phase = Phase.DAY
            self.state.cycle += 1
            logger.info(f"Transitioned to Day {self.state.cycle}.")

        # Execute the specific expansion event/gimmick, if one is active
        if self.gimmick:
            return self.gimmick.on_phase_change(self.state)
            
        return None

    def get_current_phase_machine(self) -> PhaseState:
        """Dynamically generates the state machine for the current phase."""
        if self.state.phase == Phase.DAY:
            return DayPhaseState(self.state)
        # Fallback for Night or Setup (will use base dummy methods)
        return PhaseState(self.state)