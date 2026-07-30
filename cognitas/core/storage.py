import os
import logging
from typing import Optional

from cognitas.core.state import GameState

logger = logging.getLogger("cognitas.storage")

class StorageManager:
    """
    Handles reading and writing the GameState to disk.
    Ensures the save file always goes to cognitas/data/state.json
    """
    def __init__(self, filename: str = "state.json"):
        # Absolute path resolution:
        # 1. Get current directory (cognitas/core)
        core_dir = os.path.dirname(os.path.abspath(__file__))
        # 2. Go up one level (cognitas/)
        base_dir = os.path.dirname(core_dir)
        # 3. Enter the data directory (cognitas/data/)
        self.data_dir = os.path.join(base_dir, "data")
        
        # Ensure the 'data' directory exists
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 4. Construct final absolute path: .../cognitas/data/state.json
        self.filepath = os.path.join(self.data_dir, filename)

    def save_state(self, state: GameState) -> bool:
        """Invokes the GameState save method with the absolute path."""
        logger.info(f"Saving game state to absolute path: {self.filepath}")
        return state.save_to_file(self.filepath)

    def load_state(self) -> Optional[GameState]:
        """Invokes the GameState load method with the absolute path."""
        if not os.path.exists(self.filepath):
            logger.warning(f"No save file found at: {self.filepath}")
            return None
            
        logger.info(f"Loading game state from absolute path: {self.filepath}")
        return GameState.load_from_file(self.filepath)