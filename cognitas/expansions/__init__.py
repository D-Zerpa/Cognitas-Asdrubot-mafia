from __future__ import annotations
from typing import Optional, Any, Dict, Type, Callable, List
import importlib
import logging
import sys

log = logging.getLogger(__name__)

# ==============================================================================
#  CLASE BASE (INTERFACE)
# ==============================================================================

class Expansion:
    """
    Base interface for all game expansions.
    Expansions can override lifecycle/phase hooks.
    """
    name: str = "base"

    # ---- Easter Egg message loader ----
    memes: dict[str, str | list[str]] = {}

    # ---- Lifecycle / phase hooks ----
    async def on_phase_change(self, guild: Any, game_state, new_phase: str) -> None: 
        pass

    # Nota: Cambiado a Any/dict porque P3 devuelve un diccionario {content, file_path}
    def banner_for_day(self, game_state) -> Optional[Any]: 
        return None
    
    def banner_for_night(self, game_state) -> Optional[Any]: 
        return None

    # Optional hooks
    def on_game_start(self, game_state) -> None: ...
    def on_game_end(self, game_state, *, reason: Optional[str] = None) -> None: ...
    def on_player_death(self, game_state, uid: str, *, cause: str) -> None: ...
    def validate_setup(self, roles_def: Dict[str, Any]) -> None: ...
    def get_status_lines(self, game_state) -> list[str]: return []

    # Specific ability-related hooks
    async def on_action_commit(self, interaction: Any, game_state, actor_uid: str, target_uid: str | None, action_data: dict) -> None:
        """
        Called after a player successfully registers an action via /act.
        Useful for passive reactions like Watchers, Trackers or Oracles.
        """
        pass


# ==============================================================================
#  SISTEMA DE REGISTRO (REGISTRY)
# ==============================================================================

_EXPANSION_REGISTRY: Dict[str, Type[Expansion]] = {}

def register(name: str) -> Callable[[Type[Expansion]], Type[Expansion]]:
    """Decorator to register an expansion by profile name."""
    key = (name or "").lower().strip()
    def _wrap(cls: Type[Expansion]) -> Type[Expansion]:
        _EXPANSION_REGISTRY[key] = cls
        # log.debug(f"Expansión registrada: {key} -> {cls.__name__}")
        return cls
    return _wrap

def get_registered(profile: str) -> Optional[Type[Expansion]]:
    return _EXPANSION_REGISTRY.get((profile or "").lower().strip())

def get_unique_profiles() -> list[str]:
    """
    Returns a list of unique canonical names from registered expansions.
    Deduplicates aliases by checking the class.
    """
    if not _EXPANSION_REGISTRY:
        _auto_import_all()
        
    unique_classes = set(_EXPANSION_REGISTRY.values())
    # Sort by name for consistent UI
    return sorted([cls.name for cls in unique_classes if hasattr(cls, "name")])


# ==============================================================================
#  MAPA DE ARCHIVOS & CARGADOR (LOADER)
# ==============================================================================

# Este mapa conecta el 'alias' que pide el usuario con el 'archivo.py' real.
# Es necesario para saber qué archivo importar antes de buscar en el registro.
PROFILE_MAP = {
    "p3": "persona3",
    "persona": "persona3",
    "persona3": "persona3",
    "smt": "smt_iv",
    "base": "default",
    # Añade aquí cualquier otro nombre corto que uses
}

def load_expansion_instance(profile_name: str) -> Optional[Expansion]:
    """
    Carga dinámicamente la expansión.
    1. Busca en el registro si ya está cargada.
    2. Si no, usa PROFILE_MAP para importar el archivo (lo que dispara el @register).
    3. Devuelve la instancia desde el registro.
    """
    if not profile_name:
        return None

    key = profile_name.lower().strip()

    # 1. ¿Ya está registrada en memoria? (Ej: tras un reload o uso previo)
    if key in _EXPANSION_REGISTRY:
        cls = _EXPANSION_REGISTRY[key]
        return cls()

    # 2. Si no está, necesitamos importar el archivo para que corra el @register
    # Buscamos el nombre del archivo en el mapa. Si no está, probamos con el nombre tal cual.
    module_name = PROFILE_MAP.get(key, key)

    try:
        module_path = f"cognitas.expansions.{module_name}"
        
        # Importamos (o recargamos) el módulo.
        # Al importarse, el decorador @register("p3") dentro de persona3.py se ejecutará.
        if module_path in sys.modules:
            importlib.reload(sys.modules[module_path])
        else:
            importlib.import_module(module_path)
        
        # 3. Volvemos a buscar en el registro
        if key in _EXPANSION_REGISTRY:
            cls = _EXPANSION_REGISTRY[key]
            log.info(f"✅ Expansión cargada y registrada: {key} (Clase: {cls.__name__})")
            return cls()
        
        # 4. Fallback: Si el archivo no usó @register, buscamos clase 'Expansion' (compatibilidad)
        mod = sys.modules[module_path]
        if hasattr(mod, "Expansion"):
            log.warning(f"⚠️ El archivo {module_name} no usó @register('{key}'). Usando clase 'Expansion' por defecto.")
            return mod.Expansion() # type: ignore

        log.warning(f"❌ El módulo {module_name} se cargó, pero no registró la clave '{key}' ni tiene clase 'Expansion'.")
        return None

    except ImportError:
        if module_name != "default":
            log.warning(f"ℹ️ No se encontró módulo de expansión: {module_name}")
        return None
    except Exception as e:
        log.error(f"❌ Error cargando expansión {module_name}: {e}")
        import traceback
        traceback.print_exc()
        return None


# ==============================================================================
#  UTILITIES FOR DISCOVERY (LEGACY SUPPORT)
# ==============================================================================

def list_registered_keys() -> list[str]:
    """Return registered expansion keys (ensure discovery first)."""
    _auto_import_all()
    return sorted(_EXPANSION_REGISTRY.keys())

def _auto_import_all() -> None:
    """
    Import known expansion modules so their @register decorators run.
    Uses PROFILE_MAP values to know what to import.
    """
    # Usamos los valores únicos del mapa para no importar repetidos
    known_modules = set(PROFILE_MAP.values())
    
    # Añade aquí otros módulos que no estén en el mapa si es necesario
    known_modules.update(["philosophers", "smt", "persona3"]) 

    for mod in known_modules:
        if mod == "default": continue
        try:
            importlib.import_module(f"cognitas.expansions.{mod}")
        except ImportError:
            pass
        except Exception as e:
            log.warning(f"Error auto-importando {mod}: {e}")

# Opcional: Poblar el registro al inicio si se desea
_auto_import_all()

