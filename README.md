# 🧠 **Cognitas** *(a.k.a. Asdrubot)*  - Mafia Game Bot (v2.0)

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![Discord](https://img.shields.io/badge/Discord-Bot-5865F2?logo=discord&logoColor=white)
![Status](https://img.shields.io/badge/Status-Active-brightgreen)

Asdrubot is a custom **Discord bot** for hosting **Mafia / Werewolf-style games** with advanced mechanics, roleplay depth, and moderator tools.  
Built for **personal use and supervised hosting** — not for public deployment.

---

## 📂 Project Structure

**Disclaimer:** Cognitas is a one-man project, and that man doesn't have a good documentation practice, so the actual structure might not relate to the following tree. 

```
cognitas/
 ├─ bot.py              # Main bot entrypoint
 ├─ core/               # Core game logic, state, storage, roles
 │   ├─ actions.py      # Phase-aware action storage (day/night)
 │   ├─ lunar.py        # Lunar cycle management
 │   ├─ phases.py       # Start/end day & night, reminders
 │   ├─ players.py      # Player management (flags, effects, alive/dead)
 │   └─ storage.py      # Save/load persistent state
 └─ cogs/               # Discord slash command groups
     ├─ actions.py      # /act (player) and /actions (admin)
     ├─ game.py         # /game_* and role assignment
     ├─ players.py      # /player group
     ├─ voting.py       # /vote group and phase voting
     ├─ moderation.py   # purge, channel setup, broadcast
     ├─ maintenance.py  # sync, list, clean commands
     ├─ role_debug.py   # role debug tools
     ├─ fun.py          # /dice, /coin
     └─ help.py         # /help
```

---

## ✨ Features

- 🌓 **Day/Night Phases** — Automatically open/close discussion and action phases.  
- 🌑 **Lunar Cycle** — 4-step moon cycle (`New → First Quarter → Full → Last Quarter`) with game mechanics attached.  
- 📊 **Voting System** — Supports votes, hidden votes, weighted votes, and lynch thresholds.  
- 🎯 **Role Flags** — Player behavior driven by flags:  
  - `day_act`, `night_act` (can perform actions in that phase)  
  - `hidden_vote`, `voting_boost`, `no_vote`, `silenced`  
  - `lynch_plus`, `immune_night`, `protected`, etc.  
- 📜 **State Persistence** — Full state stored in `state.json`, with auto-backup.  
- 🛡️ **Moderator Tools** — Clear votes, purge messages, broadcast announcements.  
- 🎲 **Fun/utility Commands** — Dice rolls and coin flips for roleplay.  

---

## 👥 Player Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/player list` | List all registered players |
| `/player alias_show @user` | Show aliases of a player |
| `/votes` | Show current day’s voting breakdown |
| `/status` | Show phase (day/night), day counter, lunar phase, time left, and alive players |
| `/vote cast @user` | Cast a vote |
| `/vote clear` | Remove your vote |
| `/vote mine` | Show your vote |
| `/vote end_day` | Request to end the day (needs 2/3 alive players) |
| `/act [@target] [note]` | Perform your day/night action (if allowed by role) |
| `/dice [faces]` | Roll a die (default 20) |
| `/coin` | Flip a coin |

---

## 🛡️ Admin / Moderator Commands

### Player Management
- `/player register @user [name]` — Register a player.  
- `/player unregister @user` — Remove a player.  
- `/player rename @user <new_name>` — Change a player’s name.  
- `/player view @user` — Show detailed player info.  
- `/player edit @user field value` — Safely edit player fields.  
- `/player set_flag @user <flag> <value>` — Set a flag (typed).  
- `/player del_flag @user <flag>` — Remove a flag.  
- `/player add_effect @user <effect>` — Add an effect.  
- `/player remove_effect @user <effect>` — Remove an effect.  
- `/player kill @user` — Mark player as dead.  
- `/player revive @user` — Mark player as alive.  

### Game Management
- `/game_start [profile]` — Start a new game.  
- `/game_reset` — Reset game state.  
- `/finish_game [reason]` — End the game.  
- `/who [@user]` — Show info for a user.  
- `/assign @user <role>` — Assign a role.  

### Phases & Voting
- `/start_day [duration] [channel] [force]` — Start Day phase.  
- `/end_day` — End Day phase.  
- `/start_night [duration]` — Start Night phase.  
- `/end_night` — End Night phase.  
- `/clearvotes` — Clear all votes.  

### Actions & Logs
- `/actions logs [phase=auto|day|night] [number] [user] [public=false]` — Logs of actions per phase.  
- `/actions breakdown [phase=auto|day|night] [number] [public=false]` — Who can act, who acted, who is missing.  

### Moderation & Utility
- `/bc <text>` — Broadcast to Day channel.  
- `/set_day_channel [#channel]` — Set Day channel.  
- `/set_admin_channel [#channel]` — Set Admin channel.  
- `/set_log_channel [#channel]` — Set Logs channel.  
- `/show_channels` — Show configured channels.  
- `/purge [limit] [user] [contains] …` — Bulk delete messages.  

### Maintenance
- `/debug_roles` — Show loaded roles.  
- `/sync_here` — Sync commands in current guild.  
- `/list_commands [scope]` — List commands (global or guild).  
- `/clean_commands [scope] [nuke]` — Remove stray commands.  

---

## 🚧 Coming Soon

- More expansions, more features for those expansions, more for the **INFINITE MAFIA**.

---

## 📜 Notes

- Designed for **manual moderator supervision**.  
- State auto-saves to `state.json` in repo root.  
