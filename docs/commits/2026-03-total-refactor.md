REFACTOR: Complete architectural rebuild from scratch (v2.0)

Wiped the legacy codebase and rebuilt the entire system using a strict Separation of Concerns (SoC) pattern, fully decoupling the mathematical game engine from the Discord API UI layer. 

Core Engine:
- Implemented `GameState` for centralized memory, configuration, and state serialization.
- Built `ActionManager` with priority queues, resolution timing (Instant/Queued), and RNG accuracy checks.
- Created a scalable `ConditionManager` to natively handle buffs, debuffs, redirections, and stacking rules.
- Added `VotingManager` with dynamic weight calculations and absolute majority triggers.

Data & Expansions:
- Built `RoleLoader` to parse roles, passive flags, and abilities dynamically from JSON data files.
- Implemented the `BaseExpansion` hook system (Strategy Pattern) to support complex custom mechanics (e.g., Persona 3 Oracle Radar, Nyx counters) without touching the core engine.

Discord Integration & UI (Cogs):
- Terraforming & Moderation: Added `/terraform`, `/wipe`, and smart auto-assignment to generate and manage isolated private channels and role permissions instantly.
- Gameplay: Added `/act`, `/vote`, and `/status` featuring dynamic Discord Unix timestamps and localized UI feedback.
- Time Management: Built `tasks.loop` background watchers to handle real-time phase countdowns, server clocks (Voice Channels), and automatic text channel locking.
- God Tools: Added `/force_kill`, `/force_revive`, `/set_flag`, and manual timer adjustments for live Game Master intervention.