from __future__ import annotations
import discord
import random
import os
from typing import List
from . import Expansion, register
from ..status import Status, register as register_status
from ..status import engine as SE

# ==============================================================================
#  PERSONA 3 EXPANSION
# ==============================================================================

@register("persona3")
@register("p3")
class PersonaExpansion(Expansion):
    name = "p3"
    
    _daily_nyx_msg: str = ""
    # --- EASTER EGGS ---
    
    memes = {
        "mass destruction": "🎺 BABY BABY BABY BABY BABY... YEEEEAH! \nhttps://www.youtube.com/watch?v=C9faUEyNfqA",
        "disturbing the peace": "🎶 LOOK INTO MY EYES! \nhttps://www.youtube.com/watch?v=33yKDWb3Gbg",
        "disturbing the piece": "🎶 LOOK INTO MY EYES! \nhttps://www.youtube.com/watch?v=33yKDWb3Gbg",
        "junpei": "Junpei Ace Detective? More like **Stupei Ace Defective**.",
        "marin karin": "🧊 *Mitsuru intenta usar Marin Karin...* ¡Falló! (Como siempre).",
        "akihiko": "💪 Did you see that, Shinji?!",
        "protein": "💪 I've been waiting for this!",
        "the enemy": "😱 *Gasp!* The enemy!",
        "toaster": "🤖 No soy una tostadora. Soy un arma anti-sombras de última generación.\n*♪ Burn my bread... ♪*",
        "tostadora": "🤖 No soy una tostadora. Soy un arma anti-sombras de última generación.\n*♪ Burn my bread... ♪*",
        "tartarus": "😩 ¿Otra vez a subir escaleras? *Sigh...*",
        "nyx": "The Arcana is the means by which all is revealed...",
        "tanaka": "🎶 Anata no, terebi ni, Jika-netto Tanaka~ 🎶\n💰 *¡Amazing Commodities!*",
    }

    # --- NARRATIVE SKELETON ---
    # Map: Alive Arcanas -> Flavor Text
    NYX_TIMELINE = {
        13: "El cielo está tranquilo. La vida cotidiana continúa ignorante del destino.",
        12: "La primera campana ha sonado. Una sombra se proyecta sobre la ciudad.",
        11: "La luna comienza a teñirse de un verde enfermizo.",
        10: "Susurros en la oscuridad... La gente empieza a olvidar sus sueños.",
        9:  "La apatía se extiende como una plaga silenciosa.",
        8:  "Las sombras se alargan. El Sello se debilita visiblemente.",
        7:  "Mitad del camino. La balanza se inclina hacia la noche eterna.",
        6:  "El aire se vuelve pesado. Respirar cuesta cada vez más.",
        5:  "El cielo se desgarra. Figuras ominosas observan desde las alturas.",
        4:  "La cordura de la humanidad pende de un hilo.",
        3:  "Tres pilares restantes. El rugido de Nyx es ensordecedor.",
        2:  "La desesperación es absoluta. Solo queda rezar... o luchar.",
        1:  "El último sello. La Muerte está llamando a la puerta.",
        0:  "LA HORA OSCURA ETERNA HA COMENZADO. NYX HA DESCENDIDO."
    }

    # --------------------------------------------------------------------------
    #  PHASE HOOKS
    # --------------------------------------------------------------------------
    
    async def on_phase_change(self, guild: discord.Guild, game_state, new_phase: str):
        # Local imports to break the cycle
        from ..core.infra import get_infra

        if new_phase == "day":
            await self._send_fuuka_log(guild, game_state)
            await self._trigger_nyx_effects(guild, game_state)

        # Reaper Logic: Night 4
        if new_phase == "night" and game_state.current_day_number == 4:
            reaper_is_alive = False
            for p in getattr(game_state, "players", {}).values():
                # Check canonical role name "Reaper"
                if p.get("role") == "Reaper" and p.get("alive", True):
                    reaper_is_alive = True
                    break
            
            if reaper_is_alive:
                infra = get_infra(guild.id)
                ch_id = (infra.get("channels") or {}).get("game")
                if ch_id:
                    ch = guild.get_channel(ch_id)
                    if ch:
                        await ch.send("⛓️ **Se escuchan cadenas arrastrándose en la oscuridad...** 💀")

    def banner_for_day(self, game_state):
        count = self._count_arcanas(game_state, alive_only=True)
        flavor = self.NYX_TIMELINE.get(count, "El fin se acerca inexorablemente...")
        
        msg = (
            f"🌑 **La Hora Oscura se aproxima...**\n"
            f"# ⏳ Faltan **{count}** horas para el Apocalipsis.\n\n"
            f"> *\"{flavor}\"*"
        )
        
        # Append entropy report if available
        if self._daily_nyx_msg:
            msg += f"\n\n{self._daily_nyx_msg}"
            self._daily_nyx_msg = ""
            
        img_path = self._find_image_for_count(count)
        return {
            "content": msg,
            "file_path": img_path
        }

    def banner_for_night(self, game_state):
        # Usamos la misma lógica para mostrar el reloj y la cuenta atrás actualizada
        return self.banner_for_day(game_state)

    def _find_image_for_count(self, count: int) -> str | None:
        """
        Locate the countdown image.
        Target directory: cognitas/expansions/assets/p3/
        """
        # Build path relative to THIS file (persona3.py)
        base_dir = os.path.join(os.path.dirname(__file__), "assets", "p3")
        
        # Try multiple formats and filenames
        for ext in [".jpg", ".png", ".jpeg", ".gif"]:
            candidates = [
                f"p3_hour_{count}{ext}", 
                f"hour_{count}{ext}", 
                f"{count}{ext}"
            ]
            for fname in candidates:
                full = os.path.join(base_dir, fname)
                if os.path.exists(full):
                    return full
        return None

    def get_status_lines(self, game_state) -> list[str]:
        c = self._count_arcanas(game_state, alive_only=True)
        return [f"**Arcana Count:** {c}"]

    # --------------------------------------------------------------------------
    #  ACTION HOOKS
    # --------------------------------------------------------------------------

    async def on_action_commit(self, interaction: discord.Interaction, game_state, actor_uid: str, target_uid: str | None, action_data: dict) -> None:
        from ..core.players import send_to_player  # Local import

        if not target_uid: return

        players = getattr(game_state, "players", {})
        target = players.get(target_uid)
        
        # 1. Is target SEES?
        if not target or not target.get("flags", {}).get("sees", False):
            return

        # 2. Notify Oracles (exclude self-target)
        oracles = self._get_active_oracles(game_state, exclude_uid=actor_uid)
        if not oracles:
            return

        target_name = target.get("role", "Unknown role")
        msg = f"📡 **[ORACLE]** Anomalía detectada: Habilidad usada contra **{target_name}**."

        for oracle_uid in oracles:
            await send_to_player(interaction.guild, oracle_uid, msg)

    # --------------------------------------------------------------------------
    #  NYX LOGIC
    # --------------------------------------------------------------------------

    async def _trigger_nyx_effects(self, guild: discord.Guild, game_state):
        from ..core.players import send_to_player  # Local import

        self._daily_nyx_msg = ""
        alive_arcanas = self._count_arcanas(game_state, alive_only=True)
        total_arcanas = self._count_arcanas(game_state, alive_only=False)
        dead_arcanas = total_arcanas - alive_arcanas
        
        target_count = 2
        status_name = None
        filter_flag = None
        flavour_text = ""

        # Determine Phase thresholds
        if dead_arcanas >= 6:
            status_name = "Confusion"
            filter_flag = None # Any target
            flavour_text = "🌀 **Fase Tenebris:** La desesperación nubla las mentes..."
        elif dead_arcanas >= 4:
            status_name = "Drowsiness"
            filter_flag = "night_act" # Only those active at night
            flavour_text = "💤 **Fase Apogeo:** La Apatía consume la voluntad..."
        elif dead_arcanas >= 1:
            status_name = "Paralyzed"
            filter_flag = "day_act" # Only those active during day (vote or skill)
            flavour_text = "⛓️ **Fase Umbra:** El miedo paraliza los cuerpos..."
        else:
            return # Phase 0

        # Select candidates
        candidates = []
        for uid, p in game_state.players.items():
            if not p.get("alive", True): continue
            
            if filter_flag:
                flags = p.get("flags", {})
                if flags.get(filter_flag, False):
                    candidates.append(uid)
            else:
                candidates.append(uid)

        if not candidates: return

        # Pick random victims
        victims = random.sample(candidates, min(len(candidates), target_count))
        
        for uid in victims:
            SE.apply(game_state, uid, status_name, source="Nyx Global")
            await send_to_player(guild, uid, f"💀 **La influencia de Nyx te alcanza:** {flavour_text}")

        self._daily_nyx_msg = (
            f"{flavour_text}\n"
            f"**{len(victims)}** personas han sucumbido al efecto: **{status_name}**."
        )

    # --------------------------------------------------------------------------
    #  DEATH HOOKS
    # --------------------------------------------------------------------------

    async def on_player_death(self, guild: discord.Guild, game_state, uid: str, reason: str):
        # 1. Nyx Inheritance Logic
        await self._handle_nyx_death(guild, game_state, uid, reason)

    async def _handle_nyx_death(self, guild: discord.Guild, game_state, uid: str, reason: str):
        from ..core.infra import get_infra  # Local import

        player = game_state.players.get(uid)
        if not player: return

        role = player.get("role", "")
        if role != "Nyx": return

        # Verify Phase (< 3)
        dead_arcanas = self._count_arcanas(game_state, alive_only=False) - self._count_arcanas(game_state, alive_only=True)
        
        # Phase 3 starts at 6 dead. If >= 6, Nyx dies for real.
        if dead_arcanas >= 6:
            return 

        # Reveal Ryoji (False Reveal)
        infra = get_infra(guild.id)
        game_ch_id = (infra.get("channels") or {}).get("game")
        if game_ch_id:
            ch = guild.get_channel(game_ch_id)
            if ch:
                await ch.send(
                    "🎭 **¡Revelación!**\n"
                    "El cuerpo cae inerte, pero algo no encaja...\n"
                    "La ficha revela: **Ryoji Mochizuki** (Independiente).\n"
                    "*La Muerte no puede morir, solo cambiar de envase...*"
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
        from ..core import actions as act_core       # Local import
        from ..core.players import send_to_player    # Local import

        # We need Night (N-1)
        prev_night_num = max(1, game_state.current_day_number - 1)
        actor_uids = act_core.acted_uids("night", prev_night_num)
        
        oracles = self._get_active_oracles(game_state)
        if not oracles: return

        if not actor_uids:
            msg = f"📡 **[ORACLE] Registro Táctico — Noche {prev_night_num}**\n*No se detectó actividad anoche.*"
        else:
            names = []
            for uid in actor_uids:
                p = game_state.players.get(uid, {})
                names.append(p.get("name") or p.get("alias") or "???")
            
            list_str = ", ".join(names)
            msg = (
                f"📡 **[ORACLE] Registro Táctico — Noche {prev_night_num}**\n"
                f"Se detectaron firmas energéticas de los siguientes agentes:\n"
                f"`{list_str}`"
            )

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