from __future__ import annotations
from . import Status, register
from .engine import pick_random_alive

# ---------- Paralyzed ----------
@register("Paralyzed")
class Paralyzed(Status):
    name = "Paralyzed"; type = "debuff"; visibility = "private"
    stack_policy = "refresh"; default_duration = 1; decrement_on = "night"
    # blocks day ability; your /act can pass action_kind="day_action"
    blocks = {"day_action": True}

    def on_apply(self, game, uid, entry): return f"<@{uid}> You've been Paralyzed!"
    def on_expire(self, game, uid, entry): return f"<@{uid}> You recovered from paralysis."

# ---------- Drowsiness ----------
@register("Drowsiness")
class Drowsiness(Status):
    name = "Drowsiness"; type = "debuff"; visibility = "private"
    stack_policy = "refresh"; default_duration = 1; decrement_on = "day"
    blocks = {"night_action": True}

    def on_apply(self, game, uid, entry): return f"<@{uid}> You've been affected by Drowsiness!"
    def on_expire(self, game, uid, entry): return f"<@{uid}> You recovered from drowsiness."

# ---------- Confusion ----------
@register("Confusion")
class Confusion(Status):
    name = "Confusion"; type = "debuff"; visibility = "private"
    stack_policy = "refresh"; default_duration = 2; decrement_on = "always"

    def on_apply(self, game, uid, entry): return f"<@{uid}> You've been Confused!"
    def on_expire(self, game, uid, entry): return f"<@{uid}> You recovered from confusion."

    def on_action(self, game, uid, entry, action_kind, target_uid):
        # Only affects abilities; not voting
        if action_kind not in ("day_action", "night_action"):
            return {"action_allowed": True, "reason": None, "redirect_to": None}
        # coin toss: True=heads (ok), False=tails (redirect)
        import random
        if random.random() < 0.5:
            # tails -> redirect to random alive (not self)
            new_tgt = pick_random_alive(game, exclude=uid)
            if new_tgt:
                return {"action_allowed": True, "reason": None, "redirect_to": new_tgt}
        # heads -> proceed as chosen
        return {"action_allowed": True, "reason": None, "redirect_to": None}

# ---------- Jailed ----------
@register("Jailed")
class Jailed(Status):
    name = "Jailed"; type = "debuff"; visibility = "private"
    stack_policy = "refresh"; default_duration = 2; decrement_on = "always"
    blocks = {"day_action": True, "night_action": True, "vote": True, "day_talk": True}

    def on_apply(self, game, uid, entry): return f"<@{uid}> You've been Jailed!"
    def on_expire(self, game, uid, entry): return f"<@{uid}> You're free again!"

# ---------- Silenced ----------
@register("Silenced")
class Silenced(Status):
    name = "Silenced"; type = "debuff"; visibility = "private"
    stack_policy = "refresh"; default_duration = 1; decrement_on = "night"
    # talking in day channel is policy-enforced in your cog; we flag a block here:
    blocks = {"day_talk": True}

    def on_apply(self, game, uid, entry): return f"<@{uid}> You've been Silenced!"
    def on_expire(self, game, uid, entry): return f"<@{uid}> You can speak again."

# ---------- Double vote (stacking adds weight) ----------
@register("DoubleVote")
class DoubleVote(Status):
    name = "Double vote"; type = "buff"; visibility = "private"
    stack_policy = "multiple"; default_duration = 1; decrement_on = "night"
    vote_weight_multiplier = 2.0  # base 1 -> 2; stacking adds more

    def on_apply(self, game, uid, entry): return f"<@{uid}> You've been blessed with double vote!"
    def on_expire(self, game, uid, entry): return f"<@{uid}> Your double vote expired."

# ---------- Sanctioned (stacking halves, then blocks) ----------
@register("Sanctioned")
class Sanctioned(Status):
    name = "Sanctioned"; type = "debuff"; visibility = "private"
    # stacks should accumulate to affect vote twice -> 0.0
    stack_policy = "multiple"
    default_duration = 1 ; decrement_on = "night"
    vote_weight_multiplier = 0.5

    def on_apply(self, game, uid, entry):
        stacks = entry.get("stacks", 1)
        if stacks >= 2:
            return f"<@{uid}> Your Sanction got worse, you can't vote!"
        return f"<@{uid}> You're Sanctioned, your vote counts as half!"

    def on_expire(self, game, uid, entry): return f"<@{uid}> Your Sanction was removed."

# ---------- Wounded ----------
@register("Wounded")
class Wounded(Status):
    name = "Wounded"; type = "debuff"; visibility = "private"
    stack_policy = "add"; default_duration = 2; decrement_on = "always"
    # Policy from spec:
    #  - one stack: can't vote
    #  - two stacks: die immediately
    #  - if not healed by next day start: die
    blocks = {"vote": True}  # at least one stack blocks voting

    def on_apply(self, game, uid, entry):
        stacks = entry.get("stacks", 1)
        if stacks >= 2:
            _kill_player(game, uid, reason="Wounded x2")
            return f"<@{uid}> Your Wound got worse, you died!"
        return f"<@{uid}> You're Wounded, you can't vote. Find a healer."

    def on_tick(self, game, uid, entry, phase):
        # If this tick is day-start and still wounded -> die
        if phase == "day" and entry.get("remaining", 1) <= 1:
            _kill_player(game, uid, reason="Wounded (not healed by dawn)")
            return f"<@{uid}> succumbed to their wounds."
        return None

    def on_expire(self, game, uid, entry): return f"<@{uid}> You're healthy again!"

# ---------- Poisoned ----------
@register("Poisoned")
class Poisoned(Status):
    name = "Poisoned"; type = "debuff"; visibility = "private"
    stack_policy = "add"; default_duration = 1 ; decrement_on = "always"

    def on_apply(self, game, uid, entry):
        stacks = entry.get("stacks", 1)
        if stacks >= 2:
            _kill_player(game, uid, reason="Poisoned x2")
            return f"<@{uid}> You died by poison. RIP."
        return f"<@{uid}> You're Poisoned. Find a healer."

    def on_tick(self, game, uid, entry, phase):
        # end of day (after one tick) -> die if still poisoned
        if phase == "day" and entry.get("remaining", 1) <= 1:
            _kill_player(game, uid, reason="Poisoned (not healed by end of day)")
            return f"<@{uid}> You died by poison. RIP."
        return None

    def on_expire(self, game, uid, entry): return f"<@{uid}> You're healthy again!"

# ---- helpers ----
def _kill_player(game, uid: str, *, reason: str):
    p = game.players.get(uid, {})
    p["alive"] = False
    p["death_reason"] = reason
