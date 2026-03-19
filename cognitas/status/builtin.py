from __future__ import annotations
from . import Status, register
from .engine import pick_random_alive

# Helper to avoid circular imports if _kill_player logic is needed locally
async def _kill_player(game, uid: str, reason: str):
    p = game.players.get(uid)
    if p:
        p["alive"] = False
        p["death_reason"] = reason

# ---------- Paralyzed (Parálisis) ----------
@register("Paralyzed")
class Paralyzed(Status):
    name = "Paralyzed"; type = "debuff"; visibility = "private"
    stack_policy = "refresh"; default_duration = 1; decrement_on = "night"
    blocks = {"day_action": True}

    def on_apply(self, game, uid, entry): return f"<@{uid}> ¡Sufres de **Parálisis**!"
    def on_expire(self, game, uid, entry): return f"<@{uid}> Te has recuperado de la **Parálisis**."

# ---------- Drowsiness (Letárgico) ----------
@register("Drowsiness")
class Drowsiness(Status):
    name = "Drowsiness"; type = "debuff"; visibility = "private"
    stack_policy = "refresh"; default_duration = 1; decrement_on = "day"
    blocks = {"night_action": True}

    def on_apply(self, game, uid, entry): return f"<@{uid}> ¡Te sientes **Letárgico**!"
    def on_expire(self, game, uid, entry): return f"<@{uid}> Ya no te sientes **Letárgico**."

# ---------- Confusion (Confusión) ----------
@register("Confusion")
class Confusion(Status):
    name = "Confusion"; type = "debuff"; visibility = "private"
    stack_policy = "refresh"; default_duration = 2; decrement_on = "always"

    def on_apply(self, game, uid, entry): return f"<@{uid}> ¡Sufres de **Confusión**!"
    def on_expire(self, game, uid, entry): return f"<@{uid}> Tu mente se aclara. Ha cesado la **Confusión**."

    def on_action(self, game, uid, entry, action_kind, target_uid):
        # 50% chance to redirect
        import random
        if target_uid and random.random() < 0.5:
            new_target = pick_random_alive(game, exclude=uid)
            if new_target:
                return {"action_allowed": True, "reason": "Confusion", "redirect_to": new_target}
        return {"action_allowed": True, "reason": None, "redirect_to": None}

# ---------- Silenced (Silencio) ----------
@register("Silenced")
class Silenced(Status):
    name = "Silenced"; type = "debuff"; visibility = "public"
    stack_policy = "refresh"; default_duration = 1; decrement_on = "day"
    blocks = {"vote": True, "speak": True}

    def on_apply(self, game, uid, entry): return f"<@{uid}> ha sido reducido al **Silencio**."
    def on_expire(self, game, uid, entry): return f"<@{uid}> ha recuperado el habla (Fin del **Silencio**)."

# ---------- Wounded (Herido) ----------
@register("Wounded")
class Wounded(Status):
    name = "Wounded"; type = "debuff"; visibility = "private"
    stack_policy = "add"; default_duration = 1; decrement_on = "always"
    blocks = {"day_action": True, "night_action": True}

    def on_apply(self, game, uid, entry): 
        return f"<@{uid}> ¡Estás **Herido**! Necesitas ser curado antes de que acabe el día."

    def on_tick(self, game, uid, entry, phase):
        # If this tick is day-start and still wounded -> die
        if phase == "day" and entry.get("remaining", 1) <= 1:
            _kill_player(game, uid, reason="Heridas (sin sanar)")
            return f"<@{uid}> sucumbió a sus heridas."
        return None

    def on_expire(self, game, uid, entry): return f"<@{uid}> ¡Tus heridas han sanado! Ya no estás **Herido**."

# ---------- Poisoned (Envenenado - No estaba en tu lista pero es standard) ----------
@register("Poisoned")
class Poisoned(Status):
    name = "Poisoned"; type = "debuff"; visibility = "private"
    stack_policy = "add"; default_duration = 1 ; decrement_on = "always"

    def on_apply(self, game, uid, entry):
        stacks = entry.get("stacks", 1)
        if stacks >= 2:
            _kill_player(game, uid, reason="Veneno x2")
            return f"<@{uid}> Moriste por una dosis letal de veneno."
        return f"<@{uid}> ¡Estás Envenenado! Necesitas ser curado."

    def on_tick(self, game, uid, entry, phase):
        if phase == "day" and entry.get("remaining", 1) <= 1:
            _kill_player(game, uid, reason="Envenenamiento")
            return f"<@{uid}> murió a causa del veneno."
        return None

    def on_expire(self, game, uid, entry): return f"<@{uid}> Te has curado del veneno."
