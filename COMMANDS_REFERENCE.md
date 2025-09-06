# 📖 Asdrubot — Commands Reference (Consolidated)

This document lists all available slash commands, grouped by **Player** and **Administrator / Moderator** commands.

> Notes
> - *(admin)* requires **Administrator**.
> - *(manage_messages)* requires **Manage Messages** (for moderators).
> - Some admin commands are visible only if you have permissions.
> - `/actions …` commands are phase-aware (Day/Night); `/act` auto-detects the current phase.

---

## 👥 Player Commands

- `/help`  
  Show the command list (ephemeral embed).

- `/player list`  
  Show all registered players, separated into alive and dead.

- `/player alias_show @user`  
  Display all aliases of a given player.

- `/votes`  
  Vote breakdown for the current day.

- `/status`  
  Global status: current phase (day/night), counter (Day N / Night N), lunar phase, time remaining, and alive players.

- `/vote cast @user`  
  Cast your vote against a player during the Day.

- `/vote clear`  
  Remove your current vote.

- `/vote mine`  
  Show your current vote.

- `/vote end_day`  
  Request to end the Day without a lynch (requires 2/3 of alive players).

- `/act [@target] [note]`  
  Register **your action** for the current phase (Day or Night), if your role allows it (via `day_act`/`night_act` flag).

- `/dice [faces=20]`  
  Roll a die with the given number of faces (2–1000).

- `/coin`  
  Flip a coin (Heads/Tails).

---

## 🛡️ Administrator / Moderator Commands

### 👥 Player Management
- `/player register @user [name]` *(admin)*  
  Register a player into the game.

- `/player unregister @user` *(admin)*  
  Remove a player from the game.

- `/player rename @user <new_name>` *(admin)*  
  Change the display name of a player.

- `/player view @user` *(admin)*  
  Show a full embed with the player’s state (name, alive, role, flags, effects, aliases).

- `/player edit @user field value` *(admin)*  
  Safely edit stored fields like `alive`, `name`, `role`, `effects`, `notes`.  
  _(Voting/lynch-related fields must be managed via flags.)_

- `/player set_flag @user <flag> <value>` *(admin)*  
  Set a flag on a player (typed; supports autocomplete). Examples: `hidden_vote` (bool), `voting_boost` (int), `night_act`/`day_act` (bool).

- `/player del_flag @user <flag>` *(admin)*  
  Remove a flag from a player.

- `/player add_effect @user <effect>` *(admin)*  
  Add an effect to a player.

- `/player remove_effect @user <effect>` *(admin)*  
  Remove an effect from a player.

- `/player kill @user` *(admin)*  
  Mark a player as dead.

- `/player revive @user` *(admin)*  
  Mark a player as alive again.

### 🎮 Game Management
- `/game_start [profile=default]` *(admin)*  
  Start a new game with the specified role profile.

- `/game_reset` *(admin)*  
  Hard reset of game state.

- `/finish_game [reason]` *(admin)*  
  Finish the current game and archive state (optional reason).

- `/who [@user]` *(admin)*  
  Show information about a specific player.

- `/assign @user <role>` *(admin)*  
  Assign a role to a player.

### 🗳️ Phases & Voting
- `/start_day [duration] [channel] [force=false]` *(admin)*  
  Start the Day phase, set duration and channel. `force` replaces an active Day.

- `/end_day` *(admin)*  
  End the Day phase.

- `/start_night [duration]` *(admin)*  
  Start the Night phase.

- `/end_night` *(admin)*  
  End the Night phase.

- `/clearvotes` *(admin)*  
  Clear all current votes.

### 🌓 Actions & Logs
- `/actions logs [phase=auto|day|night] [number] [user] [public=false]` *(admin)*  
  - With `user` **and no `number`**: shows that user’s **entire history** for the chosen phase (all days/nights).  
  - With `number` (optional `user`): shows logs for that specific Day/Night.

- `/actions breakdown [phase=auto|day|night] [number] [public=false]` *(admin)*  
  Who **can act** (alive with `day_act`/`night_act`), who **acted**, and who is **missing**, for that Day/Night.

### 🛡️ Moderation & Utility
- `/bc <text>` *(admin)*  
  Broadcast a message to the configured Day channel.

- `/set_day_channel [#channel]` *(admin)*  
  Configure the Day channel.

- `/set_admin_channel [#channel]` *(admin)*  
  Configure the Admin channel.

- `/set_log_channel [#channel]` *(admin)*  
  Configure the Logs channel.

- `/show_channels` *(admin)*  
  Display the configured Day and Admin channels.

- `/purge [limit=100] [user] [contains] [include_bots=false] [include_pinned=false]` *(manage_messages)*  
  Delete recent messages in the current channel with flexible filters.

### 🧰 Maintenance
- `/debug_roles` *(admin)*  
  List loaded role keys.

- `/sync_here` *(admin)*  
  Sync slash commands for the current server (instant).

- `/list_commands [scope=global|guild]` *(admin)*  
  List remote slash commands (global or this guild), plus local ones.

- `/clean_commands [scope=global|guild] [nuke=false] [prune_empty_roots=true] [also_remove=\"...\"]` *(admin)*  
  Remove stray slash commands, optionally nuke before syncing.
