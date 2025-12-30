from __future__ import annotations

import time
import logging
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..core.state import game
from ..core.storage import save_state
from ..core.logs import log_event  
from ..core import actions as act_core 
from ..status import engine as SE

log = logging.getLogger(__name__)

# ---------- Visual Helpers (UI in Spanish) ----------

def _label_from_uid(uid: str | None) -> str:
    if not uid:
        return "—"
    p = game.players.get(str(uid), {})
    return p.get("name") or p.get("alias") or f"<@{uid}>"

def _fmt_action_line(a: dict) -> str:
    """
    Format: • 🎯 **Target** | 📝 Note text (<t:time:R>)
    """
    # 1. Target visual (Bold)
    tgt_uid = a.get("target")
    if tgt_uid:
        target_label = f"**{_label_from_uid(tgt_uid)}**"
    else:
        target_label = "*Sí mismo / Ninguno*"

    # 2. Note (Only show if present)
    raw_note = (a.get("note") or "").strip()
    note_part = f" | 📝 {raw_note}" if raw_note else ""

    # 3. Time (Relative timestamp)
    at = a.get("at")
    time_part = f" (<t:{int(at)}:R>)" if at else ""

    return f"• 🎯 {target_label}{note_part}{time_part}"


async def _gate_action(ctx, game, actor_uid, action_kind: str, target_uid=None, public=False):
    """Checks if a status effect blocks the action."""
    chk = SE.check_action(game, actor_uid, action_kind, target_uid)
    if not chk.get("allowed", True):
        reason = (chk.get("reason") or "").strip()
        # Get localized message from status engine
        msg = SE.get_block_message(reason)
        return {"ok": False, "msg": msg, "ephemeral": not public, "redirect_to": None}
    return {"ok": True, "msg": None, "ephemeral": False, "redirect_to": chk.get("redirect_to")}


# ---------- Interaction Context Adapter ----------
class InteractionCtx:
    def __init__(self, interaction: discord.Interaction):
        self._i = interaction
        self.guild = interaction.guild
        self.bot = interaction.client
        self.channel = interaction.channel
        self.author = interaction.user
        self.message = None

    async def reply(self, content: str = None, **kwargs):
        try:
            if self._i.response.is_done():
                return await self._i.followup.send(content or "\u200b", **kwargs)
            else:
                return await self._i.response.send_message(content or "\u200b", **kwargs)
        except Exception:
            if self.channel:
                try:
                    return await self.channel.send(content or "\u200b", **kwargs)
                except Exception:
                    pass

    async def send(self, content: str = None, **kwargs):
        return await self.reply(content, **kwargs)


# =================================================================
#  A) USER COMMAND: /act   (phase-aware: day or night)
# =================================================================
class ActionsCog(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot

    @app_commands.command(name="act", description="Registrar tu acción para la fase actual (Día o Noche).")
    @app_commands.describe(
        target="Jugador objetivo (opcional)",
        note="Nota de texto libre sobre tu acción (opcional)",
        public="Publicar confirmación visible para todos (default: false)",
    )
    async def act(
        self, 
        interaction: discord.Interaction, 
        target: discord.Member | None = None, 
        note: str = "", 
        public: bool = False
    ):
        await interaction.response.defer(ephemeral=not public)
        ctx = InteractionCtx(interaction)

        # Automatically resolve phase
        phase = (getattr(game, "phase", "day") or "day").lower()
        if phase not in ("day", "night"):
            phase = "day"

        # Phase validation (must have active deadline)
        if phase == "night" and not getattr(game, "night_deadline_epoch", None):
            return await ctx.reply("❌ No es fase de **Noche**.", ephemeral=not public)
        if phase == "day" and not getattr(game, "day_deadline_epoch", None):
            return await ctx.reply("❌ No es fase de **Día**.", ephemeral=not public)

        actor_uid = str(interaction.user.id)
        players = getattr(game, "players", {}) or {}
        actor = players.get(actor_uid)
        
        # Player validation
        if not actor or not actor.get("alive", True):
            return await ctx.reply("❌ No estás registrado o no estás vivo.", ephemeral=not public)

        # Channel validation (Infra)
        role_ch_id = (actor.get("role_channel_id") if isinstance(actor, dict) else None)
        if role_ch_id and interaction.channel and interaction.channel.id != role_ch_id:
            # Allow admins to test from anywhere, restrict users
            if not interaction.user.guild_permissions.administrator:
                return await ctx.reply("⚠️ Usa el canal privado de tu rol para usar `/act`.", ephemeral=not public)

        # Flag validation (Role permissions)
        flags = actor.get("flags", {}) or {}
        needed_flag = "day_act" if phase == "day" else "night_act"
        if not bool(flags.get(needed_flag, False)):
            phase_lbl = "Día" if phase == "day" else "Noche"
            return await ctx.reply(f"⛔ No tienes permitido actuar durante el **{phase_lbl}**.", ephemeral=not public)

        # Target validation
        target_uid = str(target.id) if target else None
        if target_uid:
            t = players.get(target_uid)
            if not t:
                return await ctx.reply("❌ El objetivo no está registrado.", ephemeral=not public)
            # We allow acting on dead players (e.g. revivers), role logic decides validity.

        # Action type
        action_kind = "day_action" if phase == "day" else "night_action"

        # Status Gate (Check for Paralysis, etc.)
        gate = await _gate_action(ctx, game, actor_uid, action_kind, target_uid, public=public)
        if not gate["ok"]:
            # Gate msg is already localized by SE.get_block_message
            return await ctx.reply(f"⛔ {gate['msg']}", ephemeral=gate["ephemeral"])

        if gate.get("redirect_to"):
            target_uid = gate["redirect_to"]
            try:
                await ctx.reply("🌀 Sufres de Confusión... tu acción ha sido redirigida.", ephemeral=True)
            except Exception:
                pass

        # Determine cycle number
        phase_norm = "day" if phase == "day" else "night"
        number = act_core.current_cycle_number(phase_norm)

        # Clean note
        clean_note = (note or "").strip()
        if clean_note:
            log.info(f"[ACT] User {interaction.user} sent note: {clean_note}")

        # Enqueue Action (Core)
        res = act_core.enqueue_action(
            game=game,
            actor_uid=actor_uid,
            action_kind=action_kind,
            target_uid=target_uid,
            payload={
                "action": "act",
                "note": clean_note,
                "at": int(time.time()),
            },
            number=number,
        )

        if not res.get("ok", True):
            msg = SE.get_block_message(res.get("reason") or "")
            return await ctx.reply(msg or "❌ Acción rechazada.", ephemeral=not public)

        await save_state()

        # Expansion Hooks
        if getattr(game, "expansion", None):
            try:
                await game.expansion.on_action_commit(
                    interaction,
                    game, 
                    actor_uid, 
                    target_uid, 
                    res.get("record", {})
                )
            except Exception as e:
                log.error(f"Error in expansion action hook: {e}")

        # Audit Log (Admin Log)
        try:
            await log_event(
                self.bot,
                interaction.guild.id if interaction.guild else None,
                f"{phase_norm.upper()}_ACTION",
                actor_id=actor_uid,
                target_id=(target_uid or "None"),
                note=clean_note
            )
        except Exception:
            pass

        # Feedback to User
        verb = "actualizada" if res.get("replaced") else "registrada"
        phase_display = "Día" if phase == "day" else "Noche"
        await ctx.reply(f"✅ Acción {verb} para **{phase_display} {number}**.", ephemeral=not public)


# =================================================================
#  B) ADMIN GROUP: /actions logs | /actions list
# =================================================================
PHASE_CHOICES = [
    app_commands.Choice(name="auto", value="auto"),
    app_commands.Choice(name="day", value="day"),
    app_commands.Choice(name="night", value="night"),
]

def _resolve_phase(phase: Optional[str]) -> str:
    if (phase or "").lower() == "auto" or not phase:
        return (getattr(game, "phase", "day") or "day").lower()
    p = (phase or "").lower()
    return p if p in ("day", "night") else "night"


class ActionsAdminCog(commands.GroupCog, name="actions", description="Utilidades de Acciones (Admin)"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="logs", description="Ver logs: user=historial completo; number=Día/Noche específico.")
    @app_commands.describe(
        phase="Fase a inspeccionar (auto/day/night)",
        number="Número de Día/Noche (omitir para actual)",
        user="Filtrar por usuario",
        public="Hacer visible el reporte (default: false)",
    )
    @app_commands.choices(phase=PHASE_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def logs_cmd(
        self,
        interaction: discord.Interaction,
        phase: Optional[app_commands.Choice[str]] = None,
        number: Optional[int] = None,
        user: Optional[discord.Member] = None,
        public: bool = False,
    ):
        await interaction.response.defer(ephemeral=not public)
        ctx = InteractionCtx(interaction)

        p = _resolve_phase(phase.value if phase else None)
        phase_lbl = "Día" if p == "day" else "Noche"

        # A) User History (all cycles)
        if user is not None and number is None:
            uid = str(user.id)
            rows = act_core.get_user_logs_all(p, uid)
            title = f"Historial de Acciones ({phase_lbl}) — {user.display_name}"
            embed = discord.Embed(title=title, color=0x8E44AD)

            if not rows:
                embed.description = "ℹ️ No hay acciones registradas."
                return await ctx.reply(embed=embed, ephemeral=not public)

            by_num: dict[int, list[dict]] = {}
            for n, act in rows:
                by_num.setdefault(n, []).append(act)

            for n in sorted(by_num.keys()):
                acts = by_num[n]
                lines = [_fmt_action_line(a) for a in acts]
                embed.add_field(name=f"{phase_lbl} {n}", value=("\n".join(lines)[:1024] or "—"), inline=False)

            return await ctx.reply(embed=embed, ephemeral=not public)

        # B) Phase logs (specific or current cycle)
        n = number if number is not None else act_core.current_cycle_number(p)
        uid = str(user.id) if user else None
        rows = act_core.get_logs(p, n, uid)

        title = f"Logs de Acciones — {phase_lbl} {n}"
        embed = discord.Embed(title=title, color=0x8E44AD)

        if not rows:
            embed.description = "ℹ️ No hay acciones registradas en este ciclo."
            return await ctx.reply(embed=embed, ephemeral=not public)

        by_user: dict[str, list[dict]] = {}
        for r in rows:
            u = str(r.get("uid"))
            by_user.setdefault(u, []).append(r)

        for u, acts in by_user.items():
            lines = [_fmt_action_line(a) for a in acts]
            name = _label_from_uid(u)
            embed.add_field(name=f"👤 {name}", value=("\n".join(lines)[:1024] or "—"), inline=False)

        await ctx.reply(embed=embed, ephemeral=not public)

    @app_commands.command(name="breakdown", description="Resumen de quién ha actuado y quién falta.")
    @app_commands.choices(phase=PHASE_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def list_cmd(
        self,
        interaction: discord.Interaction,
        phase: Optional[app_commands.Choice[str]] = None,
        number: Optional[int] = None,
        public: bool = False,
    ):
        await interaction.response.defer(ephemeral=not public)
        ctx = InteractionCtx(interaction)

        p = _resolve_phase(phase.value if phase else None)
        n = number if number is not None else act_core.current_cycle_number(p)

        # Get data sets
        can_act = set(act_core.actors_for_phase(p))
        acted = set(act_core.acted_uids(p, n))

        # --- STATUS FILTERING ---
        # Split 'missing' candidates into 'Real Pending' and 'Blocked'
        candidates_missing = sorted(can_act - acted)
        
        pending_real = []
        blocked = []
        
        # Determine the action kind to check (day_action / night_action)
        action_kind = "day_action" if p == "day" else "night_action"

        for uid in candidates_missing:
            # Check status without specific target (just ability to act)
            chk = SE.check_action(game, uid, action_kind, target_uid=None)
            
            if not chk.get("allowed", True):
                # System says they can't act -> Blocked
                blocked.append(uid)
            else:
                # Can act and hasn't yet -> Pending
                pending_real.append(uid)

        # Those who already acted (simple intersection)
        acted_sorted = sorted(acted & can_act)

        # Format helper
        def fmt_names(uids: List[str]) -> str:
            if not uids: return "—"
            names = []
            for uid in uids[:30]: 
                pdata = game.players.get(uid, {})
                label = pdata.get("name") or pdata.get("alias") or f"<@{uid}>"
                names.append(f"`{label}`")
            if len(uids) > 30: names.append(f"… (+{len(uids)-30} más)")
            return ", ".join(names)

        phase_lbl = "Día" if p == "day" else "Noche"
        
        # Build Embed
        desc = (
            f"**Total Habilitados:** {len(can_act)} | **Listos:** {len(acted_sorted)} | "
            f"**Pendientes:** {len(pending_real)}"
        )
        if blocked:
            desc += f" | **Bloqueados:** {len(blocked)}"

        embed = discord.Embed(
            title=f"Resumen de Acciones — {phase_lbl} {n}",
            description=desc,
            color=0x2C3E50 if p == "night" else 0x3498DB
        )
        embed.add_field(name=f"✅ Han actuado ({len(acted_sorted)})", value=fmt_names(acted_sorted), inline=False)
        embed.add_field(name=f"⏳ Pendientes ({len(pending_real)})", value=fmt_names(pending_real), inline=False)
        
        if blocked:
            embed.add_field(name=f"⛔ Bloqueados ({len(blocked)})", value=fmt_names(blocked), inline=False)

        await ctx.reply(embed=embed, ephemeral=not public)


async def setup(bot: commands.Bot):
    await bot.add_cog(ActionsCog(bot))
    await bot.add_cog(ActionsAdminCog(bot))