# 🎌 Player Flags Catalog

Use `/player set_flag <member> <flag> <value>` to apply these flags.  
Values are automatically parsed (`true/false` → bool, numbers → int, else → string).

---

## 🗳️ Voting Behavior

| Flag          | Type  | Aliases                 | Description                                    |
|---------------|-------|-------------------------|------------------------------------------------|
| `hidden_vote` | bool  | `incognito`, `hidden`   | Vote is anonymous in public breakdown/status. |
| `voting_boost`| int   | `vote_boost`, `vote_bonus` | Adds to the player’s ballot weight (1+boost). |
| `no_vote`     | bool  | `silenced_vote`, `mute_vote` | Player cannot vote (ballot value = 0).      |
| `silenced`    | bool  | —                       | Player is silenced, treated as no voting power.|

---

## ⚖️ Lynch Threshold Modifiers

| Flag           | Type | Aliases                          | Description                                    |
|----------------|------|----------------------------------|------------------------------------------------|
| `lynch_plus`   | int  | `lynch_resistance`, `needs_extra_votes` | Extra votes required to lynch this target. |

---

## 🌙 Night / Action Modifiers

| Flag           | Type  | Aliases         | Description                                     |
|----------------|-------|-----------------|-------------------------------------------------|
| `immune_night` | bool  | `night_immune`  | Player is immune to night eliminations.        |
| `action_blocked` | bool | `blocked`, `role_blocked` | Night action is blocked for this player. |
| `protected`    | bool  | —               | Player is temporarily protected from kills.    |

---

## 📝 Notes

- **Types**:  
  - `bool` → `true/false/on/off/yes/no/1/0`  
  - `int` → any integer (e.g. `2`, `5`, `10`)  
  - `str` → free text (notes, tags, etc.)
- **Canonical names** are shown in the **Flag** column.  
- **Aliases** are accepted as input and resolve to the canonical flag automatically.  
- Add new flags by editing `FLAG_DEFS` in the cog; they’ll show up here and in autocomplete.
