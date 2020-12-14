import discord
import logging
import asyncio

from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n

from .abc import MixinMeta
from .utils import only_phase, mod_or_to, prompt_yes_or_no

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)


@cog_i18n(_)
class Troubleshooting(MixinMeta):
    @mod_or_to()
    @commands.group(name="tfix", aliases=["tournamentfix"])
    @commands.guild_only()
    async def tournamentfix(self, ctx: commands.Context):
        """
        Advanced commands for fixing possible bugs during the tournament.

        :warning: **Those commands will force run what you ask for, and may cause even more \
issues if you don't know what you're doing!**
        This allows you to reload some internal components of your tournament, refresh \
informations from remote, hard reset the internal list of participant, matches, or even the \
whole tournament.

        Run `[p]help tfix <yourcommand>` for details on the command before breaking everything.
        """
        pass

    @only_phase()
    @tournamentfix.command(name="reload")
    async def tournamentfix_reload(self, ctx: commands.Context):
        """
        Reload the tournament from disk.

        This reloads the config and refreshes the participants and matches list.

        This command is relatively safe to use, and fixes most problems. Try this before other, \
more "violent", options.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        await tournament.save()
        tournament.stop_loop_task()
        del self.tournaments[guild.id]
        try:
            self.tournaments[guild.id] = await self._restore_tournament(guild)
        except Exception as e:
            log.error(f"[Guild {guild.id}] Can't reload tournament {tournament}.", exc_info=e)
            await ctx.send(
                _(
                    "The tournament was successfully unloaded from memory, but an error occured "
                    "when reloading. Check the logs for details. You can try manually reloading "
                    "with the `{prefix}tfix restore` command."
                ).format(prefix=ctx.clean_prefix)
            )
        else:
            await ctx.send(_("Tournament successfully reloaded."))

    @tournamentfix.command(name="restore")
    async def tournamentfix_restore(self, ctx: commands.Context):
        """
        Try to restore a lost tournament.

        If the bot suddenly tells you there's no tournament setup, that means the bot failed \
reloading your tournament after a restart of the module/bot, but the data should still be on disk.

        This command attempts to run the process of reloading a tournament from disk.
        If there is already a tournament setup, this command won't work. You may then want to use \
`[p]tset reload`, which does the same thing, but unloads the tournament first.
        """
        guild = ctx.guild
        if guild.id in self.tournaments:
            await ctx.send(
                _(
                    "There's already a tournament setup on this server. If you want "
                    "to force reload, use `{prefix}tset reload` instead."
                ).format(prefix=ctx.clean_prefix)
            )
            return
        if not await self.data.guild(guild).tournament():
            await ctx.send(_("I can't find any saved tournament on disk."))
        try:
            self.tournaments[guild.id] = await self._restore_tournament(guild)
        except Exception as e:
            log.error(f"[Guild {guild.id}] Can't reload tournament from disk.", exc_info=e)
            await ctx.send(
                _(
                    "The tournament was found on disk, but it cannot be reloaded because of an "
                    "issue. If this persists, contact an administrator of the bot."
                ).format(prefix=ctx.clean_prefix)
            )
        else:
            await ctx.send(_("Tournament successfully loaded from disk."))

    @only_phase()
    @tournamentfix.command(name="hardreset")
    async def tournamentfix_hardreset(self, ctx: commands.Context):
        """
        Hard resets the tournament from memory.

        This will not ask questions or try to clean anything, just wipe what we have saved, both \
in memory and on disk.

        Use this only if nothing else works.
        Here are a few things to note when using this:
        - The bot will not try to call anything on the bracket, Challonge will remain untouched
        - You cannot setup (yet) a tournament past the start of registration/check-in (can't \
setup if the tournament is ongoing)
        - None of the channels will be removed or cleared
        - The participants will keep their roles and permissions
        - No message sent to anyone, the bot will just suddenly start to say "No tournament \
setup" on most commands. If your tournament is ongoing, it is your job to tell them.
        """
        guild = ctx.guild
        result = await prompt_yes_or_no(
            ctx,
            _(
                "This command is dangerous, type `{prefix}help tfix hardreset` for a detailed "
                "description of what the bot does or not, and the consequences.\n"
                "Do you want to continue?"
            ).format(prefix=ctx.clean_prefix),
        )
        if result is False:
            return
        try:
            self.tournaments[guild.id].stop_loop_task()
        except AttributeError:
            pass
        del self.tournaments[guild.id]
        await self.data.guild(guild).tournament.set({})
        log.info(f"[Guild {guild.id}] Hard reset of the tournament, requested by {ctx.author}.")
        await ctx.send(_("Everything was successfully internally reset."))

    @only_phase("ongoing")
    @tournamentfix.command(name="resetmatches")
    async def tournamentfix_resetmatches(self, ctx: commands.Context, try_delete: bool = False):
        """
        Resets the internal list of matches and participants.

        All ongoing matches will be lost. If the task is still active, all matches will be \
started again, with new channels.

        You can ask the bot to delete all channels too (categories \
excluded) by calling the command like this: `[p]tfix resetmatches yes`
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        if try_delete is True:
            channels = [x.channel for x in tournament.matches if x.channel is not None]
        tournament.matches = []
        tournament.participants = []
        await tournament.save()
        if try_delete is False:
            await ctx.send(_("Matches reset."))
            return
        await ctx.send(_("Matches reset. Starting channels deletion, this might take a while..."))
        failed = 0
        async with ctx.typing():
            for channel in channels:
                try:
                    await channel.delete()
                except discord.HTTPException:
                    failed += 1
        await ctx.send(
            _("Channels deleted.")
            + (_("\n{num} channels couldn't be deleted.").format(num=failed) if failed else "")
        )

    @only_phase("pending", "register", "awaiting")
    @tournamentfix.command(name="resetparticipants")
    async def tournamentfix_resetparticipants(
        self, ctx: commands.Context, try_remove: bool = False
    ):
        """
        Resets the list of participants during registration.

        All participants will be forgotten, but they keep their roles unless specified by calling \
`[p]tfix resetparticipants yes`.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        if try_remove is True:
            participants = tournament.participants if tournament.participant_role else []
        tournament.participants = []
        await tournament.save()
        if try_remove is False:
            await ctx.send(_("Participants reset."))
            return
        await ctx.send(_("Participants reset. Starting roles removal, this might take a while..."))
        failed_participants = 0
        async with ctx.typing():
            for participant in participants:
                try:
                    await participant.remove_roles(tournament.participant_role)
                except discord.HTTPException:
                    failed_participants += 1
        await ctx.send(
            _("Roles removed.")
            + (
                _("\n{num} participants couldn't have their role removed.").format(
                    num=failed_participants
                )
                if failed_participants
                else ""
            )
        )

    @only_phase("pending", "register", "awaiting")
    @tournamentfix.command(name="registerfromrole")
    async def tournamentfix_registerfromrole(self, ctx: commands.Context, *, role: discord.Role):
        """
        Registers everyone in a role.

        If there are members already registered in this role, they are ignored.
        Previous participants are kept, else you might want to run `[p]tfix resetparticipants` \
before.
        Running this after a check-in start will pre-check everyone, including already registered \
members of that role.
        """
        guild = ctx.guild
        if not role.members:
            await ctx.send(_("That role doesn't have any member."))
            return
        tournament = self.tournaments[guild.id]
        participants = tournament.participants
        to_register = [x for x in role.members if x not in participants]
        total = len(participants) + len(to_register)
        if tournament.limit and total > tournament.limit:
            await ctx.send(
                _(
                    "You want to register {register} members, but you're exceeding "
                    "the limit of participants ({total}/{limit})."
                ).format(register=len(to_register), total=total, limit=tournament.limit)
            )
            return
        pre_check = tournament.checkin_phase in ("ongoing", "done")
        if not to_register:
            if pre_check is False:
                await ctx.send(_("No new member to register."))
            else:
                for member in role.members:
                    participant = tournament.find_participant(discord_id=member.id)[1]
                    if participant is None:
                        continue
                    participant.checked_in = True
                await ctx.send(
                    _("No new participant. {len} participants from role checked in.").format(
                        len=len(role.members)
                    )
                )
            return
        failed = 0
        checked = 0
        async with ctx.typing():
            for member in to_register:
                try:
                    await tournament.register_participant(member, send_dm=False)
                except discord.HTTPException:
                    failed += 1
        if pre_check:
            for participant in [
                tournament.find_participant(discord_id=x.id)[1] for x in role.members
            ]:
                if participant is None:
                    continue
                participant.checked_in = True
                checked += 1
        await ctx.send(
            _(
                "Successfully registered {register} participants from role {role}.{failed}{check}"
            ).format(
                register=len(to_register) - failed,
                role=role.name,
                failed=_("\n{failed} members couldn't be registered.").format(failed=failed)
                if failed
                else "",
                check=_("\n{checked} existing participants checked in.").format(checked=checked)
                if checked
                else "",
            )
        )

    @only_phase()
    @tournamentfix.command(name="refresh")
    async def tournamentfix_refresh(self, ctx: commands.Context):
        """
        Refresh informations of the tournament from the bracket (Challonge)

        The bot only fetches tournament's informations on setup, never after, so you might want \
to use this if you changed something like the limit of participants.
        This does not reload the config (`[p]tset` commands), try `[p]tfix reload` instead.

        What can be changed:
        - Tournament name
        - Limit of participants

        What cannot be changed:
        - URL (the bot will return 404 if you do that, just re-setup)
        - Game name (config is based on this)
        - Start time (register and check-in start/end time is already calculated, too many cases \
to check if this changes, depending on the current phase)

        The rest is not used by the bot.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        data = await tournament.show(tournament.id)
        tournament.name = data["name"]
        tournament.limit = data["limit"]
        await ctx.send(_("Tournament name and limit of participants updated."))

    @only_phase("ongoing")
    @tournamentfix.command(name="pausetask")
    async def tournamentfix_pausetask(self, ctx: commands.Context):
        """
        Pause the background task launching matches, managing streams, AFKs and more...

        When you start the tournament, a background task will start, executing every 15 seconds.
        This task does the following things:
        - Refresh participants
        - Refresh matches
        - Launch matches
        - Check for AFK players
        - Delete inactive match channels
        - Assign streams
        - Save data on disk

        If you need to pause the bot from doing these things (like bracket changes), you can use \
this and restart later.

        :warning: To prevent disqualifying everyone for AFK when the task is resumed, AFK check \
will be disabled for all ongoing matches at the time of the task pause.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        if tournament.task is None:
            await ctx.send(_("The task isn't active right now."))
            return
        tournament.loop_task.cancel()
        await ctx.send(
            _("Loop task stopped. Resume it with `{prefix}tfix resumetask`").format(
                prefix=ctx.clean_prefix
            )
        )

    @only_phase("ongoing")
    @tournamentfix.command(name="resumetask")
    async def tournamentfix_resumetask(self, ctx: commands.Context):
        """
        Resume the background task, after a bug or a manual pause.

        See `[p]help tfix pausetask` for details about the task.
        Note that this may disable AFK checks for some matches to prevent seeing everyone removed.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        tournament.task_errors = 0
        failed = False
        try:
            async with ctx.typing():
                await tournament.cancel_timeouts()
                # dpy doesn't allow directly executing the coro, so I looked at the internals
                # Loop._injected contains Tournament, aka self, not including this will fail
                await tournament.loop_task.coro(tournament.loop_task._injected)
        except Exception as e:
            log.error(
                f"[Guild {guild.id}] User tried to resume the task, but it failed", exc_info=e
            )
            failed = True
        if failed is True or tournament.task_errors > 0:
            await ctx.send(
                _(
                    "I attempted to run the task once but it failed. The task will not be "
                    "resumed until the bug is resolved, check your logs or contact a bot admin.\n"
                    "You may want to try running `{prefix}tfix reload`."
                ).format(prefix=ctx.clean_prefix)
            )
        else:
            await asyncio.sleep(2)
            await tournament.start_loop_task()
            await ctx.send(_("The loop task was successfully resumed."))

    @only_phase("ongoing")
    @tournamentfix.command(name="runtaskonce")
    async def tournamentfix_runtaskonce(self, ctx: commands.Context):
        """
        Run the background task only once.

        See `[p]help tfix pausetask` for details about the task.
        Note that this may disable AFK checks for some matches to prevent seeing everyone removed.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        try:
            async with ctx.typing():
                await tournament.cancel_timeouts()
                # dpy doesn't allow directly executing the coro, so I looked at the internals
                # Loop._injected contains Tournament, aka self, not including this will fail
                await tournament.loop_task.coro(tournament.loop_task._injected)
        except Exception as e:
            log.error(
                f"[Guild {guild.id}] User tried to run the task once, but it failed", exc_info=e
            )
            await ctx.send(_("An error occured. Check your logs or contact a bot admin."))
        else:
            await ctx.tick()

    @only_phase("ongoing")
    @tournamentfix.command(name="unlock")
    async def tournamentfix_unlock(self, ctx: commands.Context):
        """
        A command that may unblock unresponding commands.

        The bot has an internal lock that prevents important commands such as `[p]win` or `[p]dq` \
from being run while the bot is updating the informations from Challonge, preventing conflicts.

        This is a task that is generally light, and that should time out after 10 seconds anyway.
        If you notice the bot simply doesn't respond for a while with some commands, try this \
command as the lock could have been left locked due to a bug.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        try:
            tournament.lock.release()
        except RuntimeError:
            await ctx.send(_("The lock is currently released."))
        else:
            await ctx.send(
                _("Interlal lock released. There may be an issue somewhere, pay attention.")
            )
