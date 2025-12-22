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

# ---------- Visual Helpers (New & Clean) ----------

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
        target_label = "*Self / None*"

    # 2. Note (Only show if present)
    raw_note = (a.get("note") or "").strip()
    note_part = f" | 📝 {raw_note}" if raw_note else ""

    # 3. Time (Relative timestamp)
    at = a.get("at")
    time_part = f" (<t:{int(at)}:R>)" if at else ""

    return f"• 🎯 {target_label}{note_part}{time_part}"


async def _gate_action(ctx, game, actor_uid, action_kind: str, target_uid=None, public=False):
    chk = SE.check_action(game, actor_uid, action_kind, target_uid)
    if not chk.get("allowed", True):
        reason = (chk.get("reason") or "").strip()
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

    @app_commands.command(name="act", description="Register your action for the current phase (day or night).")
    @app_commands.describe(
        target="Target player (optional)",
        note="Free text note about your action (optional)",
        public="Post a public acknowledgement instead of ephemeral (default: false)",
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

        # Resolve phase automatically
        phase = (getattr(game, "phase", "day") or "day").lower()
        if phase not in ("day", "night"):
            phase = "day"

        # Phase check (must have deadline)
        if phase == "night" and not getattr(game, "night_deadline_epoch", None):
            return await ctx.reply("It is not **Night** phase.", ephemeral=not public)
        if phase == "day" and not getattr(game, "day_deadline_epoch", None):
            return await ctx.reply("It is not **Day** phase.", ephemeral=not public)

        actor_uid = str(interaction.user.id)
        players = getattr(game, "players", {}) or {}
        actor = players.get(actor_uid)
        if not actor or not actor.get("alive", True):
            return await ctx.reply("You are not registered or you are not alive.", ephemeral=not public)

        # Channel check
        role_ch_id = (actor.get("role_channel_id") if isinstance(actor, dict) else None)
        if role_ch_id and interaction.channel and interaction.channel.id != role_ch_id:
            # Allow admins to act from anywhere for testing, users restricted
            if not interaction.user.guild_permissions.administrator:
                return await ctx.reply("Use your role’s private channel to /act.", ephemeral=not public)

        # Flag check
        flags = actor.get("flags", {}) or {}
        needed_flag = "day_act" if phase == "day" else "night_act"
        if not bool(flags.get(needed_flag, False)):
            return await ctx.reply(f"You are not allowed to act during **{phase.title()}**.", ephemeral=not public)

        # Target check
        target_uid = str(target.id) if target else None
        if target_uid:
            t = players.get(target_uid)
            if not t:
                return await ctx.reply("Target is not registered.", ephemeral=not public)
            # DEAD TARGET FIX: We allow acting on dead players (e.g. for revivers/mediums).
            # Status/Role logic handles validity later.

        # Action kind
        action_kind = "day_action" if phase == "day" else "night_action"

        # Status Gate
        gate = await _gate_action(ctx, game, actor_uid, action_kind, target_uid, public=public)
        if not gate["ok"]:
            return await ctx.reply(gate["msg"], ephemeral=gate["ephemeral"])

        if gate.get("redirect_to"):
            target_uid = gate["redirect_to"]
            try:
                await ctx.reply("🌀 You're Confused... your action was redirected.", ephemeral=True)
            except Exception:
                pass

        # Determine cycle number
        phase_norm = "day" if phase == "day" else "night"
        number = act_core.current_cycle_number(phase_norm)

        # Enqueue Action
        # We print the note to console to verify it arrived
        clean_note = (note or "").strip()
        if clean_note:
            log.info(f"[ACT] User {interaction.user} sent note: {clean_note}")

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
            return await ctx.reply(msg or "Action rejected.", ephemeral=not public)

        await save_state()

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
                log.error(f"Expansion action hook failed: {e}")


        # Audit log
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

        verb = "updated" if res.get("replaced") else "registered"
        await ctx.reply(f"✅ Action {verb} for **{phase_norm.title()} {number}**.", ephemeral=not public)


# =================================================================
#  B) ADMIN GROUP: /actions logs | /actions breakdown
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


class ActionsAdminCog(commands.GroupCog, name="actions", description="Day/Night actions utilities (admin)"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="logs", description="Phase logs: user=all numbers; number=specific Day/Night.")
    @app_commands.describe(
        phase="Which phase to inspect (auto/day/night)",
        number="Day/Night number; omit to use current",
        user="Filter by user",
        public="Post publicly (default: false)",
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

        # A) User history (all cycles)
        if user is not None and number is None:
            uid = str(user.id)
            rows = act_core.get_user_logs_all(p, uid)
            title = f"{p.title()} Actions — {user.display_name} (History)"
            embed = discord.Embed(title=title, color=0x8E44AD)

            if not rows:
                embed.description = "No actions recorded."
                return await ctx.reply(embed=embed, ephemeral=not public)

            by_num: dict[int, list[dict]] = {}
            for n, act in rows:
                by_num.setdefault(n, []).append(act)

            for n in sorted(by_num.keys()):
                acts = by_num[n]
                lines = [_fmt_action_line(a) for a in acts]
                embed.add_field(name=f"{p.title()} {n}", value=("\n".join(lines)[:1024] or "—"), inline=False)

            return await ctx.reply(embed=embed, ephemeral=not public)

        # B) Phase logs (specific cycle)
        n = number if number is not None else act_core.current_cycle_number(p)
        uid = str(user.id) if user else None
        rows = act_core.get_logs(p, n, uid)

        title = f"{p.title()} {n} — Logs"
        embed = discord.Embed(title=title, color=0x8E44AD)

        if not rows:
            embed.description = "No actions recorded."
            return await ctx.reply(embed=embed, ephemeral=not public)

        by_user: dict[str, list[dict]] = {}
        for r in rows:
            u = str(r.get("uid"))
            by_user.setdefault(u, []).append(r)

        for u, acts in by_user.items():
            lines = [_fmt_action_line(a) for a in acts]
            name = _label_from_uid(u)
            # Clean Title (Emoji + Name only)
            embed.add_field(name=f"👤 {name}", value=("\n".join(lines)[:1024] or "—"), inline=False)

        await ctx.reply(embed=embed, ephemeral=not public)

    @app_commands.command(name="breakdown", description="Who can act vs who acted.")
    @app_commands.choices(phase=PHASE_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def breakdown_cmd(
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

        can_act = set(act_core.actors_for_phase(p))
        acted = set(act_core.acted_uids(p, n))

        missing = sorted(can_act - acted)
        acted_sorted = sorted(acted & can_act)

        def fmt_names(uids: List[str]) -> str:
            if not uids: return "—"
            names = []
            for uid in uids[:24]:
                pdata = game.players.get(uid, {})
                label = pdata.get("name") or pdata.get("alias") or f"<@{uid}>"
                names.append(f"`{label}`")
            if len(uids) > 24: names.append(f"… (+{len(uids)-24} more)")
            return ", ".join(names)

        embed = discord.Embed(
            title=f"{p.title()} {n} — Breakdown",
            description=f"**Total:** {len(can_act)} | **Done:** {len(acted_sorted)} | **Waiting:** {len(missing)}",
            color=0x2C3E50 if p == "night" else 0x3498DB
        )
        embed.add_field(name="✅ Acted", value=fmt_names(acted_sorted), inline=False)
        embed.add_field(name="⏳ Pending", value=fmt_names(missing), inline=False)

        await ctx.reply(embed=embed, ephemeral=not public)


async def setup(bot: commands.Bot):
    await bot.add_cog(ActionsCog(bot))
    await bot.add_cog(ActionsAdminCog(bot))