# 📖 Asdrubot v2.0 — Commands Reference

This document lists all available slash commands, grouped by **Player** and **Administrator** commands.

---

## 👥 Player Commands

- `/player list`  
  Show all registered players, separated into alive and dead.

- `/player alias_show @user`  
  Display all aliases of a given player.

- `/player alias_add @user <alias>` *(admin only)*  
  Add an alias to a player.

- `/player alias_del @user <alias>` *(admin only)*  
  Remove an alias from a player.

- `/vote cast @user`  
  Cast your vote against a player during the Day.

- `/vote clear`  
  Remove your current vote.

- `/vote mine`  
  Show your current vote.

- `/vote end_day`  
  Request to end the Day without a lynch. If 2/3 of alive players request this, the Day will close early.

- `/votos`  
  Show the breakdown of all current votes.

- `/status`  
  Show the current Day status and time remaining.

- `/act @user [note]`  
  Register your night action (if applicable to your role).

- `/dice [faces=20]`  
  Roll a die with the given number of faces.

- `/coin`  
  Flip a coin (Heads/Tails).

- `/help`  
  Show the command list (ephemeral embed).

---

## 🛡️ Administrator Commands

### Player Management
- `/player register @user [name]`  
  Register a player into the game.

- `/player unregister @user`  
  Remove a player from the game.

- `/player rename @user <new_name>`  
  Change the display name of a player.

- `/player edit @user field:<alive|role|name|vote_weight|voting_boost|hidden_vote> value:<...>`  
  Edit a core field of a player directly.

- `/player kill @user`  
  Mark a player as dead.

- `/player revive @user`  
  Mark a player as alive again.

- `/player set_flag @user key value`  
  Add or update a custom flag on a player.

- `/player del_flag @user key`  
  Remove a custom flag from a player.

- `/player add_effect @user effect`  
  Add a custom effect to a player.

- `/player remove_effect @user effect`  
  Remove a custom effect from a player.

- `/player view @user`  
  Show a full embed with the player’s state (name, alive, role, flags, effects, aliases, vote weights).

### Game Management
- `/game_start [profile=default]`  
  Start a new game with the specified role profile.

- `/game_reset`  
  Reset the current game state (players remain registered).

- `/finish_game [reason]`  
  Finish the current game and archive state.

- `/who [@user]`  
  Show information about a specific player (role if assigned).

- `/assign @user <role>`  
  Assign a role to a player.

### Phases & Voting
- `/start_day [duration] [channel] [force=false]`  
  Start the Day phase, set duration and channel. Force replaces an active Day.

- `/end_day`  
  End the Day phase. If a player has majority votes, they are lynched.

- `/start_night [duration]`  
  Start the Night phase and open the Night channel.

- `/end_night`  
  End the Night phase and advance to the next Day.

- `/clearvotes`  
  Clear all current votes (admin override).

### Moderation & Utility
- `/bc <text>`  
  Broadcast a message to the configured Day channel.

- `/set_day_channel [#channel]`  
  Configure the Day channel.

- `/set_admin_channel [#channel]`  
  Configure the Admin channel.

- `/set_log_channel [#channel]`  
  Configure the Logs channel.

- `/show_channels`  
  Display the currently configured Day and Admin channels.

- `/purge <N>`  
  Delete the last N messages in the current channel (requires Manage Messages).

---

## 🌙 Expansion-Specific (SMT)
- **Moon phases** automatically advance each Day/Night if profile `smt` is used.  
  (No direct commands; handled by expansion hooks.)
