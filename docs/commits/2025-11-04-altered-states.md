### ✨ New Altered States System
- Added a new modular Status system under `cognitas/status/`:
  - `__init__.py` → registry and base Status class
  - `engine.py` → apply / heal / tick / resolve logic
  - `builtin.py` → built-in statuses: Paralyzed, Drowsiness, Confusion,
    Jailed, Silenced, Double vote, Sanctioned, Wounded, Poisoned

### ⚙️ Core integration
- `core/phases.py`: calls `SE.tick()` at each phase start
  (day = public banners, night = DM banners)
- `core/storage.py`: persists `status_map` and `status_log`
- `core/votes.py`: now uses status-aware voting logic
  (Wounded blocks vote; Sanctioned halves/blocks; Double vote adds weight)

### 🗳️ Voting improvements
- `_voter_vote_value()` and `_tally_votes_simple_plus_boosts()` updated to
  handle fractional vote weights
- Votes display as `2.5 / 6` when fractional
- `check_action(..., "vote")` fully enforced for blockers

### 🧍 Player system
- `core/players.py`: `/register` now creates private role channels
  (`role_channel_id`) and stores them on each player
- Added `_slug()` helper for safe channel names
- `cogs/players.py`: `hidden_vote` now read exclusively from `flags.hidden_vote`
  (no top-level key); `vote_boost` and `vote_weight` remain unchanged

### ⚔️ Actions & Phases
- `/act` command (in `cogs/actions.py`):
  - Requires usage from the player’s private role channel
  - Checks `SE.check_action()` for status blocks (Paralyzed, Drowsiness, Jailed)
  - Automatically redirects target on Confusion tails
- `start_day` and `start_night` now process status ticks automatically

### 💾 Persistence & safety
- Added `status_map` and `status_log` to game save/load
- All statuses auto-cleared on player death (`SE.heal(all_=True)`)

### 🧩 GM tools
- Added `cogs/status.py`:
  - `/status apply`, `/status heal`, `/status list`, `/status inspect`
  - Autocomplete for all registered statuses
  - Supports custom duration and full cleanse
- Added `/votes_sanity` diagnostic command (optional) to compare
  legacy vs. status-driven vote weights

### ✅ Result
Core systems now integrate fully with the Altered States engine.
Status effects are modular, persistent, and affect voting/action behavior.
Players receive dedicated role channels for commands, enabling full role isolation.