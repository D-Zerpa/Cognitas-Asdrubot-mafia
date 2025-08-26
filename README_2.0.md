# 🛠️ Asdrubot v2.0 - Developer Guide

This document explains the **technical structure** of the bot after the v2.0 refactor and migration to Slash Commands.  
It is intended for developers working on the project.

---

## 📂 Project Structure

```
cognitas/
 ├── bot.py               # Entry point (loads cogs, syncs slash commands)
 ├── core/                # Core game logic
 │   ├── phases.py        # Day/Night cycle handling (start/end + reminders)
 │   ├── votes.py         # Voting system (votes, breakdowns, thresholds, end_day 2/3)
 │   ├── players.py       # Player management (register, unregister, rename, aliases)
 │   ├── game.py          # Game state orchestration, roles loading, expansions
 │   ├── roles.py         # Role definitions loader (supports multiple profiles)
 │   ├── reminders.py     # Time reminders with relative Discord timestamps
 │   ├── storage.py       # Persistence (JSON/SQLite)
 │   └── state.py         # Global GameState object
 │
 ├── cogs/                # Slash command interfaces
 │   ├── players.py       # /player … commands
 │   ├── voting.py        # /start_day, /end_day, /vote …, /status, /votos
 │   ├── game.py          # /game_start, /assign, /who, /finish_game, /game_reset
 │   ├── moderation.py    # /bc, /purge, /set_day_channel, /set_admin_channel, /show_channels
 │   ├── actions.py       # /act (night actions)
 │   ├── help.py          # /help (command list)
 │   └── fun.py           # /dice, /coin, meme lynch (future)
 │
 ├── expansions/          # Optional expansions (game-specific rulesets)
 │   ├── __init__.py      # Base Expansion class (on_phase_change hooks)
 │   └── smt.py           # SMT expansion (moon phases)
 │
 ├── data/                # Role definitions
 │   ├── roles_default.json
 │   └── roles_smt.json   # Example for SMT expansion
 │
 ├── README.md
 ├── CHANGELOG_v2.0.md
 └── requirements.txt
```

---

## ⚙️ Core Principles

- **Separation of concerns**:  
  Core files (`core/`) hold **game logic only**.  
  Cogs (`cogs/`) only handle **slash command interface** and delegate to core.

- **Slash commands everywhere**:  
  Legacy prefix commands (`!`) have been removed.  
  All interactions are now via `/…` commands.

- **Profiles and expansions**:  
  - Roles are loaded from `data/roles_{profile}.json`.  
  - Expansions (e.g., SMT) can add hooks to phases (like moon cycles).

---

## 🔌 Adding a New Cog

1. Create a file under `cogs/` (e.g., `cogs/myfeature.py`).
2. Use `@app_commands.command` for single commands or `commands.GroupCog` for grouped commands.
3. Register in `bot.py` under `INITIAL_EXTENSIONS`.
4. Run the bot and check logs for “Slash synced …”.

Example:

```python
import discord
from discord import app_commands
from discord.ext import commands

class MyCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="hello", description="Say hello")
    async def hello(self, interaction: discord.Interaction):
        await interaction.response.send_message("Hello!")
        
async def setup(bot): await bot.add_cog(MyCog(bot))
```

---

## 🌙 Adding an Expansion

1. Create a file under `expansions/`, subclassing `Expansion` from `expansions/__init__.py`.
2. Implement hooks like `on_phase_change(game_state, new_phase)`.
3. Register expansion loading in `core/game.py` based on profile.

Example:

```python
from . import Expansion

class MyExpansion(Expansion):
    name = "myexp"

    def on_phase_change(self, game_state, new_phase: str):
        # Custom behavior
        game_state.my_var = f"Changed at {new_phase}"
```

---

## 🧪 Testing Checklist (Quick)

- `/player register`, `/player list`, `/player alias add` → Player system OK
- `/game_start profile: default`, `/assign`, `/who` → Game start & roles OK
- `/start_day 2m` → Day starts, reminders show up
- `/vote cast`, `/votos`, `/vote end_day` → Voting OK
- `/end_day`, `/start_night`, `/act`, `/end_night` → Phase cycle OK
- `/bc`, `/purge`, `/show_channels` → Moderation OK
- `/dice`, `/coin`, `/help` → Utilities OK
- `/game_start profile: smt` → Expansion SMT hooks work (moon_phase rotates)

---

## 🚀 Next Steps

- Add meme lynch generator.
- Add thematic day/night messages.
- Improve `/help` with Discord embeds.
