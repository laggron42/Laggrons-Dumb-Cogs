import discord
import logging

from discord.ext import tasks

from redbot.core import commands
from redbot.core.i18n import Translator, get_babel_locale

from .abc import MixinMeta
from .utils import only_phase

from datetime import datetime
from babel.dates import format_date, format_time

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)

MAX_ERRORS = 3


class Registration(MixinMeta):
    def __init__(self):
        self.update_message_loop.start()
        self.task_errors = 0

    @tasks.loop(seconds=5)
    async def update_message_loop(self):
        guilds = filter(lambda x: x.status in ("register", "checkin"), self.tournaments.values())
        for tournament in guilds:
            if tournament.register_message is not None:
                try:
                    await tournament.register_message.edit(
                        content=tournament._prepare_register_message()
                    )
                except discord.NotFound as e:
                    log.error(
                        f"[Guild {tournament.guild.id}] Regiser message lost. "
                        "Removing from memory...",
                        exc_info=e,
                    )
                    tournament.register_message = None

    @update_message_loop.error
    async def on_loop_task_error(self, exception):
        self.task_errors += 1
        if self.task_errors >= MAX_ERRORS:
            log.critical(
                "Error in loop task. 3rd error, cancelling the task ...",
                exc_info=exception,
            )
        else:
            log.error(
                "Error in loop task. Resuming ...",
                exc_info=exception
            )
            self.update_message_loop.start()

    @only_phase("register", "checkin")
    @commands.command(name="in")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def _in(self, ctx: commands.Context):
        """
        Register to the current tournament, or check-in.
        """
        tournament = self.tournaments[ctx.guild.id]
        participant = tournament.find_participant(discord_id=ctx.author.id)[1]
        if participant is not None:
            # participant checkin-in
            if tournament.checkin_channel and ctx.channel.id != tournament.checkin_channel.id:
                await ctx.send(_("You cannot check in this channel."))
                return
            if tournament.phase != "checkin":
                await ctx.send(_("The check-in hasn't started yet."))
                return
            await participant.check()
        else:
            # participant registering
            if tournament.register_channel and ctx.channel.id != tournament.register_channel.id:
                await ctx.send(_("You cannot register in this channel."))
                return
            if tournament.limit and len(tournament.participants) + 1 > tournament.limit:
                await ctx.send(_("No more places for this tournament."))
                return
            try:
                await tournament.register_participant(ctx.author)
            except discord.HTTPException as e:
                log.error(
                    f"[Guild {ctx.guild.id}] Can't register participant {ctx.author.id}",
                    exc_info=e,
                )
                await ctx.send(_("I can't give you the role."))
                return
        await ctx.tick()

    @only_phase("register", "checkin")
    @commands.command(name="out")
    async def _out(self, ctx: commands.Context):
        """
        Leave the current tournament.

        If the tournament has started, use `[p]dq` instead.
        """
        tournament = self.tournaments[ctx.guild.id]
        i, participant = tournament.find_participant(discord_id=ctx.author.id)
        if participant is None:
            await ctx.send(_("You are not registered for this tournament."))
            return
        del self.tournaments[ctx.guild.id].participants[i]
        del participant  # not truely deleted until the last reference is removed
        log.debug(f"[Guild {ctx.guild.id}] Player {ctx.author} unregistered.")
        await ctx.tick()

    @only_phase("pending")
    @commands.command(name="inscriptions")
    async def begin_registration(self, ctx: commands.Context):
        """
        Starts the registration phase.
        """
        tournament = self.tournaments[ctx.guild.id]
        register_channel = tournament.register_channel
        participant_role = tournament.participant_role
        game_role = tournament.game_role

        await register_channel.purge(limit=None)
        await register_channel.set_permissions(participant_role, read_messages=True, send_messages=True,
                                               add_reactions=False)
        await register_channel.edit(slowmode_delay=60)

        await ctx.message.add_reaction("✅")

        locale = get_babel_locale()

        def format_datetime(date: datetime):
            date = format_date(date, format="full", locale=locale)
            time = format_time(date, format="short", locale=locale)
            return _("{date} at {time}").format(date=date, time=time)

        await tournament.announcements_channel.send(_(
            "Inscriptions for the **{tournament.name}** are opened in {register_channel} ! "
            "Consult the pinned messages {game_role}\n"
            ":calendar_spiral: This tournament will occur on **{date}**.").
                                                    format(tournament=tournament,
                                                           register_channel=register_channel.mention,
                                                           game_role=game_role.mention,
                                                           date=format_datetime(tournament.tournament_start)
                                                           )
        )
