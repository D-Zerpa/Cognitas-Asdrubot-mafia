# 🧠 **Cognitas** *(a.k.a. Asdrubot)*  

> 🎭 A modest **Discord bot** for running **Mafia / Werewolf-style games**.  
> Automates phases, tracks secret actions, manages voting, and keeps the game flowing.

![Banner](https://img.shields.io/badge/Discord-Mafia%20Bot-7289DA?style=for-the-badge&logo=discord&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge)

---

## 📂 **Project Structure**

| Folder / File | Purpose |
|--------------|---------|
| **bot.py** | Main entry point. Starts the Discord client and loads cogs. |
| **bot_t.py** | Alternative entry point for testing purposes. |
| **roles.json** | Stores all role definitions, abilities, and factions. |
| **state.json** | Saves the current game state for persistence across restarts. |
| **requirements.txt** | Project dependencies. |

### `cognitas/cogs/` — **Commands**
| File | Description |
|------|------------|
| **admin.py** | Admin commands: starting phases, assigning roles, etc. |
| **actions.py** | Manages Night actions and private role abilities. |
| **voting.py** | Handles voting logic, lynch thresholds, and vote clearing. |

### `cognitas/core/` — **Game Engine**
| File | Description |
|------|------------|
| **roles.py** | Loads roles from `roles.json` and resolves ability usage. |
| **state.py** | Central game state manager (players, phases, etc.). |
| **storage.py** | Saves and restores game progress automatically. |
| **timer.py** | Manages day/night timers, reminders, and locks channels. |
| **config.py** | Stores global configuration values. |

---

## ✨ **Features**

- 🕹️ **Good Game Automation** — Phases, players, votes, kills.
- ⏳ **Day & Night Timers** — Automatic starts, reminders & locks.
- 🧩 **Fully Configurable Roles** — Defined in `roles.json`.
- 🔒 **Secret Night Actions** — Private command usage.
- 🗳️ **Weighted Voting System** — Supports buffs & debuffs.
- 🛠️ **Persistent State** — Bot remembers game progress after restarts.
- 📢 **Admin Logs** — All actions logged privately.
- 🧑‍🤝‍🧑 **Multi-Channel Support** — Role, day, admin, and voting channels.

---

## 🎮 **Commands Overview**

### 🛠️ **Admin Commands**
| Command | Description |
|--------|------------|
| `!assign_roles` | Automatically assigns roles to registered players. |
| `!set_day_channel #channel` | Sets the default Day phase discussion channel. |
| `!set_admin_channel #channel` | Sets the admin log channel. |
| `!start_day [time] [#channel]` | Starts a new Day phase (default `24h`). |
| `!start_night [time] [#channel]` | Starts a new Night phase (default `12h`). |
| `!apply_mark @player` | Applies Plotino’s mark: 1 fewer vote needed to lynch. |
| `!clearvotes` | Clears all votes for the current Day. |
| `!finish_game` | Ends the session and resets the state. |
| `!purge <amount>` | Deletes messages in the current channel. |

---

### 🎭 **Player Commands**
| Command | Description |
|---------|------------|
| `!vote @player` | Votes to lynch a player during the Day phase. |
| `!unvote` | Removes your current vote. |
| `!act @target [note]` | Submits your Night action **secretly** *(auto-deletes)*. |
| `!status` | Displays the current game state and deadlines. |
| `!role` | Sends you your private role card via DM. |

---

## 🚧 **Coming Soon**
- 🎨 **Lynch Meme Generator** → Automatically generates memes when a player gets lynched.  
- 🔮 **Slash Commands + Autocomplete** → Modern UI with dropdown suggestions.  
- 📊 **Live Game Dashboard** → Real-time stats and voting visualizations.

---

## 📜 **License**
**MIT License** — Free to use, modify, and distribute.

---

> “Fiat Lux, Fiat Lusus” — *Let there be light, let there be play.*