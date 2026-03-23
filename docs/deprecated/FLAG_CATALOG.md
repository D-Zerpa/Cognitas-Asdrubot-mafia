# 🎌 Player Flags Catalog (v3.0)

**Flags** are persistent attributes that define the innate capabilities of a role or player.
They are managed via: `/player set_flag <member> <flag> <value>`.

> **Note:** Temporary effects like *Silenced*, *Paralyzed*, or *Protected* are **no longer flags**.
> They are now managed through the **Status Engine** (`/effects apply`).

---

## ⚙️ Core Mechanics

These flags affect the base game operation: voting, lynching, and action permissions.

| Flag | Type | Aliases | Logic Location | Description |
| :--- | :--- | :--- | :--- | :--- |
| **`day_act`** | `bool` | — | `cogs/actions.py` | Allows the player to use `/act` during the **DAY** phase. |
| **`night_act`** | `bool` | — | `cogs/actions.py` | Allows the player to use `/act` during the **NIGHT** phase. |
| **`hidden_vote`** | `bool` | `incognito`<br>`hidden` | `core/votes.py` | The player's vote appears as anonymous (glitched text) in public tallies (`/votes`). |
| **`voting_boost`** | `int` | `vote_boost`<br>`vote_bonus` | `status/engine.py` | Adds a fixed integer value to the vote weight. (e.g., `1` → Vote worth 2.0). |
| **`double_vote`** | `bool` | `mayor` | `status/engine.py` | Multiplies the total vote weight by **x2**. (Applied after boosts). |
| **`lynch_plus`** | `int` | `lynch_resistance`<br>`needs_extra_votes` | `core/votes.py` | Increases the threshold required to lynch this player (Base Threshold + `lynch_plus`). |

---

## 🌕 Expansion: Persona 3

These flags activate mechanics specific to the *The Dark Hour* expansion.

| Flag | Type | Aliases | Logic Location | Description |
| :--- | :--- | :--- | :--- | :--- |
| **`arcana`** | `bool` | `arcano` | `expansions/persona.py` | Marks the player as an **Arcana Bearer**. If alive, they count towards Nyx's **Apocalypse Clock**. |
| **`sees`** | `bool` | `sees_member` | `expansions/persona.py` | Marks the player as a **SEES** member. If targeted by an ability, it triggers the Oracles' **Radar**. |
| **`oracle`** | `bool` | `oraculo`<br>`radar` | `expansions/persona.py` | Grants **Navigator** capabilities. The player receives Radar notifications (real-time) and the Tactical Log (dawn). |

---

## 📝 Data Types

The `/player set_flag` command attempts to automatically convert input:

* **`bool`**: Accepts `true`, `on`, `yes`, `1` or `false`, `off`, `no`, `0`.
* **`int`**: Any integer number.
* **`str`**: Free text (stored as-is).