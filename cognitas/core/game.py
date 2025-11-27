import os
import discord
from .state import game       # tu GameState existente
from .roles import load_roles
from .storage import save_state
from .logs import log_event
from .infra import get_infra
import unicodedata


def _norm_key(s: str) -> str:
    """Normalize a key for case-insensitive lookup without accents."""
    if not isinstance(s, str):
        return ""
    # remove surrounding spaces and strip accents
    s = unicodedata.normalize("NFKD", s.strip())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.upper()

def _extract_role_defaults(role_def: dict) -> dict:
    """
    Get profile-aware defaults:
    - SMT:        role_def["flags"]
    - Others:     role_def["defaults"] | role_def["base_flags"] | role_def["abilities"]["defaults"]
    """
    if not isinstance(role_def, dict):
        return {}
    # SMT
    if isinstance(role_def.get("flags"), dict):
        return role_def["flags"]
    # Others
    if isinstance(role_def.get("defaults"), dict):
        return role_def["defaults"]
    if isinstance(role_def.get("base_flags"), dict):
        return role_def["base_flags"]
    abilities = role_def.get("abilities")
    if isinstance(abilities, dict) and isinstance(abilities.get("defaults"), dict):
        return abilities["defaults"]
    return {}

def _build_roles_index(roles_def) -> dict:
    """
    Build a robust index: normalized KEY -> role_def
    Accepts 'code' | 'id' | 'name' plus 'aliases' in any combination.
    """
    roles_list = []
    if isinstance(roles_def, dict):
        roles_list = list(roles_def.get("roles") or [])
    elif isinstance(roles_def, list):
        roles_list = roles_def

    idx = {}
    for r in roles_list:
        if not isinstance(r, dict):
            continue
        keys = []
        for k in (r.get("code"), r.get("id"), r.get("name")):
            if isinstance(k, str) and k.strip():
                keys.append(_norm_key(k))
        for a in (r.get("aliases") or []):
            if isinstance(a, str) and a.strip():
                keys.append(_norm_key(a))
        # register all variants pointing to the same role_def
        for key in keys:
            if key:
                idx[key] = r
    return idx

def _lookup_role(role_name: str, roles_index: dict, roles_def) -> dict | None:
    """Search index first (fast) and fall back to scanning JSON if needed."""
    key = _norm_key(role_name or "")
    role_def = roles_index.get(key)
    if role_def:
        return role_def

    # Defensive fallback (in case the index wasn't built yet)
    roles_list = []
    if isinstance(roles_def, dict):
        roles_list = list(roles_def.get("roles") or [])
    elif isinstance(roles_def, list):
        roles_list = roles_def

    for r in roles_list:
        if not isinstance(r, dict):
            continue
        main_key = _norm_key(r.get("code") or r.get("id") or r.get("name") or "")
        alias_hit = any(_norm_key(a) == key for a in (r.get("aliases") or []) if isinstance(a, str))
        if main_key == key or alias_hit:
            return r
    return None


async def set_channels(*, day: discord.TextChannel | None = None, admin: discord.TextChannel | None = None):
    if day is not None:
        game.game_channel_id = day.id
    if admin is not None:
        game.admin_channel_id = admin.id
    await save_state()

async def start(ctx, *, profile: str = "default", day_channel: discord.TextChannel | None = None, admin_channel: discord.TextChannel | None = None):
    """
    Start a game with a roles profile (default, smt, ...).
    - Load roles_{profile}.json (or fall back to default)
    - Reset basic counters
    - Set day/admin channels if provided
    """
    from ..expansions import load_expansion_instance
    
    game.profile = profile.lower()
    game.roles_def = load_roles(game.profile)
    game.roles = _build_roles_index(game.roles_def)
    game.expansion = load_expansion_instance(game.profile)


    # Minimal non-destructive resets of players
    game.votes = {}
    game.end_day_votes = set()
    game.status_map = {} 
    game.status_log = []
    game.game_over = False
    game.current_day_number = 0
    game.phase = "day"
    game.day_deadline_epoch = None
    game.night_deadline_epoch = None

    await set_channels(day=day_channel or ctx.channel, admin=admin_channel)
    await save_state()

    chan = ctx.guild.get_channel(game.day_channel_id)
    await ctx.reply(
        f"🟢 **Game started** with profile **{game.profile}**.\n"
        f"Day channel: {chan.mention if chan else '#?'} | Roles file loaded."
    )
    await log_event(ctx.bot, ctx.guild.id, "GAME_START", profile=game.profile, day_channel_id=game.day_channel_id)


async def hard_reset(ctx_or_interaction):
    """
    Full reset compatible with:
    - commands.Context (ctx)  -> uses ctx.reply(...)
    - discord.Interaction     -> uses interaction.response / followup
    """
    # 1) clear memory
    game.players = {}
    game.votes = {}
    game.day_channel_id = None
    game.admin_channel_id = None
    game.default_day_channel_id = None
    game.current_day_number = 0
    game.day_deadline_epoch = None
    game.night_deadline_epoch = None
    game.profile = "default"
    game.roles_def = {}
    game.roles = {}
    game.night_actions = {}
    game.game_over = False
    # TODO: cancel timers if they exist

    # 2) delete files
    for path in ("state.json", "state.json.bak", "status.json", "status.json.bak"):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except Exception:
            pass

    # 3) persist empty state
    await save_state()

    # 4) respond to the user (ctx or interaction)
    try:
        if isinstance(ctx_or_interaction, discord.Interaction):
            interaction = ctx_or_interaction
            if not interaction.response.is_done():
                await interaction.response.send_message("🧹 Game state fully reset.", ephemeral=True)
            else:
                await interaction.followup.send("🧹 Game state fully reset.", ephemeral=True)
        else:
            # commands.Context
            await ctx_or_interaction.reply("🧹 Game state fully reset.")
    except Exception:
        pass

    # 5) log to the log channel (works for both)
    try:
        if isinstance(ctx_or_interaction, discord.Interaction):
            await log_event(ctx_or_interaction.client, ctx_or_interaction.guild.id, "GAME_RESET")
        else:
            await log_event(ctx_or_interaction.bot, ctx_or_interaction.guild.id, "GAME_RESET")
    except Exception:
        pass
 

async def finish(ctx, *, reason: str | None = None):
    game.game_over = True
    await save_state()
    await ctx.reply(f"🏁 **Game finished.** {('Reason: ' + reason) if reason else ''}".strip())
    await log_event(ctx.bot, ctx.guild.id, "GAME_FINISH", reason=reason or "-")


async def who(ctx, member: discord.Member | None = None):
    """
    Show player info (role if any) or a basic list.
    """
    if member:
        uid = str(member.id)
        pdata = game.players.get(uid)
        if not pdata:
            return await ctx.reply("Player not registered.")
        role = pdata.get("role") or "—"
        alive = "✅" if pdata.get("alive", True) else "☠️"
        return await ctx.reply(f"<@{uid}> — **{pdata.get('name','?')}** | Role: **{role}** | {alive}")
    # quick list if no member is passed
    alive = [u for u, p in game.players.items() if p.get("alive", True)]
    await ctx.reply(f"Alive players: {', '.join(f'<@{u}>' for u in alive) if alive else '—'}")

async def assign_role(ctx, member: discord.Member, role_name: str):
    """
    Assign a role to a player and link them to their pre-created private channel.
    """
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("Player not registered.")

    # 1. Look up role definition
    role_def = _lookup_role(role_name, getattr(game, "roles", {}) or {}, getattr(game, "roles_def", {}))
    if not role_def:
        return await ctx.reply(f"Unknown role: `{role_name}`")

    # Use the canonical name from the definition (e.g., "Makoto Yuki")
    canonical_name = role_def.get("name")
    game.players[uid]["role"] = canonical_name

    # 2. Merge defaults/flags (Existing logic)
    defaults = _extract_role_defaults(role_def)
    game.players[uid]["flags"] = defaults.copy() if defaults else {}

    # 3. CHANNEL LINKING LOGIC
    guild = getattr(ctx, "guild", None) or member.guild
    infra = get_infra(guild.id)
    
    # Retrieve the map created by bootstrap: { "Role Name": channel_id }
    role_channels = infra.get("role_channels", {})
    chan_id = role_channels.get(canonical_name)
    
    feedback_extra = ""
    
    if chan_id:
        channel = guild.get_channel(chan_id)
        if channel:
            try:
                # a) Grant permissions to the member
                await channel.set_permissions(
                    member, 
                    view_channel=True, 
                    send_messages=True, 
                    read_message_history=True
                )
                
                # b) Link player to this channel in state
                game.players[uid]["role_channel_id"] = chan_id
                
                # c) Send welcome/notification
                await channel.send(
                    f"👋 Welcome, {member.mention}. You have been assigned the role **{canonical_name}**.\n"
                    f"This is your private channel for actions and system notifications."
                )
                feedback_extra = f" | 📺 Linked to {channel.mention}"
            except Exception as e:
                feedback_extra = f" | ⚠️ Link failed: {e}"
        else:
            # Channel ID exists in infra but channel is gone from Discord
            game.players[uid]["role_channel_id"] = None
            feedback_extra = " | ⚠️ Role channel missing (deleted?)"
    else:
        # No pre-created channel found for this role
        game.players[uid]["role_channel_id"] = None

    await save_state()
    await ctx.reply(f"🎭 Role **{canonical_name}** assigned to <@{uid}>{feedback_extra}.")
    await log_event(ctx.bot, ctx.guild.id, "ASSIGN", user_id=str(member.id), role=canonical_name)

