import achallonge
import discord
import logging
import re

from datetime import datetime, timedelta
from copy import deepcopy

from redbot.core import commands
from redbot.core import checks
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify
from redbot.core.utils import menus

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
            await tournament.seed_participants_and_upload()

        async def start():
            tournament.phase = "ongoing"
            await tournament.start()
            await tournament._get_top8()

        async def launch_sets():
            await tournament.launch_sets()
            tournament.start_loop_task()
            await tournament.save()

        tasks = [
            (_("Start the tournament"), start),
            (_("Send messages"), tournament.send_start_messages),
            (_("Launch sets"), launch_sets),
        ]
        if need_upload:
            tasks.insert(0, (_("Seed and upload"), seed_and_upload()))
        message: discord.Message = None
        embed = discord.Embed(title=_("Starting the tournament..."))
        embed.description = _("Game: {game}\n" "URL: {url}").format(
            game=tournament.game, url=tournament.url
        )

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
                    0, name=_("Progression"), value=text, inline=False,
                )
                await message.edit(embed=embed)
            else:
                embed.add_field(
                    name=_("Progression"), value=text, inline=False,
                )
                message = await ctx.send(embed=embed)

        await update_embed(0)
        for i, task in enumerate(tasks):
            task = task[1]
            try:
                await task()
            except achallonge.ChallongeException:
                await update_embed(i, True)
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

    @only_phase("ongoing")
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
        async with ctx.typing():
            tournament.cancel()
            await tournament.stop()
            categories = tournament.winner_categories + tournament.loser_categories
            failed_category = False
            try:
                for category in categories:
                    for channel in category.text_channels:
                        await channel.delete()
                    await category.delete()
            except discord.HTTPException as e:
                log.warning(
                    f"[Guild {ctx.guild.id}] Failed to remove some channels/categories.\n"
                    f"Last channel: {channel} Last category: {category}",
                    exc_info=e,
                )
                failed_category = True
            failed = []
            if tournament.participant_role:
                channels = [
                    tournament.checkin_channel,
                    tournament.queue_channel,
                    tournament.register_channel,
                    tournament.scores_channel,
                ]
                for channel in channels:
                    try:
                        await channel.set_permissions(
                            tournament.participant_role, send_messages=False
                        )
                    except discord.HTTPException as e:
                        log.warning(
                            f"[Guild {ctx.guild.id}] Failed to edit channel {channel.id}",
                            exc_info=e,
                        )
                        failed.append(channel)
        await self.data.guild(guild).tournament.set({})
        del self.tournaments[guild.id]
        message = _("Tournament ended.")
        if failed_category:
            message += _(
                "\n\nFailed when clearing the channels and categories. See logs for details."
            )
        if failed:
            message += _("\n\nFailed closing the following channels:\n- ")
            message += "\n- ".join([x.mention for x in failed])
        await ctx.send(message)

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
        if tournament.phase in ("register", "checkin"):
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
    async def upload(self, ctx: commands.Context):
        """
        Upload the participants to the bracket, and seed if possible.

        If you set braacket informations, the bot will seed participants based on this.
        Previously added participants in the bracket will be overwritten.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
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
        if message:
            result = await prompt_yes_or_no(
                ctx, f":warning: {message}\n" + _("Do you want to continue?")
            )
            if result is False:
                return
        try:
            async with ctx.typing():
                await tournament.seed_participants_and_upload(tournament.checkin_phase == "done")
        except achallonge.ChallongeException:
            raise
        except Exception as e:
            log.error(f"[Guild {ctx.guild.id}] Failed seeding/uploading participants.", exc_info=e)
            await ctx.send(
                _(
                    "An error occured while seeding/uploading. "
                    "Check your logs or contact an admin of the bot."
                )
            )
        else:
            text = _("{len} participants successfully seeded and uploaded to the bracket!").format(
                len=len(tournament.participants)
            )
            if tournament.ranking["league_name"] and tournament.ranking["league_id"]:
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
                    text += _("\nParticipants are not seeded starting at position {pos}.").format(
                        pos=position
                    )
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
        try:
            player = next(filter(lambda x: x.id == ctx.author.id, tournament.participants))
        except StopIteration:
            await ctx.send(_("You are not a member of this tournament."))
            return
        if player.match is None:
            await ctx.send(_("You don't have any ongoing match."))
            return
        if scores_channel is not None and scores_channel.id != ctx.channel.id:
            await ctx.send(
                _("You have to use this command in {channel}.").format(
                    channel=scores_channel.mention
                )
            )
            return
        if (player.match.start_time + timedelta(minutes=5)) > datetime.now(tournament.tz):
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
        await player.match.end(*score)
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
        await tournament.to_channel.send(msg, allowed_mentions=mentions)
        await ctx.send(_("TOs were called. Prepare a new arena for them..."))

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

    @only_phase("ongoing")
    @commands.command()
    @commands.guild_only()
    async def bracket(self, ctx: commands.Context):
        """
        Show the tournament's bracket.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        await ctx.send(_("Bracket: **{url}**").format(url=tournament.url))

    @only_phase("ongoing")
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

    @only_phase("ongoing")
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
        embed = discord.Embed(
            title=_("List of ongoing matches"), description=_("Sorted by duration")
        )
        embed.url = tournament.url
        text = ""
        match: Match
        for match in sorted(
            filter(lambda x: x.status == "ongoing", tournament.matches), key=lambda x: x.start_time
        ):
            duration = datetime.now(tournament.tz) - match.start_time
            text += _("Set {set} ({time}): {player1} vs {player2}\n").format(
                set=match.channel.mention
                if match.channel
                else _("#{set} *in DM*").format(set=match.set),
                time=duration.strftime("%H:%M:%S"),
                player1=match.player1.mention,
                player2=match.player2.mention,
            )
        pages = list(pagify(text, page_length=1024))
        embeds = []
        for i, page in enumerate(pages):
            _embed = deepcopy(embed)
            _embed.add_field(name="\u200B", value=page, inline=False)
            _embed.set_footer(text=_("Page {i}/{total}").format(i=i, total=len(pages)))
            embeds.append(_embed)
        await menus.menu(ctx, embeds, controls=menus.DEFAULT_CONTROLS)
