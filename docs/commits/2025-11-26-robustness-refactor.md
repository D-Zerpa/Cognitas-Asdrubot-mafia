### 🛠️ Robustness Refactor: Concurrency, Integrity & Status Hardening

**Major architectural improvements and critical bug fixes resulting from a full code audit.**

### ⚡ Performance & Stability
* **Async Image Processing:** Refactored `johnbotjovi.lynch` to run blocking PIL operations in a thread executor, preventing Event Loop freezes during image generation.
* **Circular Import Resolution:** Decoupled expansion loading from `core.game`. Introduced `load_expansion_instance` factory in `expansions/__init__.py` to resolve dependency cycles with `storage`.
* **Safe State Loading:** Updated `load_state` to raise a critical exception instead of returning an empty dict on failure, preventing accidental overwrite of persistent data.

### 🏗️ Architecture & Channels
* **Channel Linking Refactor:** Removed channel creation from `/register`. Channels are now pre-created by bootstrap and linked dynamically to players during `/assign` based on canonical role names.
* **Permission Hygiene:** Updated `/unregister` to explicitly revoke channel permissions for removed players.

### 💀 Game Integrity (Death & Life)
* **Unified Death Logic:** Centralized death handling in `process_death`. Ensures `alive=False`, vote clearing, status cleansing, and role updates happen consistently for both `/kill` and lynching.
* **Clean Revive:** Updated `/revive` to automatically cleanse existing statuses (poison, silence) before bringing a player back.
* **Ghost Ability Fix:** Fixed `assign_role` to overwrite player flags instead of merging them, preventing players from retaining abilities (like immunity) from previous roles.
* **Game Reset Fix:** `game_start` now properly clears `status_map` and `status_log` to prevent state leakage between games.

### 🧪 Mechanics & Status Engine
* **Dead Actions:** Removed the hardcoded `alive` check in `/act` to allow specific roles (e.g., Chidori/Mediums) to interact with the dead.
* **Bulletproof Status Duration:** Introduced `decrement_on` policy (`day`, `night`, `always`) to `Status` class.
* **Hardened Built-ins:** Updated `Paralyzed`, `Silenced`, `Jailed`, and `Confusion` with explicit decay policies to correctly handle phase transitions (e.g., Confused persists across Night->Day).