import logging
import abc
from enum import Enum
from typing import Optional
from .state import GameState

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
    def process_phase_change(self, state: GameState) -> Optional[str]:
        """
        Triggered precisely after the phase or cycle has advanced.
        Should return an announcement string (e.g., "🌕 Luna Llena") if needed,
        or None if the expansion stays silent this phase.
        """
        pass

class TimeManager:
    """
    Handles the raw flow of time. Completely decoupled from specific expansions.
    """
    def __init__(self, state: GameState, gimmick: Optional[ExpansionGimmick] = None):
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
            return self.gimmick.process_phase_change(self.state)
            
        return None