2025-10 — Expansion System Refactor

### ✨ Features
- Added formal `Expansion` API with stable hooks:
  - `on_phase_change(game, new_phase)`
  - `banner_for_day(game)`
  - Optional lifecycle hooks (`on_game_start`, `on_game_end`, etc.)
- Implemented two concrete expansions:
  - `PhilosophersExpansion` (base, no global effects)
  - `SMTExpansion` (handles lunar cycle via core.lunar)

### 🧠 Core refactor
- `core/game.py`: `_load_expansion_for()` now always returns a valid Expansion instance.
- `core/phases.py`: removed direct lunar logic; now calls expansion hooks for phase transitions and dawn banners.
- `core/storage.py`: `_ensure_defaults()` ensures `game.expansion` is set after load.
- `config.py`: added `DEFAULT_PROFILE` (env-configurable default expansion).

### 🛠 Admin commands (ModerationCog)
- `/set_expansion` — change active expansion (optional `force` flag).
- `/set_phase` — force game phase to day/night.
- `/set_day` — set current day number.
- `/bump_day` — increment/decrement day counter.
- `/get_state` — view compact snapshot (phase, day, profile, channels, banner preview).

### 🧩 Extras
- Added optional registry decorator (`@register("name")`) for easy expansion registration.
- Added template `expansions/myexp.py` for new expansions.
- Core now fully agnostic to expansion mechanics.

### ✅ Result
Core logic decoupled from game-specific content.  
New expansions can be added without modifying core files.  
Moderators can safely inspect and adjust game state through slash commands.
