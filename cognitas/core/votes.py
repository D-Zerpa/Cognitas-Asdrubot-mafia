import math
import discord
from .state import game
from .storage import save_state
from .logs import log_event

def _alive_count() -> int:
    return len(game.alive_ids())

def _two_thirds_threshold() -> int:
    return max(1, math.ceil((_alive_count() * 2) / 3))

async def vote(ctx, target_member: discord.Member):
    """Registra un voto y chequea si alguien llegó al umbral de linchamiento."""
    if game.day_channel_id != ctx.channel.id:
        return await ctx.reply("This is not the Day voting channel.")

    voter = str(ctx.author.id)
    target = str(target_member.id)

    if target not in game.players or not game.players[target].get("alive", True):
        return await ctx.reply("You must vote a valid, alive player.")

    # registrar voto
    game.votes[voter] = target
    save_state("state.json")

    await ctx.reply(f"✅ Vote registered on <@{target}> (weight {game.vote_weight(voter)}).")

    # comprobar si algún objetivo alcanzó su umbral
    totals = game.totals_per_target()
    for obj_uid, total in totals.items():
        req = game.required_for_target(obj_uid)
        if total >= req:
            # cerrar el canal y anunciar (sin ejecutar muerte aquí; delega a phases.end_day)
            chan = ctx.guild.get_channel(game.day_channel_id)
            overw = chan.overwrites_for(ctx.guild.default_role)
            overw.send_messages = False
            await chan.set_permissions(ctx.guild.default_role, overwrite=overw)
            await chan.send(f"🗳️ Threshold reached: <@{obj_uid}> ({total}/{req}). **Channel closed.**")
            # opción: llamar aquí a end_day con lynch_target_id=obj_uid
            return

    await log_event(ctx.bot, ctx.guild.id, "VOTE_CAST", voter_id=voter, target_id=target)

    try:
        await ctx.message.delete(delay=2)
    except Exception:
        pass

async def unvote(ctx):
    voter = str(ctx.author.id)
    if voter in game.votes:
        del game.votes[voter]
        save_state("state.json")
        await ctx.reply("🧹 Your vote has been cleared.")
    else:
        await ctx.reply("You had no active vote.")

    await log_event(ctx.bot, ctx.guild.id, "VOTE_CLEAR", voter_id=voter)

    try:
        await ctx.message.delete(delay=2)
    except Exception:
        pass

async def myvote(ctx):
    voter = str(ctx.author.id)
    tgt = game.votes.get(voter)
    if not tgt:
        return await ctx.reply("You have no active vote.")
    await ctx.reply(f"Your current vote is on <@{tgt}> (weight {game.vote_weight(voter)}).")

    try:
        await ctx.message.delete(delay=2)
    except Exception:
        pass

async def votes_breakdown(ctx):
    """Resumen por objetivo con pesos (solo en canal de Día)."""
    if game.day_channel_id != ctx.channel.id:
        return await ctx.reply("This is not the Day voting channel.")
    if not game.votes:
        return await ctx.reply("There are no votes yet.")

    totals = game.totals_per_target()
    if not totals:
        return await ctx.reply("There are no valid votes.")

    lines = []
    for target_uid, total in sorted(totals.items(), key=lambda x: (-x[1], x[0])):
        voters = [v for v, t in game.votes.items() if t == target_uid]
        vw = [game.vote_weight(v) for v in voters]
        req = game.required_for_target(target_uid)
        lines.append(
            f"• <@{target_uid}> — **{total}** / {req}  "
            f"(voters: {', '.join(f'<@{v}>(w:{w})' for v, w in zip(voters, vw))})"
        )

    await ctx.reply("\n".join(lines))

async def status(ctx):
    """Resumen del estado del Día."""
    chan = ctx.guild.get_channel(game.day_channel_id) if game.day_channel_id else None
    when = f"<t:{game.day_deadline_epoch}:R>" if game.day_deadline_epoch else "N/A"
    await ctx.reply(
        f"Day channel: {chan.mention if chan else '#?'}\n"
        f"Day: {game.current_day_number}\n"
        f"Base threshold: {game.base_threshold()}\n"
        f"Ends: {when}"
    )

async def clearvotes(ctx):
    """Admin: limpia todas las votaciones."""
    game.votes = {}
    save_state("state.json")
    await ctx.send("🗑️ All votes have been cleared.")

    await log_event(ctx.bot, ctx.guild.id, "VOTES_CLEARED")

    try:
        await ctx.message.delete(delay=2)
    except Exception:
        pass

# -------- /vote end_day (2/3) --------

async def request_end_day(ctx):
    """
    Un jugador solicita terminar el Día sin linchamiento.
    Si >= 2/3 de vivos lo piden, se cierra el Día (sin lynch).
    """
    if game.day_channel_id != ctx.channel.id:
        return await ctx.reply("This is not the Day voting channel.")

    if not hasattr(game, "end_day_votes"):
        game.end_day_votes = set()

    voter = str(ctx.author.id)
    if voter not in game.players or not game.players[voter].get("alive", True):
        return await ctx.reply("Only alive players can request end of day.")

    game.end_day_votes.add(voter)
    save_state("state.json")

    needed = _two_thirds_threshold()
    current = len(game.end_day_votes)
    await ctx.reply(f"🛎️ End-day request registered ({current}/{needed}).")
    await log_event(ctx.bot, ctx.guild.id, "END_DAY_REQUEST", voter_id=voter, tally=len(game.end_day_votes))

    if current >= needed:
        # cerrar canal de día sin linchamiento
        chan = ctx.guild.get_channel(game.day_channel_id)
        overw = chan.overwrites_for(ctx.guild.default_role)
        overw.send_messages = False
        await chan.set_permissions(ctx.guild.default_role, overwrite=overw)
        await chan.send("⚖️ **Day ends without lynch (2/3 reached).** **Channel closed.**")
        # limpiar votos normales y de end_day
        game.votes = {}
        game.end_day_votes.clear()
        game.day_deadline_epoch = None
        save_state("state.json")