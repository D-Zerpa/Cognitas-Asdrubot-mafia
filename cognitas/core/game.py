import os
import discord
from .state import game      
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


async def set_channels(ctx, game_channel=None, admin_channel=None):
    """
    Sets the game and admin channels, syncing Legacy variables AND Infra.
    """
    # 1. Update Legacy State
    if game_channel:
        game.game_channel_id = game_channel.id
    if admin_channel:
        game.admin_channel_id = admin_channel.id

    # 2. Update Infra (The Fix)
    guild_id = ctx.guild.id
    infra = get_infra(guild_id)
    
    if "channels" not in infra:
        infra["channels"] = {}
        
    if game_channel:
        infra["channels"]["game"] = game_channel.id
    if admin_channel:
        infra["channels"]["admin"] = admin_channel.id
        
    # Persist
    set_infra(guild_id, infra)
    await save_state()
    
    return True

async def start(
    ctx, 
    *, 
    profile: str = "default", 
    game_channel: discord.TextChannel | None = None, 
    admin_channel: discord.TextChannel | None = None,
    alive_role_id: int | None = None,
    dead_role_id: int | None = None):

    """
    Start a game with a roles profile.
    Syncs manual Setup (channels/roles) into Infra to prevent disconnections.
    """
    # Imports necesarios dentro de la función para evitar ciclos
    from ..expansions import load_expansion_instance
    from .infra import get_infra, set_infra, set_roles
    
    # 1. Cargar configuración y expansión
    game.profile = profile.lower()
    try:
        game.roles_def = load_roles(game.profile)
        game.roles = _build_roles_index(game.roles_def)
        game.expansion = load_expansion_instance(game.profile)
    except Exception as e:
        return await ctx.reply(f"❌ Error al cargar perfil '{profile}': {e}")

    # 2. Reset de estado (Game State)
    # Usamos listas vacías para colecciones para evitar errores de JSON con sets
    game.votes = {}
    game.end_day_votes = [] 
    game.status_map = {} 
    game.status_log = []
    game.day_actions = {}
    game.night_actions = {}
    
    game.game_over = False
    game.current_day_number = 1
    game.phase = "day"
    game.day_deadline_epoch = None
    game.night_deadline_epoch = None

    # 3. Sincronización de Infraestructura (EL FIX)
    # Guardamos explícitamente la config manual en 'infra' para que el bot no la pierda
    guild_id = ctx.guild.id
    infra = get_infra(guild_id)
    
    # Aseguramos estructura
    if "channels" not in infra: infra["channels"] = {}
    if "roles" not in infra: infra["roles"] = {}

    # -- Sincronizar Canales --
    # Prioridad: Argumento > Canal actual
    target_game_ch = game_channel or ctx.channel
    
    # Guardamos en ambos sistemas (Legacy + Infra)
    game.game_channel_id = target_game_ch.id
    infra["channels"]["game"] = target_game_ch.id
    
    if admin_channel:
        game.admin_channel_id = admin_channel.id
        infra["channels"]["admin"] = admin_channel.id

    # -- Sincronizar Roles --
    # Si se pasan IDs manuales, los guardamos en infra inmediatamente
    if alive_role_id:
        game.alive_role_id = alive_role_id
        infra["roles"]["alive"] = alive_role_id
    
    if dead_role_id:
        game.dead_role_id = dead_role_id
        infra["roles"]["dead"] = dead_role_id

    # Guardamos los cambios en Infra
    set_infra(guild_id, infra)

    # También llamamos al helper set_roles por compatibilidad si se especificaron
    if alive_role_id or dead_role_id:
        await set_roles(guild_id, alive=alive_role_id, dead=dead_role_id)

    # 4. Guardado final y Feedback
    await save_state()

    roles_msg = "Roles cargados."
    if alive_role_id and dead_role_id:
        roles_msg += " Roles Vivo/Muerto vinculados."

    await ctx.reply(
        f"🟢 **Juego iniciado** con perfil **{game.profile}**.\n"
        f"Canal de juego: {target_game_ch.mention} | {roles_msg}"
    )
    
    await log_event(ctx.bot, guild_id, "GAME_START", profile=game.profile, game_channel_id=game.game_channel_id)


async def hard_reset(ctx_or_interaction):
    """
    Full reset compatible with:
    - commands.Context (ctx)  -> uses ctx.reply(...)
    - discord.Interaction     -> uses interaction.response / followup
    """
    # 1) clear memory
    game.players = {}
    game.votes = {}
    game.game_channel_id = None
    game.admin_channel_id = None
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
                await interaction.response.send_message("🧹 Estado del juego reiniciado.", ephemeral=True)
            else:
                await interaction.followup.send("🧹 Estado del juego reiniciado.", ephemeral=True)
        else:
            # commands.Context
            await ctx_or_interaction.reply("🧹 Estado del juego reiniciado.")
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
    await ctx.reply(f"🏁 **Juego terminado.** {('Razón: ' + reason) if reason else ''}".strip())
    await log_event(ctx.bot, ctx.guild.id, "GAME_FINISH", reason=reason or "-")


async def who(ctx, member: discord.Member | None = None):
    """
    Show player info (role if any) or a basic list.
    """
    if member:
        uid = str(member.id)
        pdata = game.players.get(uid)
        if not pdata:
            return await ctx.reply("Jugador no registrado.")
        role = pdata.get("role") or "—"
        alive = "✅" if pdata.get("alive", True) else "☠️"
        return await ctx.reply(f"<@{uid}> — **{pdata.get('name','?')}** | Role: **{role}** | {alive}")
    # quick list if no member is passed
    alive = [u for u, p in game.players.items() if p.get("alive", True)]
    await ctx.reply(f"Jugadores Vivos: {', '.join(f'<@{u}>' for u in alive) if alive else '—'}")

async def assign_role(ctx, member: discord.Member, role_name: str):
    """
    Assign a role to a player and link them to their private channel.
    AUTO-MAPPING: If the role has no channel in infra, assumes current channel is the one.
    """
    uid = str(member.id)
    if uid not in game.players:
        return await ctx.reply("❌ El jugador no está registrado.")

    # 1. Look up role definition
    role_def = _lookup_role(role_name, getattr(game, "roles", {}) or {}, getattr(game, "roles_def", {}))
    if not role_def:
        return await ctx.reply(f"Rol desconocido: `{role_name}`")

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
    new_mapping_saved = False
    
    # --- AUTO-MAPPING LOGIC ---
    if not chan_id:
        chan_id = ctx.channel.id
        if "role_channels" not in infra: infra["role_channels"] = {}
        infra["role_channels"][canonical_name] = chan_id
        new_mapping_saved = True
        feedback_extra = " | 💾 Canal mapeado automáticamente."

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
                    f"👋 Bienvenido, {member.mention}. Se te ha asignado el rol **{canonical_name}**.\n"
                    f"Este es tu canal privado para acciones y notificaciones del sistema."
                )
                feedback_extra += f" | 📺 Vinculado a {channel.mention}"
            except Exception as e:
                feedback_extra += f" | ⚠️ Fallo al vincular: {e}"
        else:
            # Channel ID exists in infra but channel is gone from Discord
            game.players[uid]["role_channel_id"] = None
            feedback_extra += " | ⚠️ Canal del rol perdido (¿borrado?)"
    else:
        # Fallback (no debería ocurrir con auto-mapping, pero por seguridad)
        game.players[uid]["role_channel_id"] = None

    await save_state()
    await ctx.reply(f"🎭 Rol **{canonical_name}** asignado a <@{uid}>{feedback_extra}.")
    await log_event(ctx.bot, ctx.guild.id, "ASSIGN", user_id=str(member.id), role=canonical_name)

