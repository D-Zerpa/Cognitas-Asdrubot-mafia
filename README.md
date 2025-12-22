# 🧠 **Cognitas** *(a.k.a. Asdrubot)* — Mafia Game Engine (v3.0)

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)
![Discord](https://img.shields.io/badge/Discord.py-2.0%2B-5865F2?logo=discord&logoColor=white)
![Status](https://img.shields.io/badge/Status-Active-brightgreen)
![License](https://img.shields.io/badge/License-Private-red)

**Cognitas** is a modular game engine for Discord designed to host complex *Mafia* / *Werewolf* games.
Unlike traditional moderation bots, Cognitas acts as an **Assisted Game Master**, automating heavy logic (votes, statuses, phases, permissions) while leaving narrative control in the hands of the human host.

> ⚠️ **Note:** Project designed for personal use and supervised hosting. Not intended for massive public deployment.

---

## ✨ Key Features (v3.0)

### ⚙️ Modular Architecture
The bot has been rewritten to separate core logic from game content.
- **Expansion System:** Load different rules and roles (e.g., *Base*, *Persona 3*, *SMT*) without modifying source code.
- **Status Engine:** A dedicated system to manage *buffs* and *debuffs* (Silence, Paralysis, Poison, Confusion) with automatic decay logic and persistence.

### 🌓 Automated Game Cycle
- **Day/Night Phases:** Automatic management of channel permissions (open/close) and phase announcements.
- **Advanced Voting:** Support for hidden votes, double votes, sanctions (fractional voting), and dynamic lynch thresholds.
- **Night Actions:** Centralized action queue (`/act`) with status validation (e.g., a *Drowsy* player cannot act).

### 🏗️ Intelligent Infrastructure
- **Dynamic Channels:** The bot creates and manages private channels ("confessionals") automatically linked to player roles.
- **World Clocks (Timezones):** Automatic renaming of voice channels to display time in multiple countries, facilitating international coordination.
- **Atomic Persistence:** The entire game state (votes, players, effects) is saved to disk (`state.json`) in real-time, ensuring resilience against restarts.

## 📂 Project Structure

The code is organized to facilitate scalability and maintenance:

```
cognitas/
 ├── bot.py                 # Entry point (Startup & Cogs loading)
 ├── config.py              # Global configuration (Intents, Paths)
 │
 ├── core/                  # SYSTEM CORE
 │    ├── actions.py        # Phase-aware action queue & validation
 │    ├── game.py           # Game orchestrator & role assignment
 │    ├── infra.py          # Discord API management (Channels/Roles)
 │    ├── johnbotjovi.py    # Image processing (Lynch posters)
 │    ├── logs.py           # Logging system
 │    ├── lunar.py          # Lunar cycle logic
 │    ├── phases.py         # Day/Night transition logic & Timers
 │    ├── players.py        # Entity management (Life, Death, Flags)
 │    ├── reminders.py      # Phase timeout reminders
 │    ├── roles.py          # Role data loading
 │    ├── state.py          # Runtime game state definition
 │    ├── storage.py        # Atomic JSON persistence
 │    └── votes.py          # Voting engine & tallying
 │
 ├── status/                # STATUS ENGINE
 │    ├── __init__.py       # Registry & Base Status class
 │    ├── builtin.py        # Standard effects (Paralyzed, Jailed, etc.)
 │    └── engine.py         # Logic for application, ticking, and cleansing
 │
 ├── expansions/            # GAME CONTENT
 │    ├── __init__.py       # Expansion registry & hooks
 │    ├── myexp.py          # Template for new expansions
 │    ├── persona.py        # Persona 3 mechanics (Nyx, SEES, Fuuka)
 │    ├── philosophers.py   # Base mechanics
 │    └── smt.py            # SMT mechanics (Law/Chaos)
 │
 ├── cogs/                  # INTERFACE (Slash Commands)
 │    ├── actions.py        # /act, /actions logs
 │    ├── bootstrap.py      # /setup, /wipe, /link_roles
 │    ├── fun.py            # /dice, /coin, /lynch
 │    ├── game.py           # /game_start, /game_reset
 │    ├── help.py           # /help
 │    ├── maintenance.py    # /sync_here, /clean_commands
 │    ├── moderation.py     # /set_channels, /bc
 │    ├── players.py        # /player register, /view, /set_flag
 │    ├── role_debug.py     # /debug_roles
 │    ├── status.py         # /effects apply, /effects list
 │    ├── timezones.py      # /tz add, /tz list
 │    └── voting.py         # /vote cast, /status, /votes
 │
 └── data/                  # DATA FILES (Roles configuration)
      ├── roles_default.json
      ├── roles_p3.json
      └── roles_smt.json
```


## 🎮 Included Expansions

### 🏛️ Base (Philosopher's Game)
The classic experience. Standard roles, majority voting, and a day/night cycle without external mechanics.

### ⚖️ Shin Megami Tensei (Law & Chaos)
A conflict of cosmic proportions based on SMT IV. Turning a simple mafia game into a decently-tailored narrative piece.
- **Dual Mafia:** Two rival factions (Order vs. Chaos) fighting against the Samurai (Town) and each other.
- **Divine Judgment:** The Order faction performs a ritual each night whose outcome (Kill/Convert).
- **Transformations:** Samurai can fuse with demons/angels to become Heralds (Mafia recruits) or powerful neutral entities.
- **YHVH:** A hidden independent role seeking to put all players into eternal Stasis.
- **Lunar phase mechanics:** Some roles or faction-driven mechanics's effects are buffed/debuffed by the moon. 

### 🌕 Persona 3 (The Dark Hour)
A complex expansion based on the Atlus JRPG. 
- **Apocalypse Clock:** Countdown mechanic based on the death of "Arcana" roles.
- **Nyx Entropy:** Automatic global events (mass paralysis, confusion) as the clock advances.
- **SEES System:** Group chat with "Radar" abilities (Fuuka) that detect hostile actions in real-time.
- **Evolving Roles:** Each role has unique perks for following an specific game style, which makes the game an unique experience for each player.

### 📚 Instructions

- All information about the features and the overall use of the bot (Commands, Flag information, etc.) is on `docs/features`.


### 📜 License and Credits

Developed by **D-Zerpa et al.** This project uses `discord.py` and `Pillow`. Assets and images from Persona 3 and SMT are property of ATLUS/SEGA.