import asyncio
import logging
import achallonge
import discord
import shutil

from abc import ABC
from typing import Mapping
from datetime import datetime, timedelta
from laggron_utils.logging import close_logger

from redbot.core import commands
from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator, cog_i18n

from .objects import Tournament, ChallongeTournament
from .games import Games
from .registration import Registration
from .settings import Settings
from .streams import Streams
from .troubleshooting import Troubleshooting
from .utils import mod_or_to, only_phase

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """
    This allows the metaclass used for proper type detection to
    coexist with discord.py's metaclass

    Credit to https://github.com/Cog-Creators/Red-DiscordBot (mod cog) for all mixin stuff.
    """

    pass


@cog_i18n(_)
class Tournaments(
    Games,
    Registration,
    Settings,
    Streams,
    Troubleshooting,
    commands.Cog,
    metaclass=CompositeMetaClass,
):

    default_guild_settings = {
        "credentials": {"username": None, "api": None},  # challonge login info
        "current_phase": None,  # possible values are "setup", "register", "checkin", "run"
        "delay": 10,
        "time_until_warn": {  # warn brackets taking too much time
            "bo3": (25, 10),  # time until warn in channel, then time until warning the T.O.s
            "bo5": (30, 10),  # in minutes
        },
        "autostop_register": False,
        "register": {"opening": 0, "second_opening": 0, "closing": 10},
        "checkin": {"opening": 60, "closing": 15},
        "start_bo5": 0,
        "channels": {
            "announcements": None,
            "category": None,
            "checkin": None,
            "queue": None,
            "register": None,
            "scores": None,
            "stream": None,
            "to": None,
            "vipregister": None,
        },
        "roles": {"participant": None, "streamer": None, "to": None},
        "tournament": {
            "name": None,
            "game": None,
            "url": None,
            "id": None,
            "limit": None,
            "status": None,
            "tournament_start": None,
            "bot_prefix": None,
            "participants": [],
            "matches": [],
            "streamers": [],
            "winner_categories": [],
            "loser_categories": [],
            "phase": None,
            "register": None,
            "checkin": None,
            "ignored_events": None,
            "register_message_id": None,
            "checkin_reminders": [],
        },
    }

    default_game_settings = {
        "ruleset": None,
        "role": None,
        "baninfo": None,
        "ranking": {"league_name": None, "league_id": None},
        "stages": [],
        "counterpicks": [],
    }

    def __init__(self, bot: Red):
        self.bot = bot
        self.data = Config.get_conf(cog_instance=self, identifier=260, force_registration=True)
        self.tournaments: Mapping[int, Tournament] = {}

        self.data.register_guild(**self.default_guild_settings)
        self.data.init_custom("GAME", 2)  # guild ID > game name
        self.data.register_custom("GAME", **self.default_game_settings)

        # see registration.py
        self.registration_loop.start()
        self.registration_loop_task_errors = 0

    __version__ = "1.0.0"
    __author__ = ["retke (El Laggron)", "Wonderfall", "Xyleff"]

    @commands.command(hidden=True)
    async def tournamentsinfo(self, ctx: commands.Context):
        """
        Get informations about the cog.
        """
        await ctx.send(
            _(
                "Laggron's Dumb Cogs V3 - tournaments\n\n"
                "Version: {0.__version__}\n"
                "Authors: {0.__author__[0]}, {0.__author__[1]} and {0.__author__[2]}\n\n"
                "Github repository: https://github.com/retke/Laggrons-Dumb-Cogs/tree/v3\n"
                "Discord server: https://discord.gg/AVzjfpR\n"
                "Documentation: http://laggrons-dumb-cogs.readthedocs.io/\n"
                "Help translating the cog: https://crowdin.com/project/laggrons-dumb-cogs/\n\n"
                "Support my work on Patreon: https://www.patreon.com/retke"
            ).format(self)
        )

    async def _restore_tournament(self, guild: discord.Guild, data: dict = None) -> Tournament:
        if data is None:
            data = await self.data.guild(guild).all()
        game_data = await self.data.custom("GAME", guild.id, data["tournament"]["game"]).all()
        if data["tournament"]["tournament_type"] == "challonge":
            if any([x is None for x in data["credentials"].values()]):
                raise RuntimeError(
                    _("The challonge credentials were lost. Can't resume tournament.")
                )
            data.update(game_data)
            tournament = await ChallongeTournament.from_saved_data(
                self.bot, guild, self.data, self.__version__, data["tournament"], data
            )
            if tournament.phase == "ongoing":
                await tournament.start_loop_task()
            return tournament

    async def restore_tournaments(self):
        count = 0
        log.debug("Resuming tournaments...")
        for guild_id, data in (await self.data.all_guilds()).items():
            if not data["tournament"] or data["tournament"]["name"] is None:
                continue
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            try:
                tournament = await self._restore_tournament(guild, data)
            except Exception as e:
                log.error(f"[Guild {guild_id}] Failed to resume tournament.", exc_info=e)
            else:
                self.tournaments[guild.id] = tournament
                count += 1
        if count > 0:
            log.info(f"Resumed {count} tournaments.")
        else:
            log.info("No tournament had to be resumed.")

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        error_mapping = {
            "401": _(
                ":information_source: A 401 error probably means the Challonge user setup on "
                "this server does not have the permission to access the "
                "tournament, or the username and API key are now invalid.\n"
                "Share admin access to this user, or setup another one with "
                "`{prefix}challongeset` (and `{prefix}tfix reload` for reloading the config).\n\n"
            ).format(prefix=ctx.clean_prefix),
            "404": _(
                ":information_source: A 404 error probably means the tournament "
                "was deleted or moved (URL or host change).\n"
            ),
            "502": _(
                ":information_source: Challonge is being unstable, try again later. "
                "This error is (sadly) very common, so no need to worry.\n"
            ),
        }
        if hasattr(error, "original"):
            if isinstance(error.original, achallonge.ChallongeException):
                error_msg = error_mapping.get(error.original.args[0].split()[0]) or ""
                return await ctx.send(
                    _(
                        "__Error from Challonge: {error}__\n{error_msg}"
                        "If this problem persists, contact T.O.s or an admin of the bot."
                    ).format(error=error.original.args[0], error_msg=error_msg)
                )
            elif isinstance(error.original, asyncio.TimeoutError):
                return await ctx.send(_("Challonge timed out responding, try again later."))
        await self.bot.on_command_error(ctx, error, unhandled_by_cog=True)

    def cog_unload(self):
        log.debug("Unloading cog...")

        # remove all handlers from the logger, this prevents adding
        # multiple times the same handler if the cog gets reloaded
        close_logger(log)

        tournament: Tournament
        for tournament in self.tournaments.values():
            tournament.stop_loop_task()
        self.registration_loop.stop()

        # remove ranking data
        shutil.rmtree(cog_data_path(self) / "ranking", ignore_errors=True)

    # this is a temporary command existing because of an annoying bug I still can't find
    # working hard on this, looking for a fix as fast as possible
    # made this command for the tournaments that run until then
    @only_phase("ongoing")
    @mod_or_to()
    @commands.command(hidden=True)
    @commands.guild_only()
    async def fixmatches(self, ctx: commands.Context):
        """
        Find and patch some potentially broken matches.

        This command exists because of an unresolved bug and should not stay for long, hopefully.
        """
        tournament = self.tournaments[ctx.guild.id]
        async with tournament.lock:
            # we don't want to start the matches twice
            # *or maybe the lock is the source of the bug*
            pass
        # potentially broken matches
        pending_matches = [
            x
            for x in tournament.matches
            if x.status == "pending" and x.channel and x.on_hold is False
        ]
        if not pending_matches:
            await ctx.send("No broken match found.")
            return
        async with ctx.typing():
            for match in pending_matches:
                await match._start()
                match.checked_dq = True
                match.start_time = datetime.now(tournament.tz) - timedelta(minutes=5)
        await ctx.send(
            f"Patched {len(pending_matches)} matches (AFK check disabled):\n"
            f"{' '.join(x.channel.mention for x in pending_matches)}"
        )
