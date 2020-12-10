import discord
import logging

from datetime import datetime
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
        self.registration_loop.start()
        self.update_message_task_errors = 0

    # update message, also scheduler for registration/checkin start/stop
    @tasks.loop(seconds=5)
    async def registration_loop(self):
        for tournament in self.tournaments.values():
            if tournament.phase in ("ongoing", "finished"):
                continue  # Tournament has its own loop for that part
            need_saving = False  # prevent saving each 5 seconds
            if tournament.register_message:
                new_content = tournament._prepare_register_message()
                if new_content != tournament.register_message.content:
                    try:
                        await tournament.register_message.edit(content=new_content)
                    except discord.NotFound as e:
                        log.error(
                            f"[Guild {tournament.guild.id}] Regiser message lost. "
                            "Removing from memory...",
                            exc_info=e,
                        )
                        tournament.register_message = None
                        need_saving = True
            if (
                tournament.checkin_phase == "ongoing"
                and tournament.checkin_stop
                and tournament.checkin_reminders
            ):
                duration = (tournament.checkin_stop - datetime.now(tournament.tz)).total_seconds()
                duration //= 60  # only minutes
                next_call, should_dm = data = max(tournament.checkin_reminders, key=lambda x: x[0])
                if next_call >= duration + 1:
                    await tournament.call_check_in(should_dm)
                    tournament.checkin_reminders.remove(data)
                    need_saving = True
            try:
                name, time = tournament.next_scheduled_event()
            except TypeError:
                pass
            else:
                if time.total_seconds() <= 0:
                    coro = {
                        "register_start": tournament.start_registration,
                        "register_second_start": tournament.start_registration,
                        "register_stop": tournament.end_registration,
                        "checkin_start": tournament.start_check_in,
                        "checkin_stop": tournament.end_checkin,
                    }.get(name)
                    log.debug(f"[Guild {tournament.guild.id}] Scheduler call: {coro}")
                    if name == "register_second_start":
                        await coro(second=True)
                    else:
                        await coro()
                    need_saving = True
            if need_saving is True:
                await tournament.save()

    @registration_loop.error
    async def on_loop_task_error(self, exception):
        self.registration_loop_task_errors += 1
        if self.registration_loop_task_errors >= MAX_ERRORS:
            log.critical(
                "Error in loop task. 3rd error, cancelling the task ...",
                exc_info=exception,
            )
        else:
            log.error("Error in loop task. Resuming ...", exc_info=exception)
            self.registration_loop.start()

    @only_phase("pending", "register", "awaiting")
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
                await ctx.send(_("You are already checked in."))
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
            if tournament.register_channel and (
                ctx.channel.id != tournament.register_channel.id
                and not (
                    tournament.vip_register_channel
                    and ctx.channel.id == tournament.vip_register_channel.id
                )
            ):
                await ctx.send(_("You cannot register in this channel."))
                return
            if tournament.limit and len(tournament.participants) + 1 > tournament.limit:
                await ctx.send(_("No more places for this tournament."))
                return
            if (
                tournament.vip_register_channel
                and ctx.channel.id == tournament.vip_register_channel.id
            ):
                # VIP registrations are valid as long as registrations aren't explicitly closed
                if tournament.register_phase == "done":
                    await ctx.send(_("Registrations aren't active."))
                    return
            elif tournament.register_phase != "ongoing":
                await ctx.send(_("Registrations aren't active."))
                return
            async with tournament.lock:
                try:
                    await tournament.register_participant(ctx.author)
                except RuntimeError:
                    return
                except discord.HTTPException as e:
                    log.error(
                        f"[Guild {ctx.guild.id}] Can't register participant {ctx.author.id}",
                        exc_info=e,
                    )
                    await ctx.send(_("I can't give you the role."))
                    return
        await ctx.tick()

    @only_phase("pending", "register", "awaiting")
    @commands.command(name="out")
    async def _out(self, ctx: commands.Context):
        """
        Leave the current tournament.

        If the tournament has started, use `[p]dq` instead.
        """
        tournament = self.tournaments[ctx.guild.id]
        try:
            await tournament.unregister_participant(ctx.author)
        except KeyError:
            await ctx.send(_("You are not registered for this tournament."))
            return
        log.debug(f"[Guild {ctx.guild.id}] Player {ctx.author} unregistered.")
        await ctx.tick()

    @only_phase("pending", "register", "awaiting")
    @mod_or_to()
    @commands.command()
    async def add(self, ctx: commands.Context, *members: discord.Member):
        """
        Register members manually.

        You can provide multiple mentions, IDs, or full names (enclosed in quotation marks if \
there are spaces).
        Members already registered are ignored.
        """
        guild = ctx.guild
        if not members:
            await ctx.send_help()
            return
        tournament = self.tournaments[guild.id]
        members = [x for x in members if x not in tournament.participants]
        if not members:
            if len(members) == 1:
                await ctx.send(_("The member you provided is already registered."))
            else:
                await ctx.send(_("The members you provided are already registered."))
            return
        total = len(tournament.participants) + len(members)
        if tournament.limit and total > tournament.limit:
            if len(members) == 1:
                await ctx.send(
                    _(
                        "You want to register a member, but you're exceeding "
                        "the limit of participants ({total}/{limit})."
                    ).format(total=total, limit=tournament.limit)
                )
            else:
                await ctx.send(
                    _(
                        "You want to register {register} members, but you're exceeding "
                        "the limit of participants ({total}/{limit})."
                    ).format(register=len(members), total=total, limit=tournament.limit)
                )
            return
        failed = 0
        async with ctx.typing():
            for member in members:
                try:
                    await tournament.register_participant(member, send_dm=False)
                except discord.HTTPException:
                    if len(members) == 1:
                        raise  # single members should raise exceptions
                    failed += 1
        succeed = len(members) - failed
        if tournament.checkin_phase != "pending":
            if succeed == 1:
                check = _(" He is pre-checked.")
            else:
                check = _(" They are pre-checked.")
        else:
            check = ""
        if failed:
            if failed == 1:
                failed = _("\nA member couldn't be registered.").format(failed=failed)
            else:
                failed = _("\n{failed} members couldn't be registered.").format(failed=failed)
        else:
            failed = ""
        if succeed == 1:
            await ctx.send(
                _("Successfully registered a participant.{check}{failed}").format(
                    check=check,
                    failed=failed,
                )
            )
        else:
            await ctx.send(
                _("Successfully registered {register} participants.{check}{failed}").format(
                    register=succeed,
                    check=check,
                    failed=failed,
                )
            )

    @only_phase()
    @mod_or_to()
    @commands.command(name="rm")
    async def remove(self, ctx: commands.Context, *members: discord.Member):
        """
        Unregister members manually.

        You can provide multiple mentions, IDs, or full names (enclosed in quotation marks if \
there are spaces).
        """
        guild = ctx.guild
        if not members:
            await ctx.send_help()
            return
        tournament = self.tournaments[guild.id]
        members = [x for x in members if x in tournament.participants]
        if not members:
            if len(members) == 1:
                await ctx.send(_("The member you provided isn't registered."))
            else:
                await ctx.send(_("The members you provided aren't registered."))
            return
        failed = 0
        async with ctx.typing():
            for member in members:
                try:
                    await tournament.unregister_participant(member)
                except discord.HTTPException:
                    if len(members) == 1:
                        raise  # single members should raise exceptions
                    failed += 1
        success = len(members) - failed
        if failed:
            if failed == 1:
                failed = _("\nA member couldn't be unregistered.")
            else:
                failed = _("\n{failed} members couldn't be unregistered.").format(failed=failed)
        else:
            failed = ""
        if success == 1:
            await ctx.send(
                _("Successfully unregistered a participant.{failed}").format(failed=failed)
            )
        else:
            await ctx.send(
                _("Successfully unregistered {register} participants.{failed}").format(
                    register=success,
                    failed=failed,
                )
            )

    @only_phase("pending", "register", "awaiting")
    @mod_or_to()
    @commands.group()
    async def register(self, ctx: commands.Context):
        """
        Manually start and stop the registrations for the tournament.

        Automated start and stop can be setup with `[p]tset register`.
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
            and tournament.register_stop > datetime.now(tournament.tz)
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
        elif tournament.register_second_start and tournament.register_second_start > datetime.now(
            tournament.tz
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
        await tournament.end_registration()
        await ctx.tick()

    @only_phase("pending", "register", "awaiting")
    @mod_or_to()
    @commands.group()
    async def checkin(self, ctx: commands.Context):
        """
        Manually start and stop the check-in for the tournament.

        Automated start and stop can be setup with `[p]tset checkin`.
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
        elif tournament.checkin_phase == "pending" and tournament.checkin_start > datetime.now(
            tournament.tz
        ):
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
        if tournament.checkin_stop and tournament.checkin_stop > datetime.now(tournament.tz):
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
        await tournament.end_checkin()
        await ctx.tick()

    @checkin.command(name="call")
    async def checkin_call(self, ctx: commands.Context, should_dm: bool = False):
        """
        Send a message in the check-in channel pinging all members not checked yet.

        You need a check-in channel and an end date configured before using this.
        If you want the bot to also DM members, type `[p]checkin call yes`
        """
        tournament = self.tournaments[ctx.guild.id]
        if tournament.checkin_phase != "ongoing":
            await ctx.send(_("Check-in is not active."))
            return
        if not tournament.checkin_channel:
            await ctx.send(_("There is no check-in channel currently configured."))
            return
        if not tournament.checkin_stop:
            await ctx.send(_("This feature is only available with a configured stop time."))
            return
        if tournament.checkin_stop < datetime.now(tournament.tz):
            await ctx.send(_("The configured check-in end time has already passed."))
            return
        if should_dm is True:
            async with ctx.typing():
                await tournament.call_check_in(True)
            await ctx.send(_("Successfully called and DMed the unchecked members."))
        else:
            await tournament.call_check_in()
            await ctx.tick()
