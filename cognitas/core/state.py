import json
import os
import logging
from typing import Dict, Any, Optional, List
from .models import Player

logger = logging.getLogger("cognitas.state")

class GameState:
    """
    Central manager for the match state. 
    Handles player data, current phase/cycle, and file persistence.
    """
    def __init__(self):
        # We use a Dictionary for O(1) lookups. Key: user_id (int), Value: Player object
        self.players: Dict[int, Player] = {}
        self.phase: str = "setup"  # e.g., 'setup', 'day', 'night'
        self.cycle: int = 0        # Represents day/night count

        self.discord_setup: Dict[str, Optional[int]] = {
            "game_channel_id": None,
            "log_channel_id": None,
            "graveyard_channel_id": None,
            "alive_role_id": None,
            "dead_role_id": None
        }

    def add_player(self, player: Player) -> None:
        """Registers a player into the game state."""
        self.players[player.user_id] = player

    def get_player(self, user_id: int) -> Optional[Player]:
        """O(1) retrieval of a player by their Discord ID."""
        return self.players.get(user_id)

    def get_alive_players(self) -> List[Player]:
        """Returns a list of players currently marked as alive."""
        return [p for p in self.players.values() if p.is_alive]

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the full game state."""
        return {
            "phase": self.phase,
            "cycle": self.cycle,
            "discord_setup": self.discord_setup,
            "players": [p.to_dict() for p in self.players.values()]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GameState':
        """Rebuilds the state from a dictionary."""
        state = cls()
        state.phase = data.get("phase", "setup")
        state.cycle = data.get("cycle", 0)
        saved_setup = data.get("discord_setup", {})
        state.discord_setup.update(saved_setup)
        
        for p_data in data.get("players", []):
            state.add_player(Player.from_dict(p_data))
            
        return state

    def save_to_file(self, filepath: str = "state.json") -> bool:
        """
        Saves the serialized state to a physical file safely using atomic write.
        """
        try:
            temp_path = f"{filepath}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=4, ensure_ascii=False)
            
            # Atomic replacement prevents corruption if process dies during write
            os.replace(temp_path, filepath)
            return True
        except Exception as e:
            logger.error(f"Critical failure saving state to {filepath}: {e}")
            return False

    @classmethod
    def load_from_file(cls, filepath: str = "state.json") -> 'GameState':
        """
        Loads the state from a JSON file. Returns a fresh state if missing or corrupted.
        """
        if not os.path.exists(filepath):
            logger.warning(f"No existing save found at {filepath}. Starting fresh.")
            return cls()
            
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("Previous game state loaded successfully.")
            return cls.from_dict(data)
        except json.JSONDecodeError as e:
            logger.error(f"Save file {filepath} is corrupted. Initializing blank state. Error: {e}")
            return cls()
        except Exception as e:
            logger.error(f"Unexpected error loading state from {filepath}: {e}")
            return cls()