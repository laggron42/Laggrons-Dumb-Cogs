import discord
import logging
import re

from redbot.core import commands
from redbot.core import checks
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify

from .abc import MixinMeta
from .dataclass import Tournament, Match
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
                    "Le format entré est incorrect.\n"
                    "Veuillez réessayer dans le bon format (3-0, 2-1, 3-2...)"
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
        match: Match
        try:
            i, match = next(
                filter(
                    lambda x: x[1].channel.id == message.channel.id, enumerate(tournament.matches)
                )
            )
        except StopIteration:
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
        Démarre le tournoi.
        """
        guild = ctx.guild
        tournament: Tournament = self.tournaments.get(guild.id)
        if tournament is None:
            await ctx.send(
                _("Il n'y a aucun tournoi en cours. Utilisez d'abord `{prefix}setup`.").format(
                    prefix=ctx.clean_prefix
                )
            )
            return
        # check for register status
        embed = discord.Embed(title=_("Lancement du tournoi..."))
        embed.description = _("Jeu: {game}\n" "URL: {url}").format(
            game=tournament.game, url=tournament.url
        )
        embed.add_field(
            name=_("Progression"),
            value=_("**Lancement...**\n*Envoi des messages*\n*Lancement des sets*"),
            inline=False,
        )
        message = await ctx.send(embed=embed)
        await tournament.start()
        embed.set_field_at(
            0,
            name=_("Progression"),
            value=_(
                ":white_check_mark: Lancement\n"
                "**Envoi des messages...**\n"
                "*Lancement des sets*"
            ),
            inline=False,
        )
        await message.edit(embed=embed)
        await tournament.send_start_messages()
        embed.set_field_at(
            0,
            name=_("Progression"),
            value=_(
                ":white_check_mark: Lancement\n"
                ":white_check_mark: Envoi des messages\n"
                "**Lancement des sets...**"
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
                    ":warning: Erreur lors du lancement des sets. Consultez les logs "
                    "pour plus d'informations."
                )
            )
            return
        embed.set_field_at(
            0,
            name=_("Progression"),
            value=_(
                ":white_check_mark: Lancement\n"
                ":white_check_mark: Envoi des messages\n"
                ":white_check_mark: Lancement des sets"
            ),
            inline=False,
        )
        await message.edit(embed=embed)
        tournament.start_loop_task()
        await ctx.send(_("Le tournoi est lancé !"))

    @only_phase("ongoing")
    @commands.command()
    async def win(self, ctx: commands.Context, *, score: ScoreConverter):
        """
        Règle le score de votre set. À utiliser par le gagnant.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        try:
            player = next(filter(lambda x: x.id == ctx.author.id, tournament.participants))
        except StopIteration:
            await ctx.send(_("Vous n'êtes pas participant au tournoi."))
            return
        if player.match is None:
            await ctx.send(_("Vous n'avez aucun match en cours."))
            return
        if ctx.author.id == player.match.player2.id:
            score = score[::-1]  # player1-player2 format
        # TODO: verify BO3/BO5 format
        # TODO: verify minimum time for a match
        await player.match.end(*score)
        await ctx.tick()

    @only_phase("ongoing")
    @commands.command()
    async def bracket(self, ctx: commands.Context):
        """
        Affiche le bracket du tournoi.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        await ctx.send(_("Bracket: **{url}**").format(url=tournament.url))

    @only_phase("ongoing")
    @commands.command()
    async def stages(self, ctx: commands.Context):
        """
        Affiche la liste des stages légaux.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        if not tournament.stages:
            await ctx.send(_("Il n'y a pas de stages légaux spécifiés pour ce jeu."))
        else:
            text = _("__Stages légaux :__") + "\n\n- " + "\n- ".join(tournament.stages)
            for page in pagify(text):
                await ctx.send(page)

    @only_phase("ongoing")
    @commands.command(aliases=["counters"])
    async def counterpicks(self, ctx: commands.Context):
        """
        Affiche la liste des counters.
        """
        guild = ctx.guild
        tournament = self.tournaments[guild.id]
        if not tournament.counterpicks:
            await ctx.send(_("Il n'y a pas de counters spécifiés pour ce jeu."))
        else:
            text = _("__Counters :__") + "\n\n- " + "\n- ".join(tournament.counterpicks)
            for page in pagify(text):
                await ctx.send(page)
