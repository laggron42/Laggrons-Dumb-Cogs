import asyncio
import achallonge
import discord
import logging
import re

from datetime import datetime, timedelta
from copy import deepcopy
from typing import List, Mapping, Optional

from redbot.core import commands
from redbot.core import checks
from redbot.core.i18n import Translator
from redbot.core.utils import menus
from redbot.core.utils.mod import mass_purge
from redbot.core.utils.chat_formatting import pagify

from .abc import MixinMeta
from .objects import Tournament, Match, Participant
from .utils import credentials_check, only_phase, mod_or_to, prompt_yes_or_no

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)

SCORE_RE = re.compile(r"(?P<score1>[0-9]+) *\- *(?P<score2>[0-9]+)")


class ScoreConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        score = SCORE_RE.match(argument)
        if score is None:
            raise commands.BadArgument(
                _(
                    "The given format is incorrect.\n"
                    "Please retry in the right format (3-0, 2-1, 3-2...)"
                )
            )
        return int(score.group("score1")), int(score.group("score2"))


class Games(MixinMeta):
    @commands.Cog.listener("on_message")
    async def check_for_channel_timeout(self, message: discord.Message):
        """
        Resets the timer if a message is sent in a set channel.
        """
        guild = message.guild
        if guild is None:
            return
        try:
            tournament: Tournament = self.tournaments[guild.id]
        except KeyError:
            return
        if tournament.phase != "ongoing":
            return
        i, match = tournament.find_match(channel_id=message.channel.id)
        if match is None:
            return
        elif match.status == "ongoing":
            if match.player1.id == message.author.id and match.player1.spoke is False:
                self.tournaments[guild.id].matches[i].player1.spoke = True
            elif match.player2.id == message.author.id and match.player2.spoke is False:
                self.tournaments[guild.id].matches[i].player2.spoke = True
        elif match.status == "finished":
            match.end_time = datetime.now(tournament.tz)

    @credentials_check
    @mod_or_to()
    @commands.command()
    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    async def start(self, ctx: commands.Context):
        """
        Starts the tournament.
        """
        guild = ctx.guild
        tournament: Tournament = self.tournaments.get(guild.id)
        if tournament is None:
            await ctx.send(
                _("There is no setup tournament. Use `{prefix}setup` first.").format(
                    prefix=ctx.clean_prefix
                )
            )
            return
        if tournament.register_phase == "ongoing":
            await ctx.send(_("Registration is still ongoing, please end it first."))
            return
        if tournament.checkin_phase == "ongoing":
            await ctx.send(_("Check-in is still ongoing, please end it first."))
            return
        need_upload = False
        if not tournament.participants:
            result = await prompt_yes_or_no(
                ctx,
                _(
                    ":warning: I don't have any participant internally registered.\n"
                    "You can still start the tournament, I will fetch the participants "
                    "from the bracket, if available, but the names must exactly match the "
                    "names of members in this server! I will disqualify the participants I "
                    "cannot find.\nKeep in mind you can register all members in a role with "
                    "`{prefix}tfix registerfromrole`.\nDo you want to continue?"
                ).format(prefix=ctx.prefix),
                timeout=60,
                delete_after=False,
            )
            if result is False:
                return
        if len(tournament.participants) > len([x for x in tournament.participants if x.player_id]):
            result = await prompt_yes_or_no(
                ctx,
                _(
                    ":warning: Some participants do not have a player ID assigned.\n"
                    "This may be because the bot failed seeding/uploading after the end of "
                    "registrations or check-in, or this is manual and you forgot to upload the "
                    "participants with `{prefix}upload`.\nYou should try the previous command "
                    "again before continuing, or some participants will be lost.\n"
                    "Do you want to continue?"
                ).format(prefix=ctx.prefix),
                timeout=60,
                delete_after=False,
            )
            if result is False:
                return
        else:
            not_uploaded = len(
                list(filter(None, [x._player_id is not None for x in tournament.participants]))
            )
            if 0 < not_uploaded < len(tournament.participants):
                need_upload = True

        async def seed_and_upload():
            await tournament.seed_participants()
            await tournament.add_participants()

        async def open_channels():
            channels = list(filter(None, [tournament.queue_channel, tournament.scores_channel]))
            for channel in channels:
                await channel.set_permissions(
                    tournament.participant_role,
                    read_messages=True,
                    send_messages=True,
                    reason=_("Tournament starting..."),
                )

        async def start():
            await tournament.start()
            tournament.phase = "ongoing"
            tournament.register_message = None
            await tournament._get_top8()

        async def launch_sets():
            await tournament.launch_sets()
            await tournament.start_loop_task()
            await tournament.save()

        tasks = [
            (_("Start the tournament"), start),
            (_("Open text channels"), open_channels),
            (_("Send messages"), tournament.send_start_messages),
            (_("Launch sets"), launch_sets),
        ]
        if need_upload:
            tasks.insert(0, (_("Seed and upload"), seed_and_upload))
        message: discord.Message = None
        embed = discord.Embed(title=_("Starting the tournament..."))
        embed.description = _("Game: {game}\n" "URL: {url}").format(
            game=tournament.game, url=tournament.url
        )
        async with tournament.lock:
            pass  # don't update scores while cache is being updated

        async def update_embed(index: int, failed: bool = False):
            nonlocal message
            text = ""
            for i, task in enumerate(tasks):
                task = task[0]
                if index > i:
                    text += f":white_check_mark: {task}\n"
                elif i == index:
                    if failed:
                        text += f":warning: {task}\n"
                    else:
                        text += f":arrow_forward: **{task}**\n"
                else:
                    text += f"*{task}*\n"
            if message is not None:
                embed.set_field_at(
                    0,
                    name=_("Progression"),
                    value=text,
                    inline=False,
                )
                await message.edit(embed=embed)
            else:
                embed.add_field(
                    name=_("Progression"),
                    value=text,
                    inline=False,
                )
                message = await ctx.send(embed=embed)

        error_mapping = {
            "422": _(
                ":information_source: A 422 error can mean multiple things:\n"
                "- There are not enough participants on Challonge. Check the bracket, and "
                "use `{prefix}upload` to try sending the participants again (seeding reset).\n"
                "- You enabled the check-in on Challonge. Check the participants on "
                "Challonge, or disable this option."
            ).format(prefix=ctx.clean_prefix),
        }
        await update_embed(0)
        for i, task in enumerate(tasks):
            task = task[1]
            try:
                await task()
            except achallonge.ChallongeException as e:
                await update_embed(i, True)
                error = error_mapping.get(e.args[0].split()[0])
                if error:
                    await ctx.send(
                        _(
                            "__Error from Challonge: {error}__\n{error_msg}\n\n"
                            "If this problem persists, contact T.O.s or an admin of the bot."
                        ).format(error=e.args[0], error_msg=error, prefix=ctx.clean_prefix)
                    )
                    return
                raise
            except Exception as e:
                log.error(
                    f"[Guild {ctx.guild.id}] Error when starting tournament. Coro: {task}",
                    exc_info=e,
                )
                await update_embed(i, True)
                # if it was a direct error from challonge, message would be different
                # we tell them so users don't bother looking into challonge issues
                # (unless challonge responded with incorrect data we can't handle)
                await ctx.send(
                    _(
                        "An error occured when starting the tournament (most likely not "
                        "related to Challonge). Check your logs or contact a bot admin."
                    )
                )
                return
            else:
                await update_embed(i + 1)
        await ctx.send(_("The tournament has now started!"))

    @only_phase("ongoing", "finished")
    @mod_or_to()
    @commands.command()
    @commands.guild_only()
    async def end(self, ctx: commands.Context):
        """
        Ends the current tournament.
        """
        guild = ctx.guild
        tournament: Tournament = self.tournaments[guild.id]
        if any(x.status == "ongoing" for x in tournament.matches):
            await ctx.send(_("There are still ongoing matches."))
            return
        i = 0
        channels = list(
            filter(
                None,
                [
                    tournament.checkin_channel,
                    tournament.queue_channel,
                    tournament.register_channel,
                    tournament.scores_channel,
                    tournament.lag_channel,
                ],
            )
        )
        categories = tournament.winner_categories + tournament.loser_categories
        temp_channels = [x for x in [y.text_channels for y in categories]]
        members = tournament.participants
        failed = {
            "categories": [],
            "temp_channels": [],
            "channels": [],
            "members": [],
        }

        async def stop_tournament():
            tournament.cancel()
            if tournament.phase != "finished":
                await tournament.stop()

        async def clear_channels():
            nonlocal failed, i
            # This isn't actually two weeks ago to allow some wiggle room on API limits
            two_weeks_ago = datetime.utcnow() - timedelta(days=14, minutes=-5)
            for channel in channels:
                try:
                    messages = await channel.history(limit=None, after=two_weeks_ago).flatten()
                    if messages:
                        await mass_purge(messages, channel)
                    if tournament.game_role:
                        await channel.set_permissions(
                            tournament.game_role, read_messages=True, send_messages=False
                        )
                    await channel.set_permissions(tournament.participant_role, send_messages=False)
                except discord.HTTPException as e:
                    log.warning(
                        f"[Guild {ctx.guild.id}] Failed editing channel "
                        f"{channel.name} with ID {channel.id}. (tournament ending)",
                        exc_info=e,
                    )
                    failed["channels"].append(channel)
                else:
                    i += 1

        async def delete_channels():
            nonlocal failed, i
            for category in categories:
                for channel in category.text_channels:
                    try:
                        await channel.delete(reason=_("Tournament ending"))
                    except discord.HTTPException as e:
                        log.warn(
                            f"[Guild {guild.id}] Failed deleting channel "
                            f"{channel.name} with ID {channel.id}. (tournament ending)",
                            exc_info=e,
                        )
                        failed["temp_channels"].append(channel)
                    else:
                        i += 1
                try:
                    await category.delete(reason=_("Tournament ending"))
                except discord.HTTPException as e:
                    log.warn(
                        f"[Guild {guild.id}] Failed deleting category "
                        f"{category.name} with ID {category.id}. (tournament ending)",
                        exc_info=e,
                    )
                    failed["categories"].append(category)
                else:
                    i += 1

        async def remove_roles():
            nonlocal i
            for member in members:
                try:
                    await member.remove_roles(
                        tournament.participant_role, reason=_("Tournament ending")
                    )
                except discord.HTTPException as e:
                    log.warn(
                        f"[Guild {guild.id}] Failed removing participant role from "
                        f"{str(member)} with ID {member.id}. (tournament ending)",
                        exc_info=e,
                    )
                    failed["members"].append(member)
                else:
                    i += 1

        tasks = [
            (_("Stopping the tournament"), stop_tournament, None),
            (_("Clearing and closing channels"), clear_channels, len(channels)),
            (_("Deleting channels"), delete_channels, len(temp_channels) + len(categories)),
            (_("Removing roles"), remove_roles, len(members)),
        ]
        message: discord.Message = None
        embed = discord.Embed(title=_("Ending the tournament..."))
        embed.description = _(
            "{participants} participants\nLasted for {time} *(based on expected start time)*"
        ).format(
            participants=len(tournament.participants),
            time=str(datetime.now(tournament.tz) - tournament.tournament_start).split(".")[0],
        )
        async with tournament.lock:
            pass  # don't update scores while cache is being updated

        async def update_message(errored=False):
            nonlocal message
            text = ""
            for local_index, task in enumerate(tasks):
                total = task[2]
                task = task[0]
                if index > local_index:
                    text += f":white_check_mark: {task}\n"
                elif local_index == index:
                    if total:
                        task += f" ({i}/{total})"
                    if errored:
                        text += f":warning: {task}\n"
                    else:
                        text += f":arrow_forward: **{task}**\n"
                else:
                    text += f"*{task}*\n"
            if message is not None:
                embed.set_field_at(
                    0,
                    name=_("Progression"),
                    value=text,
                    inline=False,
                )
                await message.edit(embed=embed)
            else:
                embed.add_field(
                    name=_("Progression"),
                    value=text,
                    inline=False,
                )
                message = await ctx.send(embed=embed)

        async def _update_message():
            while True:
                await update_message()
                await asyncio.sleep(0.5)

        index = 0
        try:
            # this task will keep updating the content of a message
            update_message_task = self.bot.loop.create_task(_update_message())
            for index, task in enumerate(tasks):
                await asyncio.sleep(0.5)
                try:
                    await task[1]()
                except achallonge.ChallongeException as e:
                    if index == 0:
                        log.warning(
                            f"[Guild {ctx.guild.id}] Can't end tournament. Someone probably ended "
                            "the tournament manually. Others functions will still "
                            "be executed for clearing the server.",
                            exc_info=e,
                        )
                        continue
                    update_message_task.cancel()
                    await update_message(True)
                    raise
                except Exception as e:
                    log.error(
                        f"[Guild {ctx.guild.id}] Error when ending tournament. Coro: {task}",
                        exc_info=e,
                    )
                    update_message_task.cancel()
                    await update_message(True)
                    await ctx.send(_("An error occured when ending the tournament."))
                    return
                else:
                    i = 0
            await self.data.guild(guild).tournament.set({})
            del self.tournaments[guild.id]
            index += 1
            await update_message()
        finally:
            update_message_task.cancel()
        message = _("Tournament ended.")
        messages = {
            "categories": _("Failed deleting the following categories:"),
            "temp_channels": _("Failed deleting the following channels:"),
            "channels": _("Failed clearing and closing the following channels:"),
            "members": _("Failed removing roles to the following members:"),
        }
        errored = False
        for kind, objects in failed.items():
            if not objects:
                continue
            if isinstance(objects[0], discord.CategoryChannel):
                text = ", ".join(x.mention for x in objects)
            else:
                text = ", ".join(x.mention for x in objects)
            message += f"\n\n{messages[kind]}\n{text}"
            errored = True
        if errored:
            message += _("\n\nCheck your console or logs for more informations.")
        await ctx.send_interactive(pagify(message))
        if tournament.announcements_channel:
            # TODO: actually show top 8
            await tournament.announcements_channel.send(
                _(
                    "The tournament is now ended, congratulations to all participants!\n"
                    "Results and ranking: {url}"
                ).format(url=tournament.url)
            )

    @only_phase("ongoing", "finished")
    @mod_or_to()
    @commands.command()
    @commands.guild_only()
    async def resetbracket(self, ctx: commands.Context):
        """
        Resets the bracket and stops the bot's activity.
        """
        if not ctx.channel.permissions_for(ctx.guild.me).add_reactions:
            await ctx.send(_('I need the "Add reactions" permission.'))
            return
        tournament = self.tournaments[ctx.guild.id]
        result = await prompt_yes_or_no(
            ctx,
            _(
                ":warning: **Warning!**\n"
                "If you continue, the entire progression will be lost, and the bot will roll "
                "back to its previous state. Then you will be able to start again with `{prefix}"
                "start`.\n**The matches __cannot__ be recovered!** Do you want to continue?"
            ).format(prefix=ctx.clean_prefix),
        )
        if result is False:
            return
        tournament.cancel()
        await tournament.reset()
        message = _("The tournament has been reset.")
        if tournament.matches:
            message += _(
                "\nStarting channels deletion, this may take a while... "
                "Please wait for this to be done before trying to restart."
            )
        await ctx.send(message)
        tournament.phase = "pending"
        [x.reset() for x in tournament.participants]
        tournament.streamers = []
        if not tournament.matches:
            return
        async with ctx.typing():
            for match in tournament.matches:
                await match.force_end()
            await tournament._clear_categories()
        if tournament.matches:
            await ctx.send(_("Channels cleared."))
        tournament.matches = []
        await tournament.save()

    @mod_or_to()
    @commands.command()
    @commands.guild_only()
    async def reset(self, ctx: commands.Context):
        """
        Resets the current tournament from the bot.
        """
        guild = ctx.guild
        if not ctx.channel.permissions_for(guild.me).add_reactions:
            await ctx.send(_('I need the "Add reactions" permission.'))
            return
        try:
            tournament = self.tournaments[guild.id]
        except KeyError:
            await ctx.send(_("There's no tournament setup on this server."))
            return
        if tournament.phase == "ongoing":
            await ctx.send(
                _("The tournament is ongoing. Please use `{prefix}resetbracket` first.").format(
                    prefix=ctx.clean_prefix
                )
            )
            return
        if tournament.participants:
            result = await prompt_yes_or_no(
                ctx,
                _(
                    ":warning: **Warning!**\n"
                    "If you continue, the participants registered will be lost. Then you will be "
                    "able to configure a new tournament with `{prefix}setup`.\n"
                    "**The participants __cannot__ be recovered!** Do you want to continue?"
                ).format(prefix=ctx.clean_prefix),
            )
            if result is False:
                return
        tournament.cancel()
        del self.tournaments[guild.id]
        await self.data.guild(guild).tournament.set({})
        await ctx.send(_("Tournament removed!"))

    @only_phase("pending", "register", "awaiting")
    @mod_or_to()
    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def upload(self, ctx: commands.Context, force: str = None):
        """
        Upload the participants to the bracket, and seed if possible.

        If you set braacket informations, the bot will seed participants based on this.

        Previously added participants in the bracket will be kept with their seeding. However, if \
you want the bot to override the previous list of participants, type `[p]upload --force`
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        force = force == "--force"
        message = None
        if not tournament.participants:
            await ctx.send(_(":warning: No participant registered."))
            return
        if tournament.checkin_phase == "ongoing":
            message = _(
                "Check-in is still ongoing. Participants not checked yet won't be uploaded."
            )
        elif tournament.checkin_phase == "pending":
            message = _("Check-in was not done. All participants will be uploaded.")
        elif force:
            message = _(
                "Using `--force` will clear the previous list of participants and replace "
                "it with the bot's internal list. Any seeding done on the bracket will be lost."
            )
        if message:
            result = await prompt_yes_or_no(
                ctx, f":warning: {message}\n" + _("Do you want to continue?")
            )
            if result is False:
                return
        error_mapping = {
            "422": _(
                ":information_source: A 422 error when uploading participants probably means "
                "the limit of participants was hit.\nDid the bot register too many participants? "
                "Or did someone edit the limit? Check the settings on Challonge."
            ),
        }
        seeded = tournament.ranking["league_name"] and tournament.ranking["league_id"]
        try:
            async with ctx.typing():
                await tournament.seed_participants(tournament.checkin_phase == "done")
        except Exception as e:
            log.error(f"[Guild {ctx.guild.id}] Failed seeding participants.", exc_info=e)
            result = await prompt_yes_or_no(
                ctx,
                _(
                    "An error occured while seeding participants. "
                    "Check your logs or contact an admin of the bot.\n"
                    "Would you like to continue without seeding?"
                ),
                delete_after=False,
            )
            if result is False:
                return
            seeded = False
        try:
            async with ctx.typing():
                added = await tournament.add_participants(force=force)
        except achallonge.ChallongeException as e:
            error = error_mapping.get(e.args[0].split()[0])
            if error:
                await ctx.send(
                    _(
                        "__Error from Challonge: {error}__\n{error_msg}\n\n"
                        "If this problem persists, contact T.O.s or an admin of the bot."
                    ).format(error=e.args[0], error_msg=error, prefix=ctx.clean_prefix)
                )
                return
            raise
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            log.error(f"[Guild {ctx.guild.id}] Failed uploading participants.", exc_info=e)
            await ctx.send(
                _(
                    "Uploading the participants to the bracket failed. This issue is not due "
                    "to seeding or Challonge. Contact an admin of the bot for details.\n"
                    ":information_source: You can manually add participants on the bracket "
                    "as long as the names matches their exact Discord name (Username#1234), "
                    "and the bot will fetch everyone back when you start the tournament (but "
                    "will disqualify the ones with an invalid name)."
                )
            )
        else:
            if not added:
                await ctx.send(
                    _(
                        "There was no new participant to upload. If you want to "
                        "enforce a new seeding, type `{prefix}upload --force`."
                    ).format(prefix=ctx.clean_prefix)
                )
                return
            text = _("{len} participants successfully seeded{upload} to the bracket!").format(
                len=added, upload=_(" and uploaded") if seeded else ""
            )
            if added == len(tournament.participants):
                if seeded:
                    # looks like it was the initial upload (or forced),
                    # so we display infos for a full seeding
                    base_elo = min([x.elo for x in tournament.participants])
                    generator = (
                        i for i, x in enumerate(tournament.participants, 1) if x.elo == base_elo
                    )
                    try:
                        position = next(generator)
                        # check a second time to make sure more than 1 participant are on base elo
                        next(generator)
                    except StopIteration:
                        pass
                    else:
                        text += _(
                            "\nParticipants are not seeded starting at position {pos}."
                        ).format(pos=position)
            else:
                text += _(
                    "\nSince there were other participants in the bracket, the new participants "
                    "were appended at the end instead of potentially overriding a manual "
                    "seeding.\nYou can force a full seeding with `{prefix}upload --force`."
                ).format(prefix=ctx.clean_prefix)
            await ctx.send(text)

    @only_phase("ongoing")
    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def win(self, ctx: commands.Context, *, score: ScoreConverter):
        """
        Set the score of your set. To be used by the winner.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        scores_channel = tournament.scores_channel
        player = tournament.find_participant(discord_id=ctx.author.id)[1]
        if player is None:
            await ctx.send(_("You are not a member of this tournament."))
            return
        if player.match is None:
            await ctx.send(_("You don't have any ongoing match."))
            return
        if player.match.status != "ongoing":
            await ctx.send(
                _(
                    "Your match has not started yet.\n"
                    "You're either awaiting for a stream, or an error occured internally. "
                    "You can ask a T.O. for a manual score setting."
                )
            )
            return
        if scores_channel is not None and scores_channel.id != ctx.channel.id:
            await ctx.send(
                _("You have to use this command in {channel}.").format(
                    channel=scores_channel.mention
                )
            )
            return
        if player.match.channel and (
            player.match.start_time + timedelta(minutes=5)
        ) > datetime.now(tournament.tz):
            await ctx.send(
                _(
                    "You need to wait for 5 minutes at least after the beginning of your "
                    "match before being able to set your score. T.O.s can bypass this by "
                    "setting the score manually on the bracket."
                )
            )
            return
        if score == (0, 0):
            await ctx.send(
                _(
                    "That's a quite special score you've got there dude, you gotta tell "
                    "me how to win without playing, I'm interested..."
                )
            )
            return
        if score[0] == score[1]:
            await ctx.send(
                _(
                    "Hmm... So you're telling me there is a tie *but* you're somehow still "
                    "the winner of your match? Review the formatting of your score."
                )
            )
            return
        if score[1] > score[0]:
            # command used by winner, highest score first
            score = score[::-1]
        # after second thought, checking the score based on BO3/BO5 is a bad idea
        # there are plenty of cases where a set could end with a lower score (bracket slowed down)
        # I'll leave the code here, uncomment if you want a strict score check
        #
        # limit = 5 if player.match.is_bo5 else 3
        # mode = _("(BO5)") if player.match.is_bo5 else _("(BO3)")
        # if sum(score) > limit:
        #     await ctx.send(
        #         _("The score does not follow the format of this set {mode}.\n").format(mode=mode)
        #         + _(":arrow_forward: sum should not be greater than {num}").format(num=limit)
        #     )
        #     return
        # if max(score) != limit // 2 + 1:
        #     await ctx.send(
        #         _("The score does not follow the format of this set {mode}.\n").format(mode=mode)
        #         + _(":arrow_forward: highest score should be {num}").format(num=limit // 2 + 1)
        #     )
        #     return
        if ctx.author.id == player.match.player2.id:
            score = score[::-1]  # player1-player2 format
        async with tournament.lock:
            pass  # don't update scores while cache is being updated
        await player.match.end(*score)
        await ctx.tick()

    @only_phase("ongoing")
    @mod_or_to()
    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 1, commands.BucketType.user)
    async def setscore(
        self,
        ctx: commands.Context,
        set: Optional[int],
        winner: discord.Member,
        score: ScoreConverter,
    ):
        """
        Set the score of a set. To be used by a T.O.

        You need to give the winner of the set, followed by its score.

        If the command is used in a channel for a set, this will be the set used by default. \
Else you can specify the set you want to update as the first argument.

        Examples:
        - `[p]setscore @Blite 2-1`
        - `[p]setscore 147 @Lorinato 3-1`
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        if set is not None:
            match = tournament.find_match(match_set=str(set))[1]
        else:
            match = tournament.find_match(channel_id=ctx.channel.id)[1]
        player = tournament.find_participant(discord_id=winner.id)[1]
        if player is None:
            await ctx.send(_("The winner is not a member of this tournament."))
            return
        if match is None:
            await ctx.send(
                _(
                    "I don't see any match here. Provide the set number as the first argument, "
                    "or use this command inside a channel for a set (see `{prefix}help setscore`)."
                ).format(prefix=ctx.clean_prefix)
            )
            return
        if match.status == "finished":
            await ctx.send(_("This match is already finished."))
            return
        if player.id not in (match.player1.id, match.player2.id):
            await ctx.send(
                _("The winner isn't part of the match {set}.").format(
                    set=match.channel.mention if match.channel else f"#{match.set}"
                )
            )
            return
        if winner.id == match.player2.id:
            score = score[::-1]  # player1-player2 format
        await match.end(*score)
        await ctx.tick()

    @only_phase("ongoing")
    @commands.command(aliases=["ff"])
    @commands.guild_only()
    async def forfeit(self, ctx: commands.Context):
        """
        Forfeit your current match.

        This will set a score of (-1 0)
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        player: Participant
        try:
            player = next(filter(lambda x: x.id == ctx.author.id, tournament.participants))
        except StopIteration:
            await ctx.send(_("You are not a member of this tournament."))
            return
        if player.match is None:
            await ctx.send(_("You don't have any ongoing match."))
            return
        result = await prompt_yes_or_no(
            ctx, _("Are you sure you want to forfeit this match?"), timeout=20
        )
        if result is False:
            return
        async with tournament.lock:
            pass  # don't update scores while cache is being updated
        await player.match.forfeit(player)
        await ctx.tick()

    @only_phase("ongoing")
    @commands.command(aliases=["dq"])
    @commands.guild_only()
    async def disqualify(self, ctx: commands.Context):
        """
        Disqualify yourself from the tournament.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        player: Participant
        try:
            player = next(filter(lambda x: x.id == ctx.author.id, tournament.participants))
        except StopIteration:
            await ctx.send(_("You are not a member of this tournament."))
            return
        result = await prompt_yes_or_no(
            ctx, _("Are you sure you want to stop the tournament?"), timeout=20
        )
        if result is False:
            return
        async with tournament.lock:
            pass  # don't update scores while cache is being updated
        await player.destroy()
        if player.match is not None:
            await player.match.disqualify(player)
        await ctx.tick()

    @only_phase("ongoing")
    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def lag(self, ctx: commands.Context):
        """
        Call TO's for a lag test.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        player = tournament.find_participant(discord_id=ctx.author.id)[1]
        if player is None:
            await ctx.send(_("You are not a participant in this tournament."))
            return
        match = player.match
        if match is None:
            await ctx.send(_("You don't have any ongoing match."))
            return
        if match.channel is None:
            target = _("check set #{set} between {player1} and {player2} (match in DM)").format(
                set=match.set, player1=match.player1.mention, player2=match.player2.mention
            )
        else:
            target = _("consult channel {channel}").format(channel=match.channel.mention)
        msg = _(":satellite: **Lag report** : TOs are invited to {target}.").format(
            channel=ctx.channel.mention, target=target
        )
        if tournament.tester_role:
            msg = f"{tournament.tester_role.mention} {msg}"
            mentions = discord.AllowedMentions(roles=[tournament.tester_role])
        else:
            mentions = None
        lag_channel = tournament.lag_channel or tournament.to_channel
        await lag_channel.send(msg, allowed_mentions=mentions)
        await ctx.send(_("TOs were called. Prepare a new arena for them..."))

    @only_phase("ongoing")
    @mod_or_to()
    @commands.command(hidden=True)
    @commands.guild_only()
    async def getset(self, ctx: commands.Context, set: Optional[int]):
        """
        Returns a set.
        Without a set number, to be used in a set channel.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        if set is None:
            match = tournament.find_match(channel_id=ctx.channel.id)[1]
        else:
            match = tournament.find_match(match_set=str(set))[1]
        await ctx.channel.send("```py\n{match}\n```".format(match=match))

    @only_phase("ongoing")
    @mod_or_to()
    @commands.command(hidden=True)
    @commands.guild_only()
    async def rmset(self, ctx: commands.Context, set: Optional[int]):
        """
        Delete the set in the bot's memory and his channel. It will be recreated if still ongoing on Challonge.
        Without a set number, to be used in a set channel.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        if set is None:
            match = tournament.find_match(channel_id=ctx.channel.id)[1]
        else:
            match = tournament.find_match(match_set=str(set))[1]
        if match is not None:
            tournament.matches.remove(match)
        await ctx.channel.delete()

    @only_phase()
    @commands.command(aliases=["rules"])
    @commands.guild_only()
    async def ruleset(self, ctx: commands.Context):
        """
        Show the tournament's ruleset.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        if not tournament.ruleset_channel:
            await ctx.send(_("There's no ruleset channel defined."))
        else:
            await ctx.send(
                _("Ruleset: {channel}").format(channel=tournament.ruleset_channel.mention)
            )

    @only_phase()
    @commands.command()
    @commands.guild_only()
    async def bracket(self, ctx: commands.Context):
        """
        Show the tournament's bracket.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        await ctx.send(_("Bracket: **{url}**").format(url=tournament.url))

    @only_phase()
    @commands.command()
    @commands.guild_only()
    async def stages(self, ctx: commands.Context):
        """
        Show the list of legal stages.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        if not tournament.stages:
            await ctx.send(_("There are no legal stages specified for this game."))
        else:
            text = _("__Legal stages:__") + "\n\n- " + "\n- ".join(tournament.stages)
            for page in pagify(text):
                await ctx.send(page)

    @only_phase()
    @commands.command(aliases=["counters"])
    @commands.guild_only()
    async def counterpicks(self, ctx: commands.Context):
        """
        Show the list of legal counter stages
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        if not tournament.counterpicks:
            await ctx.send(_("There are no counter stages specified for this game."))
        else:
            text = _("__Counters:__") + "\n\n- " + "\n- ".join(tournament.counterpicks)
            for page in pagify(text):
                await ctx.send(page)

    @mod_or_to()
    @only_phase("ongoing")
    @commands.command()
    @commands.guild_only()
    async def lsmatches(self, ctx: commands.Context):
        """
        List matches, sorted by their duration.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        # sort by suggested play order first
        matches = sorted(
            filter(lambda x: x.status == "ongoing", tournament.matches), key=lambda m: m.set
        )
        if not matches:
            await ctx.send(_("No match currently ongoing."))
            return
        # then chunk them per round
        rounds: Mapping[int, List[Match]] = {}
        for match in matches:
            try:
                rounds[match.round].append(match)
            except KeyError:
                rounds[match.round] = [match]
        del matches
        # sort the matches within a round by time
        rounds: List[List[Match]] = [
            sorted(x, key=lambda m: m.start_time) for x in rounds.values()
        ]
        # convert to strings
        rounds_str = {}
        for matches in rounds:
            text = ""
            for match in matches:
                text += _("Set {set} ({time}): {player1} vs {player2}\n").format(
                    set=match.channel.mention
                    if match.channel
                    else _("#{set} *in DM*").format(set=match.set),
                    time=str(match.duration).split(".")[0],
                    player1=match.player1.mention,
                    player2=match.player2.mention,
                )
            name = matches[0]._get_name()
            rounds_str[name] = text
        del rounds
        # format as embed fields, chunked as blocks with < 1500 characters
        # yes embeds can go further, but let's make things pretty okay?
        fields = [[]]
        total_char = 0
        for name, value in rounds_str.items():
            for i, page in enumerate(pagify(value, page_length=1024)):
                if i == 1:
                    name += _(" (continued)")
                text_len = len(name) + len(value)
                total_char += text_len
                if total_char >= 1500:
                    fields.append([{"name": name, "value": page}])
                    total_char = text_len
                else:
                    fields[-1].append({"name": name, "value": page})
        del rounds_str
        embeds = []
        embed = discord.Embed(
            title=_("List of ongoing matches"), description=_("Sorted by play order and duration")
        )
        embed.url = tournament.url
        for i, field_chunk in enumerate(fields, start=1):
            _embed = deepcopy(embed)
            for field in field_chunk:
                _embed.add_field(**field, inline=False)
            _embed.set_footer(text=_("Page {len}/{total}").format(len=i, total=len(fields)))
            embeds.append(_embed)
        await menus.menu(ctx, embeds, controls=menus.DEFAULT_CONTROLS)
