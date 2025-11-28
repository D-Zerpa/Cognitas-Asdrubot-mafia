from __future__ import annotations
from typing import Optional, List, Dict, Any
import re
import json
import discord
from discord import app_commands
from discord.ext import commands

from ..core.infra import (
    get_infra, set_infra, ensure_category, ensure_text_channel,
    ensure_day_channel, as_overwrites_for_private, ASDRU_TAG, ensure_role, set_roles, is_asdrubot_channel)
from ..core.storage import save_state
from ..core.state import game
from ..expansions import get_registered, get_unique_profiles

# ---------- Helpers ----------

def _short_mechanics() -> str:
    return (
        "• **Day**: talk and vote (/vote cast). Majority lynches.\n"
        "• **Night**: roles act with /act.\n"
        "• **Statuses** affect actions/votes; bot enforces gates.\n"
        "• **Logs**: actions & phase changes appear in the Logs channel."
    )

def _default_expansion_choices() -> list[app_commands.Choice[str]]:
    canonical = get_unique_profiles() or ["base"]
    return [app_commands.Choice(name=name, value=name) for name in canonical]

async def _load_role_names(expansion_key: str) -> List[str]:
    """
    Return the role names to create private channels for.
    Strategy:
      1) Ask expansion class for a manifest (if provided).
      2) Fallback to a known JSON file in data/ (if present).
      3) Else, return [] and let admin create later.
    """
    names: List[str] = []
    try:
        Exp = get_registered(expansion_key)
        if Exp and hasattr(Exp, "roles_manifest"):
            names = [r.get("name") for r in Exp.roles_manifest() if isinstance(r, dict) and r.get("name")]
            return [str(n) for n in names]
    except Exception:
        pass
    # Fallback — optional: if you keep a data/roles_{key}.json or roles_default.json
    try:
        import json, importlib.resources as res
        # Try specific, then default
        for fname in (f"roles_{expansion_key}.json", "roles_default.json"):
            if res.is_resource(__package__.rsplit(".",1)[0], f"../data/{fname}"):  # pseudo check
                pass  # skip, this can be replaced by actual file access if bundled
    except Exception:
        pass
    return []  # no manifest; safe default

def _slugify_channel(name: str) -> str:
    """
    Build a Discord-safe channel name: lowercase, hyphens, alnum only.
    """
    base = name.strip().lower().replace(" ", "-")
    base = re.sub(r"[^a-z0-9\-]+", "-", base)
    base = re.sub(r"-{2,}", "-", base).strip("-")
    return base or "role"

def _load_role_names_from_expansion(expansion_key: str) -> List[str]:
    """
    Try to fetch role names from the registered expansion class.
    If the expansion exposes roles_manifest() -> List[dict{name:...}], use it.
    """
    try:
        Exp = get_registered(expansion_key)
        if Exp and hasattr(Exp, "roles_manifest"):
            roles = Exp.roles_manifest()  # type: ignore
            out = []
            for r in roles or []:
                if isinstance(r, dict) and r.get("name"):
                    out.append(str(r["name"]).strip())
            # unique, keep order
            seen, uniq = set(), []
            for n in out:
                if n and n not in seen:
                    seen.add(n); uniq.append(n)
            return uniq
    except Exception:
        pass
    return []

def _load_role_names_from_json(expansion_key: str) -> List[str]:
    """
    Fallback: try reading roles from JSON files in the repo (if present).
    Looks for: cognitas/data/roles_{key}.json, then roles_default.json.
    Accepted shapes:
      - {"roles":[{"name":"..."}]} or [{"name":"..."}]
    """
    candidates = [
        f"cognitas/data/roles_{expansion_key}.json",
        "cognitas/data/roles_default.json",
    ]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("roles", data)  # dict or list
            out = []
            for r in items or []:
                if isinstance(r, dict) and r.get("name"):
                    out.append(str(r["name"]).strip())
            if out:
                seen, uniq = set(), []
                for n in out:
                    if n and n not in seen:
                        seen.add(n); uniq.append(n)
                return uniq
        except Exception:
            continue
    return []

def load_role_names(expansion_key: str) -> List[str]:
    """
    Unified loader: prefer expansion manifest, fallback to JSON.
    """
    names = _load_role_names_from_expansion(expansion_key)
    if names:
        return names
    return _load_role_names_from_json(expansion_key)


# ---------- Views ----------

class SetupView(discord.ui.View):
    def __init__(self, invoker: discord.Member, bot: commands.Bot, *, timeout: int = 600):
        super().__init__(timeout=timeout)
        self.invoker = invoker
        self.bot = bot
        self.expansion_choice: Optional[str] = None

        # Dynamic select for expansions (Keep this in __init__)
        self.expansion_select = discord.ui.Select(
            placeholder="Select expansion profile",
            min_values=1, max_values=1,
            options=[
                discord.SelectOption(label=opt.name, value=opt.value) for opt in _default_expansion_choices()
            ],
        )
        self.expansion_select.callback = self.on_select
        self.add_item(self.expansion_select)

        # NOTE: Buttons are now handled via decorators below, removing duplicates and manual add_item calls.

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.invoker.id:
            return True
        perms = interaction.user.guild_permissions
        return perms.administrator or perms.manage_guild

    async def on_select(self, interaction: discord.Interaction):
        # Callback for the dropdown
        self.expansion_choice = self.expansion_select.values[0]
        await interaction.response.send_message(f"Expansion selected: **{self.expansion_choice}**", ephemeral=True)

    # --- Buttons defined natively (Auto-wired callbacks) ---

    @discord.ui.button(label="Create Structure", style=discord.ButtonStyle.success, row=1)
    async def create_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.expansion_choice:
            return await interaction.response.send_message("⚠️ Please select an expansion profile first.", ephemeral=True)
        await self._handle_create(interaction)

    @discord.ui.button(label="Wipe Game Channels", style=discord.ButtonStyle.danger, row=1)
    async def wipe_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_wipe(interaction)

    @discord.ui.button(label="Help / Mechanics", style=discord.ButtonStyle.secondary, row=1)
    async def help_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(_short_mechanics(), ephemeral=True)

    # dispatch component custom_ids
    async def interaction_handle(self, interaction: discord.Interaction):
        cid = interaction.data.get("custom_id") if interaction.data else None  # type: ignore
        if cid == "as_create":
            await self._handle_create(interaction)
        elif cid == "as_wipe":
            await self._handle_wipe(interaction)
        elif cid == "as_help":
            await interaction.response.send_message(_short_mechanics(), ephemeral=True)

    async def on_submit(self, interaction: discord.Interaction):
        # not used; buttons/selects handle themselves
        pass

    async def _handle_create(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return await interaction.followup.send("This must be used in a server.", ephemeral=True)
        bot_member = guild.me
        if not bot_member:
            return await interaction.followup.send("Bot member not found in this guild.", ephemeral=True)

        # 1) Categories
        admin_cat   = await ensure_category(guild, "Asdrubot — Admin")
        public_cat  = await ensure_category(guild, "Asdrubot — Game")
        roles_cat   = await ensure_category(guild, "Asdrubot — Roles")
        logs_cat    = await ensure_category(guild, "Asdrubot — Logs")

        # 2) Channels
        overw_admin = as_overwrites_for_private(bot_member, self.invoker)
        ch_admin = await ensure_text_channel(guild, "asdrubot-admin", category=admin_cat, overwrites=overw_admin, topic="Private admin control. " + ASDRU_TAG)
        ch_logs  = await ensure_text_channel(guild, "asdrubot-logs", category=logs_cat, overwrites=as_overwrites_for_private(bot_member, self.invoker), topic="System logs. " + ASDRU_TAG)
        ch_day   = await ensure_text_channel(guild, "day-chat", category=public_cat, topic="Day chat. " + ASDRU_TAG)

        # 3) Alive/Dead roles (names per your request)
        alive_role = await ensure_role(guild, "Alive", colour=discord.Colour.green(), mentionable=True, hoist=False)
        dead_role  = await ensure_role(guild, "Dead", colour=discord.Colour.red(), mentionable=False, hoist=False)

        set_roles(guild.id, alive=alive_role.id, dead=dead_role.id)


        # 3) Role channels (private, one per role name)
        chosen = (self.expansion_choice or "base").strip()
        role_names: List[str] = load_role_names(chosen)

        role_channels: Dict[str, int] = {}
        if role_names:
            # Who can see new role channels by default? Bot + invoker (admin).
            overw_private = as_overwrites_for_private(bot_member, self.invoker)

            for rn in role_names:
                safe_name = f"{_slugify_channel(rn)}"
                ch = await ensure_text_channel(
                    guild,
                    safe_name,
                    category=roles_cat,
                    overwrites=overw_private,
                    topic=f"Private channel for role '{rn}'. {ASDRU_TAG}",
                )
                role_channels[rn] = ch.id
        else:
            # If no roles were found, inform admin (ephemeral)
            await interaction.followup.send(
                f"Note: no role names found for expansion '{chosen}'. Skipping role-channel creation.",
                ephemeral=True
            )

        # Persist infra
        infra = get_infra(guild.id)
        infra["categories"] = {
            "admin": admin_cat.id,
            "public": public_cat.id,
            "roles": roles_cat.id,
            "logs": logs_cat.id,
        }
        infra["channels"] = {
            "admin": ch_admin.id,
            "logs": ch_logs.id,
            "game": ch_game.id,
        }
        infra["roles_category_id"] = roles_cat.id
        infra["role_channels"] = role_channels              # <— aquí guardamos el mapping
        infra["expansion_profile"] = chosen
        set_infra(guild.id, infra)
        await save_state()

        await interaction.followup.send(
        f"✅ Server structure ready. Created {len(role_channels)} role channel(s) for '{chosen}'.",
        ephemeral=True)


    async def _handle_wipe(self, interaction: discord.Interaction):
        # show a confirm view
        view = WipeConfirmView(invoker=self.invoker, bot=self.bot)
        await interaction.response.send_message("⚠️ Wipe game channels? This will delete channels tagged with `[ASDRUBOT]` except the admin category.", view=view, ephemeral=True)

class WipeConfirmView(discord.ui.View):
    def __init__(self, invoker: discord.Member, bot: commands.Bot, *, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.invoker = invoker
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.invoker.id:
            return True
        perms = interaction.user.guild_permissions
        return perms.administrator or perms.manage_guild

    @discord.ui.button(label="Confirm wipe", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return await interaction.followup.send("Use in a server.", ephemeral=True)

        infra = get_infra(guild.id)
        admin_cat_id = (infra.get("categories") or {}).get("admin")
        preserved_cat = guild.get_channel(admin_cat_id) if admin_cat_id else None

        deleted = 0
        # delete tagged channels in all categories except admin
        for ch in list(guild.text_channels):
            if preserved_cat and getattr(ch, "category_id", None) == preserved_cat.id:
                continue
            if is_asdrubot_channel(ch):
                try:
                    await ch.delete(reason="Asdrubot wipe")
                    deleted += 1
                except Exception:
                    pass

        # Optionally delete non-admin categories that are empty and marked
        for cat in list(guild.categories):
            if preserved_cat and cat.id == preserved_cat.id:
                continue
            try:
                if (not cat.text_channels) and any(is_asdrubot_channel(x) for x in getattr(cat, "channels", [])):
                    await cat.delete(reason="Asdrubot wipe")
            except Exception:
                pass

        # Reset infra (preserve admin)
        keep_channels = {}
        if "channels" in infra and "admin" in infra["channels"]:
            keep_channels["admin"] = infra["channels"]["admin"]
        infra["channels"] = keep_channels
        infra["role_channels"] = {}
        infra["categories"] = {"admin": (infra.get("categories") or {}).get("admin")}
        infra["roles_category_id"] = None
        set_infra(guild.id, infra)
        await save_state()

        await interaction.followup.send(f"🧹 Wipe done. Deleted {deleted} channels. Admin category preserved.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        await interaction.response.send_message("Wipe cancelled.", ephemeral=True)

# ---------- Cog ----------

class BootstrapCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Initialize Asdrubot UI for this server (admin)")
    @app_commands.default_permissions(administrator=True)
    async def setup_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        view = SetupView(invoker=interaction.user, bot=self.bot)
        # small intro embed
        embed = discord.Embed(
            title="Asdrubot — Server Setup",
            description="Pick an expansion, create the server structure, and optionally wipe previous game channels.",
            color=0x2ECC71
        )
        embed.add_field(name="How it works", value=_short_mechanics(), inline=False)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        

    @app_commands.command(name="wipe", description="Clean all [ASDRUBOT] channels (keeps Admin).")
    @app_commands.default_permissions(administrator=True)
    async def wipe(self, interaction: discord.Interaction):
        view = WipeConfirmView(interaction.user)  # reusa tu view actual
        await interaction.response.send_message(
            "⚠️ This will delete all [ASDRUBOT] channels except Admin. Are you sure?",
            view=view,
            ephemeral=True,
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(BootstrapCog(bot))
