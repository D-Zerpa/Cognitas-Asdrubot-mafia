import time
from math import ceil

class GameState:
    def __init__(self):
        # --- Core runtime state ---
        self.players = {}               # { uid: {nick, role, channel_id, alive, flags, effects} }
        self.votes = {}                 # { voter_uid: target_uid }
        self.roles = {}                 # loaded from roles.json

        # --- Day phase ---
        self.day_channel_id = None      # int | None
        self.current_day_number = 1     # int
        self.day_deadline_epoch = None  # int | None (epoch seconds)
        self.day_timer_task = None      # asyncio.Task | None
        self.end_day_votes = set()   # uids (str) de vivos que pidieron cerrar el Día
        
        # --- Night phase ---
        self.night_channel_id = None        # where !act is allowed (optional)
        self.night_deadline_epoch = None    # epoch seconds
        self.night_timer_task = None        # asyncio.Task | None
        self.next_day_channel_id = None     # which channel to open at dawn

        # --- Night action log (append-only) ---
        # list of dicts: {day, ts_epoch, actor_uid, target_uid, note}
        self.night_actions = []

        # --- Server-configurable channels (set via admin cmds) ---
        self.admin_log_channel_id = None    # where admin logs go
        self.default_day_channel_id = None  # default Day channel

        # --- Game lifecycle ---
        self.game_over = False              # block new phases when True

    # -------------- Helpers  --------------
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

    # ----- voting math -----
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

    def add_unique_effect(self, uid: str, effect_type: str, *, value: int = 0, expires_day: int | None = None) -> bool:
        """Add an effect if not already present. Returns True if added."""
        p = self.players.get(uid)
        if not p:
            return False
        effs = p.setdefault("effects", [])
        for e in effs:
            if e.get("type") == effect_type and (e.get("expires_day") == expires_day):
                return False
        effs.append({"type": effect_type, "value": value, "expires_day": expires_day})
        return True

    def remove_effect(self, uid: str, effect_type: str) -> bool:
        """Remove all effects of given type. Returns True if any removed."""
        p = self.players.get(uid)
        if not p:
            return False
        before = len(p.get("effects", []))
        p["effects"] = [e for e in p.get("effects", []) if e.get("type") != effect_type]
        return len(p["effects"]) != before

# Singleton game state
game = GameState()
