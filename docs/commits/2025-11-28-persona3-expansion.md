### 🌕 Feat: Persona 3 Expansion - Nyx, SEES & Automation

**Implemented full mechanics for the Persona 3 expansion profile, including automated phase hooks and role-specific logic.**

#### 🎭 Expansion Logic (`expansions/persona.py`)
* **Nyx's Countdown:** Implemented `banner_for_day` to display the "Arcana Countdown" at dawn. Added `_count_arcanas` helper to track living Arcana carriers.
* **Nyx's Curse (Automated Entropy):** Added `_trigger_nyx_effects` hook on Day Start. Automatically calculates the Apocalyse Phase (based on dead Arcanas) and applies global status effects (Paralysis, Drowsiness, Confusion) to random valid targets.
* **Fuuka's Tactical Log:** Implemented automated morning reports for Oracle players, listing actors from the previous night via `_send_fuuka_log`.
* **Fuuka's Radar:** Added `on_action_commit` hook to notify Oracles in real-time when a SEES member is targeted by an action.
* **Inheritance System:** Added `on_player_death` hook to handle special death events (like Nyx transferring to a new host or "Ryoji" reveal).

#### ⚙️ Core & Systems Support
* **Expansion Hooks:** Updated `core/phases.py` to await async expansion hooks (`on_phase_change`) and pass `guild` context, enabling expansions to send messages.
* **Player Flags:** Registered P3-specific flags in `cogs/players.py`: `arcana` (for the countdown), `sees` (for the radar), and `oracle` (for receiving intel).
* **Action Hook:** Updated `cogs/actions.py` to trigger `game.expansion.on_action_commit` after a successful `/act`, enabling reactive passives.
* **Resource Counters:** Registered hidden statuses (`BulletAmmo`, `RoseCounter`, `RageCharge`, `AffinityCharge`) to track role resources automatically via the Status Engine.

#### 🐛 Fixes & Refactors
* **Vote Calculation:** Fixed `compute_vote_weight` in `status/engine.py` to correctly add the `voting_boost` flag value.
* **Flag Cleanup:** Removed deprecated flags (`silenced`, `no_vote`) from definitions in favor of the Status Engine.
* **Role Assignment:** Hardened `assign_role` to wipe old flags preventing "ghost abilities" when players switch roles (critical for Nyx inheritance).