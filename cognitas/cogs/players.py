import discord
from discord import app_commands
from discord.ext import commands
from ..core import players as players_core
from ..core.players import PlayerField as PF
from ..core.players import get_player_snapshot
from enum import Enum

class PlayersCog(commands.GroupCog, name="player", description="Gestionar jugadores"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="list", description="Ver jugadores vivos y muertos")
    async def list_cmd(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.list_players(ctx)

    @app_commands.command(name="register", description="Registrar jugador (admin)")
    @app_commands.describe(member="Jugador a registrar", name="Nombre opcional")
    @app_commands.default_permissions(administrator=True)
    async def register_cmd(self, interaction: discord.Interaction, member: discord.Member | None = None, name: str | None = None):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.register(ctx, member, name=name)

    @app_commands.command(name="unregister", description="Dar de baja (admin)")
    @app_commands.default_permissions(administrator=True)
    async def unregister_cmd(self, interaction: discord.Interaction, member: discord.Member):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.unregister(ctx, member)

    @app_commands.command(name="rename", description="Renombrar jugador (admin)")
    @app_commands.default_permissions(administrator=True)
    async def rename_cmd(self, interaction: discord.Interaction, member: discord.Member, new_name: str):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.rename(ctx, member, new_name=new_name)

    # Subgrupo /player alias …
    @app_commands.command(name="alias_show", description="Ver alias de un jugador")
    async def alias_show_cmd(self, interaction: discord.Interaction, member: discord.Member):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.alias_show(ctx, member)

    @app_commands.command(name="alias_add", description="Añadir alias (admin)")
    @app_commands.default_permissions(administrator=True)
    async def alias_add_cmd(self, interaction: discord.Interaction, member: discord.Member, alias: str):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.alias_add(ctx, member, alias=alias)

    @app_commands.command(name="alias_del", description="Eliminar alias (admin)")
    @app_commands.default_permissions(administrator=True)
    async def alias_del_cmd(self, interaction: discord.Interaction, member: discord.Member, alias: str):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.alias_del(ctx, member, alias=alias)


    @app_commands.command(name="edit", description="Edit a player's field (admin)")
    @app_commands.describe(
        member="Target player",
        field="Field to edit",
        value="New value (string; will be coerced to the field type)"
    )
    @app_commands.default_permissions(administrator=True)
    async def edit_cmd(self, interaction: discord.Interaction, member: discord.Member, field: PF, value: str):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.set_player_field(ctx, member, field.value, value)
        await interaction.response.defer(ephemeral=True)

    @app_commands.command(name="set_flag", description="Set a custom flag on a player (admin)")
    @app_commands.default_permissions(administrator=True)
    async def set_flag_cmd(self, interaction: discord.Interaction, member: discord.Member, key: str, value: str):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.set_flag(ctx, member, key, value)
        await interaction.response.defer(ephemeral=True)

    @app_commands.command(name="del_flag", description="Remove a custom flag from a player (admin)")
    @app_commands.default_permissions(administrator=True)
    async def del_flag_cmd(self, interaction: discord.Interaction, member: discord.Member, key: str):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.del_flag(ctx, member, key)
        await interaction.response.defer(ephemeral=True)

    @app_commands.command(name="add_effect", description="Add an effect to a player (admin)")
    @app_commands.default_permissions(administrator=True)
    async def add_effect_cmd(self, interaction: discord.Interaction, member: discord.Member, effect: str):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.add_effect(ctx, member, effect)
        await interaction.response.defer(ephemeral=True)

    @app_commands.command(name="remove_effect", description="Remove an effect from a player (admin)")
    @app_commands.default_permissions(administrator=True)
    async def remove_effect_cmd(self, interaction: discord.Interaction, member: discord.Member, effect: str):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.remove_effect(ctx, member, effect)
        await interaction.response.defer(ephemeral=True)

    # Shortcuts
    @app_commands.command(name="kill", description="Mark a player as dead (admin)")
    @app_commands.default_permissions(administrator=True)
    async def kill_cmd(self, interaction: discord.Interaction, member: discord.Member):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.kill(ctx, member)
        await interaction.response.defer(ephemeral=True)

    @app_commands.command(name="revive", description="Mark a player as alive (admin)")
    @app_commands.default_permissions(administrator=True)
    async def revive_cmd(self, interaction: discord.Interaction, member: discord.Member):
        ctx = await commands.Context.from_interaction(interaction)
        await players_core.revive(ctx, member)
        await interaction.response.defer(ephemeral=True)

    @app_commands.command(name="view", description="View a player's full state (admin)")
    @app_commands.default_permissions(administrator=True)
    async def view_cmd(self, interaction: discord.Interaction, member: discord.Member):
        data = get_player_snapshot(str(member.id))
        if not data:
            return await interaction.response.send_message("Player not registered.", ephemeral=True)

        def fmt_bool(b: bool | None):
            if b is None:
                return "—"
            return "✅ True" if b else "❌ False"

        def fmt_list(arr):
            return ", ".join(f"`{x}`" for x in arr) if arr else "—"

        def fmt_flags(d):
            if not d:
                return "—"
            parts = [f"`{k}`: `{v}`" for k, v in d.items()]
            # Prevent overlong field; keep first ~10
            if len(parts) > 10:
                parts = parts[:10] + ["…"]
            return "\n".join(parts)

        embed = discord.Embed(
            title=f"Player: {data['name']}",
            description=f"User: <@{data['uid']}>",
            color=0x3498DB if data["alive"] else 0xC0392B,
        )
        embed.add_field(name="Alive", value=fmt_bool(data.get("alive")), inline=True)
        embed.add_field(name="Role", value=data.get("role") or "—", inline=True)

        # Voting fields
        vw_field = data.get("vote_weight_field")
        vw_comp = data.get("vote_weight_computed")
        vb = data.get("voting_boost")
        hv = data.get("hidden_vote")

        embed.add_field(
            name="Voting",
            value="\n".join([
                f"- `vote_weight` (field): `{vw_field}`" if vw_field is not None else "- `vote_weight` (field): —",
                f"- `vote_weight` (computed): `{vw_comp}`" if vw_comp is not None else "- `vote_weight` (computed): —",
                f"- `voting_boost`: `{vb}`" if vb is not None else "- `voting_boost`: —",
                f"- `hidden_vote`: {fmt_bool(hv)}",
            ]),
            inline=False
        )

        # Aliases / Effects / Flags
        embed.add_field(name="Aliases", value=fmt_list(data.get("aliases", [])), inline=False)
        embed.add_field(name="Effects", value=fmt_list(data.get("effects", [])), inline=False)
        embed.add_field(name="Flags", value=fmt_flags(data.get("flags", {})), inline=False)

        embed.set_footer(text="Asdrubot v2.0 — Player inspector")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(PlayersCog(bot))

