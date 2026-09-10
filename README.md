# 🧠 **Cognitas** *(a.k.a. Asdrubot)* — Mafia Game Engine (v4.0)

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
 ├── config.py              # Global configuration
 │
 ├── cogs/                  # INTERFACE (Slash Commands)
 │    ├── gameplay.py       # Player actions and game flow commands
 │    ├── host.py           # Game master and moderation utilities
 │    ├── misc.py           # Miscellaneous and fun commands
 │    ├── system.py         # Bot system operations and maintenance
 │    └── timer.py          # Phase timer management
 │
 ├── conditions/            # STATUS ENGINE
 │    ├── __init__.py       # Registry initialization
 │    ├── builtin.py        # Standard effects registry
 │    ├── engine.py         # Logic for application, ticking, and cleansing
 │    └── factory.py        # Status object creation and validation
 │
 ├── core/                  # SYSTEM CORE
 │    ├── __init__.py
 │    ├── actions.py        # Phase-aware action queue & validation
 │    ├── models.py         # Core data models and data structures
 │    ├── state.py          # Runtime game state definition
 │    ├── storage.py        # Atomic JSON persistence
 │    ├── time.py           # Phase transition and timezone logic
 │    └── voting.py         # Voting engine & tallying
 │
 ├── data/                  # DATA MANAGEMENT
 │    ├── __init__.py
 │    ├── loaders.py        # JSON parsing and validation logic
 │    └── json/             # Static role databases
 │         ├── roles_default.json
 │         ├── roles_expedition33.json
 │         ├── roles_lovecraft.json
 │         ├── roles_p3.json
 │         └── roles_smt.json
 │
 ├── expansions/            # GAME CONTENT
 │    ├── __init__.py       # Expansion registry & hooks
 │    ├── base.py           # Classic/Default mechanics
 │    ├── expedition33.py   # Expedition 33 mechanics
 │    ├── lovecraft.py      # Lovecraftian mechanics
 │    ├── lovecraft_commands.py # Custom slash commands for Lovecraft expansion
 │    ├── persona3.py       # Persona 3 mechanics (Nyx, SEES, Arcanas)
 │    ├── smt.py            # SMT mechanics (Law/Chaos, Samurai)
 │    └── dnd.py            # DND mechanics (HP management, Classes/Subclasses)
 │
 └── utils/                 # UTILITIES
      ├── __init__.py
      └── discord_sync.py   # Discord API synchronization helpers
```


## 🎮 Included Expansions

### 🏛️ Base (Classic Game)
The standard experience loaded via `base.py`. Standard roles, majority voting, and a regular day/night cycle without external mechanics

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

### 🐙 Lovecraft (Cosmic Horror)
A custom expansion integrating sanity and cosmic horror mechanics. 
- **Paranoia and Sanity:** The Paranoia makes Sanity levels go down, when levels get to 0, the mafia wins.
- **Chaotic Town:** You can't trust the Townspeople, some of them are crazy and could make survival even harder.
- **Misterious Forces are working:** Who's killing everyone? Every night the voices demand a soul.
- **Dynamic Mafia:** No one is evil, but everyone could be. Trust no one, everyone could be the mafia. 

### 🧭 Expedition 33 (Express Mafia)
A thematic expansion. A bit more complex than the Base mafia, but without any secondary mechanic.


### 📚 Instructions

- All information about the features and the overall use of the bot (Commands, Flag information, etc.) is on `docs/features`.


### 📜 License and Credits

Developed by **D-Zerpa et al.** This project uses `discord.py` and `Pillow`. Assets and images from Persona 3 and SMT are property of ATLUS/SEGA.