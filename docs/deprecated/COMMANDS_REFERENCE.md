# 📖 Asdrubot v3.0 — Commands Reference

This document lists all available slash commands available in the system.

> **Legend:**
> - `[argument]`: Optional argument.
> - `<argument>`: Required argument.
> - **(Phase-Aware)**: The command adapts automatically depending on whether it is Day or Night.

---

## 👥 Player Commands

General commands available to all participants in the game.

### 🗳️ Voting & Game Status
- **/help**
  Show the interactive command list menu.
- **/status**
  Displays the global game status: Current Phase, Day/Night Counter, Time Remaining, and Alive Players count.
  *(Depending on the expansion, it may show extra info like Lunar Phase).*
- **/votes**
  Shows the current voting tally, including progress bars towards lynch thresholds.
- **/vote cast `<member>`**
  Cast your vote against a player during the Day phase.
- **/vote clear**
  Remove your current vote.
- **/vote mine**
  Check who you are currently voting for.
- **/vote end_day**
  Vote to end the Day phase early (requires 2/3 majority of alive players).

### ⚔️ Actions & Roleplay
- **/act `[target]` `[note]`**
  **The main action command.** Register your role's ability for the current phase.
  - *Day Phase:* Requires the `day_act` flag.
  - *Night Phase:* Requires the `night_act` flag.
  - *Notes:* You HAVE to attach a note for the GM with your action (eg, kill, protect, block).
- **/player list**
  Show a list of all registered players, separated by Alive and Dead.
- **/player alias_show `<member>`**
  Display known aliases for a specific player.

### 🎲 Fun & Utility
- **/dice `[faces]`**
  Roll a die with N faces (Default: 20). useful for RNG based roles.
- **/coin**
  Flip a coin (Heads/Tails).
- **/lynch `<target>`**
  Generates a fake "Lynch Poster" image using the target's avatar (Purely cosmetic).

## 🛡️ Administrator / Moderator Commands

These commands require **Administrator** permissions (or specific permissions like *Manage Messages* where noted).

### 👥 Player Management
- **/player register `<user>` `[name]`**
  Register a player into the game and assign the "Alive" role.
- **/player unregister `<user>`**
  Remove a player from the game and revoke channel permissions.
- **/player rename `<user>` `<new_name>`**
  Change the display name of a player in the system.
- **/player view `<user>`**
  Show a full embed with the player’s state (name, alive, role, flags, active effects, aliases).
- **/player edit `<user>` `<field>` `<value>`**
  Safely edit stored player fields (e.g., `notes`, `name`).
  *(Note: Use `set_flag` for voting/gameplay attributes).*
- **/player set_flag `<user>` `<flag>` `<value>`**
  Set a gameplay flag (e.g., `hidden_vote`, `voting_boost`, `night_act`). Supports autocomplete.
- **/player del_flag `<user>` `<flag>`**
  Remove a flag from a player.
- **/player kill `<user>`**
  Mark a player as **Dead** (updates roles, clears votes, heals statuses).
- **/player revive `<user>`**
  Mark a player as **Alive** (updates roles, clears old statuses).

### 🧪 Status Engine (Effects)
*Manage buffs, debuffs, and counters.*
- **/effects apply `<user>` `<name>` `[duration]` `[source]`**
  Apply a status effect (e.g., `Silenced`, `Poisoned`, `RoseCounter`).
- **/effects heal `<user>` `[name]` `[all=false]`**
  Remove a specific status or cleanse all statuses from a player.
- **/effects list `[user]`**
  Show active statuses for a player, or a summary of all active effects in the game.
- **/effects inspect `<name>`**
  View technical details of a status (duration, blocking rules).

### 🎮 Game Management
- **/game_start `[profile]` `[alive_role]` `[dead_role]`**
  Start a new game.
  - `profile`: Ruleset to load (e.g., `default`, `smt`, `p3`).
  - `alive_role`/`dead_role`: (Optional) Link existing server roles for a manual setup.
- **/game_reset**
  Hard reset of the game state (wipes players, votes, and history).
- **/finish_game `[reason]`**
  Finish the current game and archive the state.
- **/assign `<user>` `<role>`**
  Assign a specific role (e.g., "Makoto Yuki") to a player and **link their private channel**.
- **/who `<user>`**
  Show role information for a user.

### 🗳️ Phases & Voting
- **/start_day `[duration]` `[channel]` `[force]`**
  Start the Day phase (opens chat, announces deadline, triggers status ticks).
- **/end_day**
  End the Day phase (closes chat, resolves lynch).
- **/start_night `[duration]`**
  Start the Night phase (closes chat, triggers status ticks).
- **/end_night**
  End the Night phase.
- **/clearvotes**
  Force clear all current votes.

### ⚔️ Actions & Logs
- **/actions logs `[phase]` `[number]` `[user]` `[public]`**
  View action history.
  - Filter by `user` to see their full history.
  - Filter by `number` to see a specific Day/Night log.
- **/actions breakdown `[phase]` `[number]`**
  See who **can act**, who **acted**, and who is **missing**.

### 🌍 Infrastructure & Timezones
- **/setup**
  Run the interactive setup wizard (Create channels, roles, and categories automatically).
- **/wipe**
  Delete all game channels tagged with `[ASDRUBOT]` (keeps Admin category).
- **/link_roles `<alive>` `<dead>`**
  Manually link existing roles to the bot without running `/setup`.
- **/tz add `<channel>` `<tz>` `<label>`**
  Add a clock to a voice channel (e.g., `Europe/Madrid`).
- **/tz list**
  List all active timezone clocks.
- **/tz edit `<channel>` ...**
  Modify an existing clock.
- **/tz remove `<channel>`**
  Remove a clock.

### 🛡️ Moderation & Utility
- **/bc `<text>`**
  Broadcast a message to the active Game Channel.
- **/set_channels `[game_channel]` `[admin]`**
  Bind the main text channels for the bot.
- **/set_log_channel `[channel]`**
  Set where system logs are sent.
- **/show_channels**
  Display current channel configuration.
- **/purge `[amount]` `[user]` ...** *(Manage Messages)*
  Bulk delete messages with filters.
- **/set_expansion `<profile>`**
  Switch expansion profile mid-game (use with caution).
- **/get_state**
  View a raw snapshot of the game state (Phase, Day #, Expansion).

### 🧰 Maintenance
- **/debug_roles**
  List all loaded role keys for the current expansion.
- **/sync_here**
  Force sync slash commands to the current server.
- **/list_commands**
  List registered commands.
- **/clean_commands**
  Remove stale commands.
