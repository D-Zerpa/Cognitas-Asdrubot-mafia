from __future__ import annotations
import discord
from typing import List

from . import Expansion, register
from ..core.players import send_to_player
from ..core import actions as act_core
from ..status import Status, register as register_status


_daily_nyx_msg: str = ""

# ==============================================================================
#  PERSONA 3 EXPANSION
# ==============================================================================

@register("persona3")
@register("p3")
class PersonaExpansion(Expansion):
    name = "persona3"

    # --------------------------------------------------------------------------
    #  PHASE HOOKS (Countdown & Fuuka's Log)
    # --------------------------------------------------------------------------
    
    async def on_phase_change(self, guild: discord.Guild, game_state, new_phase: str):
        """
        Triggered when phase shifts.
        - Day start: Send "Tactical Log" to Fuuka (Oracles).
        """
        if new_phase == "day":
            # Fuuka log
            await self._send_fuuka_log(guild, game_state)
            # Nyx's effect
            await self._trigger_nyx_effects(guild, game_state)

        if new_phase == "night" and game_state.current_day_number == 4:
             infra = get_infra(guild.id)
             ch_id = (infra.get("channels") or {}).get("game")
             if ch_id:
                 ch = guild.get_channel(ch_id)
                 if ch:
                     await ch.send("⛓️ **Se escuchan cadenas arrastrándose en la oscuridad...** 💀")


    def banner_for_day(self, game_state):
        """
        Morning announcement: Arcana countdown.
        """
        count = self._count_arcanas(game_state)
        return (
            f"🌑 **La Hora Oscura se aproxima...**\n"
            f"# ⏳ Faltan **{count}** horas para el Apocalipsis."
        )
        if self._daily_nyx_msg:
            msg += f"\n\n{self._daily_nyx_msg}"
            self._daily_nyx_msg = "" # Limpiar para mañana
            
        return msg

    def get_status_lines(self, game_state) -> list[str]:
        c = self._count_arcanas(game_state)
        return [f"**Arcana Count:** {c}"]

    # --------------------------------------------------------------------------
    #  ACTION HOOKS (Fuuka's Radar)
    # --------------------------------------------------------------------------

    async def on_action_commit(
        self, 
        interaction: discord.Interaction, 
        game_state, 
        actor_uid: str, 
        target_uid: str | None, 
        action_data: dict
    ) -> None:
        """
        Real-time Radar: If a SEES member is targeted, notify Oracles immediately.
        """
        if not target_uid: return

        players = getattr(game_state, "players", {})
        target = players.get(target_uid)
        
        # 1. Target is SEES?
        if not target or not target.get("flags", {}).get("sees", False):
            return

        # 2. Notify Oracles (exclude self-target)
        oracles = self._get_active_oracles(game_state, exclude_uid=actor_uid)
        if not oracles:
            return

        target_name = target.get("name", "Unknown")
        msg = f"📡 **[ORACLE]** Anomalía detectada: Habilidad usada contra **{target_name}**."

        for oracle_uid in oracles:
            await send_to_player(interaction.guild, oracle_uid, msg)

    # --------------------------------------------------------------------------
    #  NYX LOGIC
    # --------------------------------------------------------------------------

    async def _trigger_nyx_effects(self, guild: discord.Guild, game_state):
        """
        Calculates Nyx's phase based on DEAD Arcanas and applies global status effects.
        """
        self._daily_nyx_msg = "" # Reset
        
        alive_arcanas = self._count_arcanas(game_state, alive_only=True)
        total_arcanas = self._count_arcanas(game_state, alive_only=False)
        dead_arcanas = total_arcanas - alive_arcanas
        
        # Determine Phase thresholds
        # Phase 1: >= 1 dead -> Paralyzed (Targets Day Actors)
        # Phase 2: >= 4 dead -> Drowsiness (Targets Night Actors)
        # Phase 3: >= 6 dead -> Confusion (Targets Anyone)
        
        target_count = 2
        status_name = None
        filter_flag = None # Flag required on victim (day_act/night_act)
        flavour_text = ""

        if dead_arcanas >= 6:
            status_name = "Confusion"
            filter_flag = None # Any target
            flavour_text = "🌀 **Tenebris:** La desesperación nubla las mentes, la paranoia se hace presente..."
        elif dead_arcanas >= 4:
            status_name = "Drowsiness"
            filter_flag = "night_act" # Only those active at night
            flavour_text = "💤 **Apogeo:** La Apatía comienza a drenar la voluntad..."
        elif dead_arcanas >= 1:
            status_name = "Paralyzed"
            filter_flag = "day_act" # Only those active during day (vote or skill)
            flavour_text = "⛓️ **Umbra:** El primer sello ha sido roto, el instinto humano siente que algo va mal..."
        else:
            return # Phase 0, no effects

        # Select candidates
        candidates = []
        for uid, p in game_state.players.items():
            if not p.get("alive", True): continue
            
            # Apply filter (don't paralyze someone who can't act anyway)
            if filter_flag:
                flags = p.get("flags", {})
                if flags.get(filter_flag, False):
                    candidates.append(uid)
            else:
                candidates.append(uid)

        if not candidates:
            return

        # Pick random victims
        victims = random.sample(candidates, min(len(candidates), target_count))
        
        # Apply effects
        for uid in victims:
            # Apply status
            SE.apply(game_state, uid, status_name, source="Nyx Global")
            # Notify victim privately
            await send_to_player(guild, uid, f"💀 **La influencia de Nyx te alcanza:** {flavour_text}")

        # Configure public message for the daily banner
        # Note: We do not reveal names publicly to maintain mystery/chaos.
        self._daily_nyx_msg = (
            f"{flavour_text}\n"
            f"**{len(victims)}** personas han sucumbido al efecto: **{status_name}**."
        )


    # --------------------------------------------------------------------------
    #  INTERNAL HELPERS
    # --------------------------------------------------------------------------

    def _count_arcanas(self, game_state, alive_only: bool = True) -> int:
        c = 0
        for uid, p in getattr(game_state, "players", {}).items():
            is_arcana = p.get("flags", {}).get("arcana")
            is_alive = p.get("alive", True)
            
            if is_arcana:
                if alive_only and not is_alive:
                    continue
                c += 1
        return c

    def _get_active_oracles(self, game_state, exclude_uid: str | None = None) -> List[str]:
        """Return UIDs of alive players with 'oracle' flag."""
        out = []
        for uid, p in getattr(game_state, "players", {}).items():
            if uid == exclude_uid: continue
            if p.get("alive", True) and p.get("flags", {}).get("oracle", False):
                out.append(uid)
        return out

    async def _send_fuuka_log(self, guild: discord.Guild, game_state):
        """
        Fetch last night's actions and send a summary to Fuuka.
        """
        # We are at Day N start. We need Night (N-1).
        # Note: current_day_number was just incremented in start_day.
        prev_night_num = max(1, game_state.current_day_number - 1)
        
        # Get list of who acted last night
        actor_uids = act_core.acted_uids("night", prev_night_num)
        
        # Identify Oracles (Fuuka)
        oracles = self._get_active_oracles(game_state)
        if not oracles:
            return

        # Prepare Message
        if not actor_uids:
            msg = f"📡 **[ORACLE] Registro Táctico — Noche {prev_night_num}**\n*No se detectó actividad anoche.*"
        else:
            names = []
            for uid in actor_uids:
                p = game_state.players.get(uid, {})
                # Use name/alias/display_name
                names.append(p.get("name") or p.get("alias") or "???")
            
            list_str = ", ".join(names)
            msg = (
                f"📡 **[ORACLE] Registro Táctico — Noche {prev_night_num}**\n"
                f"Se detectaron firmas energéticas de los siguientes agentes:\n"
                f"`{list_str}`"
            )

        # Send to all oracles
        for oracle_uid in oracles:
            await send_to_player(guild, oracle_uid, msg)


# ==============================================================================
#  RESOURCE COUNTERS (Status System)
# ==============================================================================

@register_status("BulletAmmo")
class BulletAmmo(Status):
    name = "Bullet Ammo"
    type = "counter"       
    visibility = "hidden"  
    stack_policy = "add"
    default_duration = 999
    decrement_on = "always"

    def on_apply(self, game, uid, entry):
        return f"🔫 **Ammo Loaded:** You have {entry['stacks']} bullets."

@register_status("RoseCounter")
class RoseCounter(Status):
    name = "Roses"
    type = "counter"
    visibility = "hidden"
    stack_policy = "add"
    default_duration = 999
    decrement_on = "always"

    def on_apply(self, game, uid, entry):
        count = entry['stacks']
        msg = f"🌹 **Rose Obtained!** Total: {count}."
        if count >= 3:
            msg += "\n✨ **Tránsito Carmesí:** You can now enter the Graveyard."
        return msg

@register_status("RageCharge")
class RageCharge(Status):
    name = "Rage"
    type = "counter"
    visibility = "hidden"
    stack_policy = "add"
    default_duration = 999
    decrement_on = "always"

    def on_apply(self, game, uid, entry):
        return f"💢 **Rage Building...** Stack: {entry['stacks']}."

@register_status("AffinityCharge")
class AffinityCharge(Status):
    name = "Affinity"
    type = "counter"
    visibility = "hidden"
    stack_policy = "add"
    default_duration = 999
    decrement_on = "always"

    def on_apply(self, game, uid, entry):
        return f"🤝 **Affinity Deepens.** Stack: {entry['stacks']}."