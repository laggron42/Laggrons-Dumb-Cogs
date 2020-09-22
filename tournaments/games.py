import discord
import logging
import re
import asyncio

from redbot.core import commands
from redbot.core import checks
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify
from redbot.core.utils.predicates import ReactionPredicate
from redbot.core.utils.menus import start_adding_reactions

from .abc import MixinMeta
from .dataclass import Tournament, Match, Participant
from .utils import credentials_check, only_phase

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
        return score.group("score1"), score.group("score2")


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
        if tournament.status != "ongoing":
            return
        i, match = tournament.find_match(channel_id=message.channel.id)
        if match is None:
            return
        if match.status == "finished" and not match.deletion_task.cancelled():
            match.reset_deletion_task()
        elif match.status == "ongoing":
            if match.player1.id == message.author.id and match.player1.spoke is False:
                self.tournaments[guild.id].matches[i].player1.spoke = True
            elif match.player2.id == message.author.id and match.player2.spoke is False:
                self.tournaments[guild.id].matches[i].player2.spoke = True

    @credentials_check
    @commands.command()
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
        # check for register status
        embed = discord.Embed(title=_("Starting the tournament..."))
        embed.description = _("Jeu: {game}\n" "URL: {url}").format(
            game=tournament.game, url=tournament.url
        )
        embed.add_field(
            name=_("Progression"),
            value=_("**Starting...**\n*Sending messages*\n*Launching sets*"),
            inline=False,
        )
        message = await ctx.send(embed=embed)
        await tournament.start()
        embed.set_field_at(
            0,
            name=_("Progression"),
            value=_(
                ":white_check_mark: Starting\n" "**Sending messages...**\n" "*Launching sets*"
            ),
            inline=False,
        )
        await message.edit(embed=embed)
        await tournament.send_start_messages()
        embed.set_field_at(
            0,
            name=_("Progression"),
            value=_(
                ":white_check_mark: Starting\n"
                ":white_check_mark: Sending messages\n"
                "**Launching sets...**"
            ),
            inline=False,
        )
        await message.edit(embed=embed)
        try:
            await tournament.launch_sets()
        except Exception as e:
            log.error(
                f"[Guild {guild.id}] Can't launch sets when starting tournament!", exc_info=e
            )
            await ctx.send(
                _(
                    ":warning: Error while launching sets, check your console "
                    "or logs for more informations."
                )
            )
            return
        embed.set_field_at(
            0,
            name=_("Progression"),
            value=_(
                ":white_check_mark: Starting\n"
                ":white_check_mark: Sending messages\n"
                ":white_check_mark: Launching sets"
            ),
            inline=False,
        )
        await message.edit(embed=embed)
        tournament.start_loop_task()
        await ctx.send(_("The tournament has now started!"))

    @only_phase("ongoing")
    @commands.command()
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
            tournament.stop_loop_task()
            await tournament.end()
            categories = tournament.winner_categories + tournament.loser_categories
            for category in categories:
                for channel in category.text_channels:
                    await channel.delete()
                await category.delete()
        await self.data.guild(guild).tournament.set({})
        del self.tournaments[guild.id]
        await ctx.send(_("Tournament ended."))

    @only_phase("ongoing")
    @commands.command()
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
        if scores_channel is not None:
            await ctx.send(
                _("You have to use this command in {channel}.").format(
                    channel=scores_channel.mention
                )
            )
            return
        if ctx.author.id == player.match.player2.id:
            score = score[::-1]  # player1-player2 format
        # TODO: verify BO3/BO5 format
        # TODO: verify minimum time for a match
        await player.match.end(*score)
        await ctx.tick()

    @only_phase("ongoing")
    @commands.command(aliases=["ff"])
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
        message = await ctx.send(_("Are you sure you want to forfeit this match?"))
        pred = ReactionPredicate.yes_or_no(message, ctx.author)
        try:
            await self.bot.wait_for("reaction_add", check=pred, timeout=20)
        except asyncio.TimeoutError:
            await ctx.send(_("Request timed out."))
            return
        if pred.result is True:
            await player.match.forfeit(player)
            await ctx.tick()
        else:
            await ctx.send(_("You are continuing this match."))

    @only_phase("ongoing")
    @commands.command(aliases=["dq"])
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
        message = await ctx.send(_("Are you sure you want to stop the tournament?"))
        pred = ReactionPredicate.yes_or_no(message, ctx.author)
        try:
            await self.bot.wait_for("reaction_add", check=pred, timeout=20)
        except asyncio.TimeoutError:
            await ctx.send(_("Request timed out."))
            return
        if pred.result is True:
            await player.destroy()
            if player.match is not None:
                await player.match.disqualify(player)
            await ctx.tick()
        else:
            await ctx.send(_("You are continuing this tournament."))

    @only_phase("ongoing")
    @commands.command()
    async def bracket(self, ctx: commands.Context):
        """
        Show the tournament's bracket.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        await ctx.send(_("Bracket: **{url}**").format(url=tournament.url))

    @only_phase("ongoing")
    @commands.command()
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
