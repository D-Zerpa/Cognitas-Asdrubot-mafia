from __future__ import annotations

import time
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..core.state import game
from ..core.storage import save_state
from ..core.logs import log_event  
from ..core import actions as act_core 
from ..status import engine as SE



def _label_from_uid(uid: str | None) -> str:
    if not uid:
        return "—"
    p = game.players.get(str(uid), {})
    return p.get("name") or p.get("alias") or f"<@{uid}>"

def _fmt_action_line(a: dict) -> str:
    act = a.get("action") or "act"
    tgt = _label_from_uid(a.get("target"))
    note = a.get("note") or "—"
    at = a.get("at")
    when = f"<t:{int(at)}:R>" if at else "—"
    return f"• action=`{act}` target={tgt} note=`{note}` at={when}"


async def _gate_action(ctx, game, actor_uid, action_kind: str, target_uid=None, public=False):
    chk = SE.check_action(game, actor_uid, action_kind, target_uid)
    if not chk.get("allowed", True):
        reason = (chk.get("reason") or "").strip()
        msg = SE.get_block_message(reason)
        return {"ok": False, "msg": msg, "ephemeral": not public, "redirect_to": None}
    return {"ok": True, "msg": None, "ephemeral": False, "redirect_to": chk.get("redirect_to")}


# ---------- Small adapter to safely reply after defer ----------
class InteractionCtx:
    def __init__(self, interaction: discord.Interaction):
        self._i = interaction
        self.guild = interaction.guild
        self.bot = interaction.client  # type: ignore
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
            # Fallback to channel if needed
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
        # Defer first to avoid Unknown interaction if anything takes long
        await interaction.response.defer(ephemeral=not public)
        ctx = InteractionCtx(interaction)

        # Resolve phase automatically from game.phase
        phase = (getattr(game, "phase", "day") or "day").lower()
        if phase not in ("day", "night"):
            phase = "day"

        # Check we actually are in a timed phase that accepts actions
        if phase == "night" and not getattr(game, "night_deadline_epoch", None):
            return await ctx.reply("It is not **Night** phase.", ephemeral=not public)
        if phase == "day" and not getattr(game, "day_deadline_epoch", None):
            # Allow you to tighten this policy to only certain day windows if desired
            return await ctx.reply("It is not **Day** phase.", ephemeral=not public)

        actor_uid = str(interaction.user.id)
        players = getattr(game, "players", {}) or {}
        actor = players.get(actor_uid)
        if not actor or not actor.get("alive", True):
            return await ctx.reply("You are not registered or you are not alive.", ephemeral=not public)

        # Require users to run /act from their own role channel, if set
        role_ch_id = (actor.get("role_channel_id") if isinstance(actor, dict) else None)
        if role_ch_id and interaction.channel and interaction.channel.id != role_ch_id:
            return await ctx.reply("Use your role’s private channel to /act.", ephemeral=not public)

        # Permission to act in this phase comes from flags: day_act / night_act
        flags = actor.get("flags", {}) or {}
        needed_flag = "day_act" if phase == "day" else "night_act"
        if not bool(flags.get(needed_flag, False)):
            return await ctx.reply(f"You are not allowed to act during **{phase.title()}**.", ephemeral=not public)

        # Validate target if provided
        target_uid = str(target.id) if target else None
        if target_uid:
            t = players.get(target_uid)
            if not t:
                return await ctx.reply("Target is not registered.", ephemeral=not public)


        # Decide action kind for this phase (day/night)
        action_kind = "day_action" if phase == "day" else "night_action"

        # Status engine gate (blocks like Paralyzed/Drowsiness/Jailed; Confusion may redirect)
        gate = await _gate_action(ctx, game, actor_uid, action_kind, target_uid, public=public)
        if not gate["ok"]:
            return await ctx.reply(gate["msg"], ephemeral=gate["ephemeral"])

        if gate.get("redirect_to"):
            target_uid = gate["redirect_to"]
            try:
                await ctx.reply("🌀 You're Confused... your action was redirected.", ephemeral=True)
            except Exception:
                pass

        # Determine logical number for the phase (Day N / Night N)
        phase_norm = "day" if phase == "day" else "night"
        number = act_core.current_cycle_number(phase_norm)

        # Build action record (schema is flexible; these fields are common)
        action_record = {
            "uid": actor_uid,
            "action": "act",
            "target": target_uid,
            "note": (note or "").strip(),
            "at": int(time.time()),
        }

        # Try via central helper.
        try:
            res = act_core.enqueue_action(
                game=game,
                actor_uid=actor_uid,
                action_kind=action_kind,          # "day_action" / "night_action"
                target_uid=target_uid,
                payload={                         # payload/metadata libre
                    "action": "act",
                    "note": (note or "").strip(),
                    "at": int(time.time()),
                },
                number=number,                    # opcional: explícita el N si tu helper lo admite
            )
            if isinstance(res, dict) and not res.get("ok", True):
                # Defensa: si el core nos bloquea, respetamos el motivo
                msg = res.get("reason") or "Action rejected by core."
                return await ctx.reply(msg, ephemeral=not public)

            await save_state()

        except AttributeError:
            # Enqueue centrally via core helper
            res = act_core.enqueue_action(
                game=game,
                actor_uid=actor_uid,
                action_kind=action_kind,          # "day_action" / "night_action"
                target_uid=target_uid,
                payload={
                    "action": "act",
                    "note": (note or "").strip(),
                    "at": int(time.time()),       # not required (core sets it) but harmless if present
                },
                number=number,                    # explicit cycle number (optional)
                action_name="act",
            )
            if not res.get("ok", True):
                # Map block reason to a user-facing message via StatusEngine
                msg = SE.get_block_message(res.get("reason") or "")
                return await ctx.reply(msg or "Action rejected.", ephemeral=not public)

            await save_state()


        # Optional audit log
        try:
            await log_event(
                self.bot,
                interaction.guild.id if interaction.guild else None,
                f"{phase_norm.upper()}_ACTION",
                actor_id=actor_uid,
                target_id=(target_uid or "None"),
                note=(note or "")
            )
        except Exception:
            pass

        await ctx.reply(f"✅ Action registered for **{phase_norm.title()} {number}**.", ephemeral=not public)


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

    # /actions logs
    @app_commands.command(
        name="logs",
        description="Phase logs: user=all numbers; number=specific Day/Night."
    )
    @app_commands.describe(
        phase="Which phase to inspect (auto/day/night)",
        number="Day/Night number; omit to use current for that phase",
        user="Filter by user (if provided WITHOUT number -> all numbers for that phase)",
        public="Post publicly instead of ephemeral (default: false)",
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

        # Case A: user given + number omitted => ALL numbers for that phase
        if user is not None and number is None:
            uid = str(user.id)
            rows = act_core.get_user_logs_all(p, uid)

            title = f"{p.title()} Actions — {user.display_name} (ALL {p}s)"
            embed = discord.Embed(title=title, color=0x8E44AD)

            if not rows:
                embed.description = "No actions recorded for this user."
                return await ctx.reply(embed=embed, ephemeral=not public)

            # Group by number
            by_num: dict[int, list[dict]] = {}
            for n, act in rows:
                by_num.setdefault(n, []).append(act)

            for n in sorted(by_num.keys()):
                acts = by_num[n]
                lines = [_fmt_action_line(a) for a in acts]
                embed.add_field(name=f"{p.title()} {n}", value=("\n".join(lines)[:1024] or "—"), inline=False)

            return await ctx.reply(embed=embed, ephemeral=not public)

        # Case B: specific number (with or without user) OR default current
        n = number if number is not None else act_core.current_cycle_number(p)
        uid = str(user.id) if user else None
        rows = act_core.get_logs(p, n, uid)

        title = f"{p.title()} {n} — Action Logs" + (f" (user: {user.display_name})" if user else "")
        embed = discord.Embed(title=title, color=0x8E44AD)

        if not rows:
            embed.description = "No actions recorded."
            return await ctx.reply(embed=embed, ephemeral=not public)

        # Group by user
        by_user: dict[str, list[dict]] = {}
        for r in rows:
            u = str(r.get("uid"))
            by_user.setdefault(u, []).append(r)

        for u, acts in by_user.items():
            lines = [_fmt_action_line(a) for a in acts]
            name = _label_from_uid(u)
            embed.add_field(name=f"{name} ({u})", value=("\n".join(lines)[:1024] or "—"), inline=False)


        await ctx.reply(embed=embed, ephemeral=not public)

    # /actions breakdown
    @app_commands.command(
        name="breakdown",
        description="Who can act, who acted, who is missing (for the chosen phase)."
    )
    @app_commands.describe(
        phase="Which phase to inspect (auto/day/night)",
        number="Day/Night number; omit to use current for that phase",
        public="Post publicly instead of ephemeral (default: false)",
    )
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

        can_act = set(act_core.actors_for_phase(p))               # alive + flags.day_act/night_act == True
        acted = set(act_core.acted_uids(p, n))                    # those who recorded an action for that number

        missing = sorted(can_act - acted)
        acted_sorted = sorted(acted & can_act)

        def fmt_names(uids: List[str]) -> str:
            if not uids:
                return "—"
            names = []
            for uid in uids[:24]:
                pdata = game.players.get(uid, {})
                label = pdata.get("name") or pdata.get("alias") or f"<@{uid}>"
                names.append(f"`{label}`")
            extra = len(uids) - min(len(uids), 24)
            if extra > 0:
                names.append(f"… (+{extra} more)")
            return ", ".join(names)

        color = 0x2C3E50 if p == "night" else 0x3498DB
        embed = discord.Embed(
            title=f"{p.title()} {n} — Act Breakdown",
            description="\n".join([
                f"**Can act:** {len(can_act)}",
                f"**Acted:** {len(acted_sorted)}",
                f"**Missing:** {len(missing)}",
            ]),
            color=color
        )
        embed.add_field(name="Acted", value=fmt_names(acted_sorted), inline=False)
        embed.add_field(name="Missing", value=fmt_names(missing), inline=False)

        await ctx.reply(embed=embed, ephemeral=not public)


# Setup: load both cogs
async def setup(bot: commands.Bot):
    await bot.add_cog(ActionsCog(bot))          # /act
    await bot.add_cog(ActionsAdminCog(bot))     # /actions logs, /actions breakdown