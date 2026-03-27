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
        # Magia de rutas absolutas:
        # 1. Obtiene la carpeta actual (cognitas/core)
        core_dir = os.path.dirname(os.path.abspath(__file__))
        # 2. Sube un nivel (cognitas/)
        base_dir = os.path.dirname(core_dir)
        # 3. Entra a la carpeta de datos (cognitas/data/)
        self.data_dir = os.path.join(base_dir, "data")
        
        # Se asegura de que la carpeta 'data' exista (por si acaso)
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 4. Construye la ruta final y absoluta: .../cognitas/data/state.json
        self.filepath = os.path.join(self.data_dir, filename)

    def save_state(self, state: GameState) -> bool:
        """Invokes the GameState save method with the absolute path."""
        logger.info(f"Guardando partida en ruta absoluta: {self.filepath}")
        return state.save_to_file(self.filepath)

    def load_state(self) -> Optional[GameState]:
        """Invokes the GameState load method with the absolute path."""
        if not os.path.exists(self.filepath):
            logger.warning(f"No se encontró archivo de guardado en: {self.filepath}")
            return None
            
        logger.info(f"Cargando partida desde ruta absoluta: {self.filepath}")
        return GameState.load_from_file(self.filepath)