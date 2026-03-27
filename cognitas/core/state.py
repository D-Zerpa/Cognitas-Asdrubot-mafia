import json
import os
import logging
from typing import Dict, Any, Optional, List
from .models import Player
from cognitas.core.time import Phase

logger = logging.getLogger("cognitas.state")

class GameState:
    """
    Central manager for the match state. 
    Handles player data, current phase/cycle, persistence, and volatile queues.
    """
    def __init__(self):
        self.players: Dict[int, Player] = {}
        self.phase: Phase = Phase.SETUP  
        self.cycle: int = 0

        self.discord_setup: Dict[str, Optional[int]] = {
            "game_channel_id": None,
            "log_channel_id": None,
            "graveyard_channel_id": None,
            "alive_role_id": None,
            "dead_role_id": None,
            "expansion": None
        }
        
        self.votes: Dict[int, Any] = {}
        self.vote_weights: Dict[int, int] = {}
        self.end_day_votes: set[int] = set()
        self.action_queue: List[Dict[str, Any]] = []

    def add_player(self, player: Player) -> None:
        self.players[player.user_id] = player

    def get_player(self, user_id: int) -> Optional[Player]:
        return self.players.get(user_id)

    def get_alive_players(self) -> List[Player]:
        return [p for p in self.players.values() if p.is_alive]

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the full game state."""
        return {
            "phase": self.phase.name if isinstance(self.phase, Phase) else "SETUP",
            "cycle": self.cycle,
            "discord_setup": self.discord_setup,
            "players": [p.to_dict() for p in self.players.values()],
            "votes": self.votes,
            "vote_weights": self.vote_weights,
            "end_day_votes": list(self.end_day_votes),
            "action_queue": self.action_queue
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GameState':
        """Rebuilds the state from a dictionary."""
        state = cls()
        
        raw_phase = data.get("phase", "SETUP")
        if isinstance(raw_phase, str):
            clean_phase = raw_phase.split(".")[-1] if "Phase." in raw_phase else raw_phase
            try:
                state.phase = Phase[clean_phase.upper()]
            except KeyError:
                state.phase = Phase.SETUP
        else:
            state.phase = Phase.SETUP
            
        state.cycle = data.get("cycle", 0)
        state.discord_setup.update(data.get("discord_setup", {}))
        
        for p_data in data.get("players", []):
            state.add_player(Player.from_dict(p_data))
            
        saved_votes = data.get("votes", {})
        state.votes = {int(k) if k.isdigit() else k: v for k, v in saved_votes.items()}
        saved_weights = data.get("vote_weights", {})
        state.vote_weights = {int(k) if k.isdigit() else k: v for k, v in saved_weights.items()}
        state.end_day_votes = set(data.get("end_day_votes", []))
        state.action_queue = data.get("action_queue", [])
            
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