from datetime import datetime
import discord
import logging

from discord.ext import tasks

from redbot.core import commands
from redbot.core.i18n import Translator

from .abc import MixinMeta
from .utils import only_phase, mod_or_to, prompt_yes_or_no

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)

MAX_ERRORS = 3


class Registration(MixinMeta):
    def __init__(self):
        self.update_message_loop.start()
        self.update_message_task_errors = 0

    @tasks.loop(seconds=5)
    async def update_message_loop(self):
        guilds = filter(lambda x: x.register_phase == "ongoing", self.tournaments.values())
        for tournament in guilds:
            if tournament.register_message is not None:
                new_content = tournament._prepare_register_message()
                if new_content == tournament.register_message.content:
                    continue
                try:
                    await tournament.register_message.edit(content=new_content)
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
                "Error in loop task. 3rd error, cancelling the task ...", exc_info=exception,
            )
        else:
            log.error("Error in loop task. Resuming ...", exc_info=exception)
            self.update_message_loop.start()

    @only_phase("register")
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
            if participant.checked_in:
                await ctx.send(_("You are alreadu checked in."))
                return
            if tournament.checkin_channel and ctx.channel.id != tournament.checkin_channel.id:
                await ctx.send(_("You cannot check in this channel."))
                return
            if tournament.checkin_phase != "ongoing":
                await ctx.send(_("The check-in isn't active."))
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

    @only_phase("register", "awaiting")
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

    @only_phase("pending", "register", "awaiting")
    @mod_or_to()
    @commands.group()
    async def register(self, ctx: commands.Context):
        """
        Manually start and stop the registrations for the tournament.

        Automated start and stop can be setup with `[p]tset registration`.
        """
        pass

    @register.command(name="start")
    async def register_start(self, ctx: commands.Context):
        """
        Starts the registration phase.
        """
        tournament = self.tournaments[ctx.guild.id]
        if tournament.register_phase == "ongoing":
            await ctx.send(_("Registrations are already ongoing."))
            return
        elif tournament.register_phase == "pending":
            result = await prompt_yes_or_no(
                ctx,
                _(
                    "Looks like you have scheduled registrations. Do you want to cancel "
                    "the next scheduled opening of registrations?\nDecline if you intend to "
                    "manually close the registrations before the scheduled opening.\nNote: this "
                    "doesn't affect the second scheduled opening for two-stage registrations."
                ),
                negative_response=False,
            )
            if result:
                tournament.ignored_events.append("register_start")
        elif tournament.register_phase == "onhold":
            result = await prompt_yes_or_no(
                ctx,
                _(
                    "The first registrations are done, but it looks like you have a second "
                    "scheduled opening (two-stage registrations). Do you want to cancel "
                    "the next scheduled opening of registrations?\nDecline if you intend to "
                    "manually close the registrations before the scheduled opening."
                ),
                negative_response=False,
            )
            if result:
                tournament.ignored_events.append("register_second_start")
        await tournament.start_registration()
        await ctx.tick()

    @register.command(name="stop")
    async def register_stop(self, ctx: commands.Context):
        """
        Ends the registration phase.
        """
        tournament = self.tournaments[ctx.guild.id]
        if tournament.register_phase != "ongoing":
            await ctx.send(_("Registrations are not active."))
            return
        if (
            not tournament.register_second_start
            and tournament.register_stop
            and tournament.register_stop > datetime.utcnow()
        ):
            result = await prompt_yes_or_no(
                ctx,
                _(
                    "Looks like you have a scheduled stop. Do you want to cancel "
                    "the next scheduled closing of registrations?\nAccept if you do not "
                    "intend to re-open the registrations (or at least before the "
                    "scheduled closing)."
                ),
                negative_response=False,
            )
            if result:
                tournament.ignored_events.append("register_stop")
        elif (
            tournament.register_second_start
            and tournament.register_second_start > datetime.utcnow()
        ):
            result = await prompt_yes_or_no(
                ctx,
                _(
                    "Looks like you have another scheduled opening (two-stage registrations). "
                    "Do you want to cancel the next scheduled opening of registrations?\n"
                    "Accept if you want to fully close the registrations as of now."
                ),
                negative_response=False,
            )
            if result:
                tournament.ignored_events.append("register_second_start")
        await tournament.end_registration(background=False)
        await ctx.tick()

    @only_phase("pending", "register", "awaiting")
    @mod_or_to()
    @commands.group()
    async def checkin(self, ctx: commands.Context):
        """
        Manually start and stop the check-in for the tournament.

        Automated start and stop can be setup with `[p]tset registration`.
        """
        pass

    @checkin.command(name="start")
    async def checkin_start(self, ctx: commands.Context):
        """
        Starts the check-in phase.
        """
        tournament = self.tournaments[ctx.guild.id]
        if tournament.checkin_phase == "ongoing":
            await ctx.send(_("Check-in is already ongoing."))
            return
        elif tournament.checkin_phase == "pending" and self.checkin_start > datetime.utcnow():
            result = await prompt_yes_or_no(
                ctx,
                _(
                    "Looks like you have a scheduled check-in. If you continue, I will cancel "
                    "this scheduled opening of the check-in, even if you manually close it "
                    "before.\nDo you want to continue?"
                ),
                negative_response=False,
            )
            if not result:
                return
            tournament.ignored_events.append("checkin_start")
        elif tournament.checkin_phase == "done":
            result = await prompt_yes_or_no(
                ctx,
                _(
                    "Check-in was already done once. You can still manually open the check-in "
                    "a second time, but be aware of this.\nDo you want to make all participants "
                    "check again? Decline if you want participants that already checked not to "
                    "be bothered by this new check-in."
                ),
                negative_response=False,
            )
            if result:
                for participant in tournament.participants:
                    participant.checked_in = False
        await tournament.start_check_in()
        await ctx.tick()

    @checkin.command(name="stop")
    async def checkin_stop(self, ctx: commands.Context):
        """
        Ends the check-in phase.
        """
        tournament = self.tournaments[ctx.guild.id]
        if tournament.checkin_phase != "ongoing":
            await ctx.send(_("Check-in is not active."))
            return
        if tournament.checkin_stop and tournament.checkin_stop > datetime.utcnow():
            result = await prompt_yes_or_no(
                ctx,
                _(
                    "Looks like you have a scheduled stop. Do you want to cancel "
                    "the next scheduled closing of check-in?\nAccept if you do not "
                    "intend to re-open the check-in (or at least before the "
                    "scheduled closing)."
                ),
                negative_response=False,
            )
            if result:
                tournament.ignored_events.append("checkin_stop")
        await tournament.end_checkin(background=False)
        await ctx.tick()
