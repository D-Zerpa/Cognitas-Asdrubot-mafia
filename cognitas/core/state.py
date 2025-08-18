import time
from math import ceil

class GameState:
    def __init__(self):
        self.players = {}             # { uid_str: {nick, role, channel_id, alive, flags, effects} }
        self.votes = {}               # { voter_uid_str: target_uid_str }
        self.roles = {}               # loaded from roles.json
        self.day_channel_id = None
        self.current_day_number = 1
        self.day_deadline_epoch = None
        self.day_timer_task = None    # asyncio.Task

    # ---------- role & player access ----------
    def role_of(self, uid: str) -> dict:
        code = self.players[uid]["role"]
        return self.roles.get(code, {})

    def role_defaults(self, uid: str) -> dict:
        return self.role_of(uid).get("defaults", {})

    def effects_of(self, uid: str) -> list:
        return self.players[uid].get("effects", [])

    def flags_of(self, uid: str) -> dict:
        return self.players[uid].get("flags", {})

    def alive_ids(self):
        return [uid for uid, p in self.players.items() if p.get("alive", True)]

    def base_threshold(self):
        return ceil(len(self.alive_ids()) / 2)

    # ---------- effect math ----------
    def _expired(self, eff: dict) -> bool:
        exp = eff.get("expires_day")
        return exp is not None and exp < self.current_day_number

    def vote_weight(self, uid: str) -> int:
        p = self.players.get(uid, {})
        if not p or not p.get("alive", True):
            return 0
        fl = self.flags_of(uid)
        if fl.get("silenced", False) or fl.get("absent", False):
            return 0
        base = int(self.role_defaults(uid).get("vote_weight_base", 1))
        boosts = [
            int(e.get("value", 0))
            for e in self.effects_of(uid)
            if e.get("type") == "vote_boost" and not self._expired(e)
        ]
        return max([base] + boosts) if boosts else base

    def lynch_delta(self, uid: str) -> int:
        d = 0
        dfl = self.role_defaults(uid)
        # Zeno (+1 once)
        if dfl.get("lynch_bonus_once", 0) == 1:
            consumed = any(e.get("type") == "zenon_bonus_consumed" for e in self.effects_of(uid))
            if not consumed:
                d += 1
        # Plotinus (-1 while marked)
        marked = any(e.get("type") == "plotino_mark" and not self._expired(e) for e in self.effects_of(uid))
        if marked:
            d -= 1
        return d

    def required_for_target(self, obj_uid: str) -> int:
        o = self.players.get(obj_uid, {})
        if not o or not o.get("alive", True):
            return 9999
        if self.flags_of(obj_uid).get("absent", False):
            return 9999
        req = self.base_threshold() + self.lynch_delta(obj_uid)
        return max(1, req)

    def totals_per_target(self) -> dict:
        totals = {}
        for voter_uid, target_uid in self.votes.items():
            if not target_uid or target_uid not in self.players:
                continue
            if not self.players[target_uid].get("alive", True):
                continue
            if self.flags_of(target_uid).get("absent", False):
                continue
            w = self.vote_weight(voter_uid)
            if w <= 0:
                continue
            totals[target_uid] = totals.get(target_uid, 0) + w
        return totals

# Singleton game state
game = GameState()