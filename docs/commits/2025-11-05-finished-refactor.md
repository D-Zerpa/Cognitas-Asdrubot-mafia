# Asdrubot 3.0‑D — Audit & Refactor Summary

> Change log and adoption guide after the full audit (core, cogs, status, expansions).  
> **All prose, code, and comments in English.**

---

## 🧭 Executive Summary

- Centralized **action gating** (day/night/vote) around `StatusEngine`.
- Introduced `core/actions.enqueue_action(...)` as a **single source of truth** for recording actions.
- **Unified block messages** exposed via `status` package (extensible by expansions).
- Corrected **status semantics**: `Jailed` blocks voting; `Sanctioned` stacks properly.
- The **expansion registry** is now a **module-level API** (decorators `@register(...)` unchanged).

---

## 📦 Key Changes

### 1) Unified gating and coherent messaging

- `/act` (and any other action entry point) should go through a **homogeneous gate**:
  ```python
  # cogs/actions.py
  async def _gate_action(ctx, game, actor_uid, action_kind: str, target_uid=None, public=False):
      chk = SE.check_action(game, actor_uid, action_kind, target_uid)
      if not chk.get("allowed", True):
          reason = (chk.get("reason") or "").strip()
          msg = SE.get_block_message(reason)  # centralized, extensible
          return {"ok": False, "msg": msg, "ephemeral": not public, "redirect_to": None}
      return {"ok": True, "msg": None, "ephemeral": False, "redirect_to": chk.get("redirect_to")}
  ```

- **Block messages** centralized in `cognitas/status/__init__.py`:
  ```python
  BLOCK_MESSAGES = {
      "blocked_by:Jailed": "You're jailed and can't act right now.",
      "blocked_by:Sanctioned": "You are sanctioned and can't vote right now.",
      "blocked_by:Paralyzed": "You're paralyzed and can't use day abilities.",
      "blocked_by:Drowsiness": "You're drowsy and can't use night abilities.",
  }

  def get_block_message(reason: str) -> str: ...
  def register_block_messages(extra: dict[str, str]) -> None: ...
  ```
  > Expansions can add/override messages with `register_block_messages({...})`.

---

### 2) Single source of truth for recording actions

- New helper in `core/actions.py`:
  ```python
  def enqueue_action(
      game,
      actor_uid: str,
      action_kind: str,               # "day_action" | "night_action"
      target_uid: Optional[str] = None,
      payload: Optional[Dict[str, Any]] = None,  # {"action": "protect", "note": "..."}
      number: Optional[int] = None,
      action_name: str = "act",
      *,
      replace: bool = True,           # allow overwrite on re-submit
      bypass_gate: bool = False,      # only for system-level actions
  ) -> Dict[str, Any]:
      """
      Inserts a canonical action record under {phase_store["<N>"]["<uid>"] = record}.
      Returns {"ok": True, "number": int, "record": {...}, "replaced": bool} or {"ok": False, "reason": "..."}.
      """
  ```

- The **cog** no longer writes directly to `state.day_actions/night_actions`; it uses `enqueue_action(...)` and confirms to the user:
  ```python
  res = act_core.enqueue_action(...)
  verb = "updated" if res.get("replaced") else "registered"
  await ctx.reply(f"✅ Action {verb} for **{phase_norm.title()} {number}**.", ephemeral=not public)
  ```

---

### 3) Status semantics corrected

- **Paralyzed**: blocks **day actions** (`blocks={"day_action": True}`).
- **Drowsiness**: blocks **night actions** (`blocks={"night_action": True}`).
- **Jailed**: blocks **voting and actions**:
  ```python
  blocks = {"day_action": True, "night_action": True, "vote": True}
  ```
- **Sanctioned**: true stacking (vote weight goes 1.0 → 0.5 → 0.0):
  ```python
  stack_policy = "multiple"
  vote_weight_delta = -0.5
  ```

> `compute_vote_weight(game, uid, base=1.0)` sums all active deltas; the vote gate uses `SE.check_action(..., "vote")`.

---

### 4) Module‑level expansion registry

- `cognitas/expansions/__init__.py` now exposes:
  ```python
  class Expansion: ...
  def register(name: str) -> Callable[[Type[Expansion]], Type[Expansion]]: ...
  def get_registered(profile: str): ...
  # (optional) def list_registered_keys(): ...
  ```

- Expansions still decorate exactly the same:
  ```python
  from . import Expansion, register

  @register("smt")
  class SMT(Expansion): ...
  ```

- **Selective activation** (optional quality‑of‑life):
  ```python
  def activate_profiles(profiles: list[str]) -> None:
      # Guarded imports so only selected profiles get registered.
  ```

---

## 🔧 Migration (BREAKING CHANGE)

- Replace any `Expansion.get_registered(key)` calls with the **module‑level** API:
  ```python
  from cognitas.expansions import get_registered
  exp_cls = get_registered("smt")
  ```

- Ensure `/vote` (cog and core) uses:
  - `SE.check_action(game, voter_uid, "vote")`
  - `SE.compute_vote_weight(game, voter_uid, base=1.0)`

---

## 🧪 Offline Diagnosis (unified script)

Run the diagnosis script (no Discord needed) to validate gates, vote weights, and expansions:

```bash
python diagnosis_script.py
# produces diagnosis_report.json with PASS/FAIL per test
```

**Covered checks:**
- Vote weights: baseline, `Sanctioned` x1 (0.5), `Sanctioned` x2 (0.0).
- Gates: `Paralyzed` (day), `Drowsiness` (night), `Jailed` (vote/day/night).
- `enqueue_action`: happy path insertion and blocked path under a status.
- Expansions: module‑level API (`register/get_registered`), module imports, and registry entries.

> **Expected:** all tests **PASS** once the changes above are applied.

---

## ✅ Live Verification Checklist (save for later)

1. **/act (Day)**  
   - Player without `day_act` → rejected with coherent message.  
   - With **Paralyzed** → gated with message.  
   - Re‑submit `/act` → “Action updated…” feedback.

2. **/act (Night)**  
   - With **Drowsiness** → gated with message.  
   - **Confusion** (if present): confirm redirect and record to a different target.

3. **/vote**  
   - Baseline weight 1.0.  
   - `Sanctioned` x1 → 0.5; x2 → 0.0 (tally reflects weights).  
   - `Jailed` → cannot vote; coherent message.

4. **Logs & breakdown**  
   - `/actions logs` and `/actions breakdown` show correct names/UIDs with the new structure.

5. **Expansions**  
   - Activate a profile (e.g., `smt`) and verify only its hooks/messages are loaded.  
   - Switch profiles and confirm isolation of features.

---

## 🧱 Design Notes (for future iterations)

- **Defense‑in‑depth**: in addition to gating in cogs, `enqueue_action` re‑checks the gate.  
- **Extensible messaging**: expansions can register specific block messages via `register_block_messages`.  
- **System actions**: if an expansion needs to bypass statuses, use `bypass_gate=True` sparingly and document it.

---

## 📚 Reference Snippets

**Reason → message mapping (UX):**
```python
reason = res.get("reason") or ""
await ctx.reply(SE.get_block_message(reason), ephemeral=True)
```

**Vote weight with combined statuses:**
```python
w = max(0.0, SE.compute_vote_weight(game, uid, base=1.0))
```

**Activate expansion profiles (optional):**
```python
from cognitas.expansions import activate_profiles
activate_profiles(["base", "smt"])
```

---

## 📝 Glossary

- **Gate**: Pre‑check before executing/recording an action or vote (`SE.check_action`).  
- **Payload**: Action metadata (`{"action": "protect", "note": "..."}`).  
- **Phase store**: Structure `{ "<N>": { "<uid>": action_record } }` per phase.
