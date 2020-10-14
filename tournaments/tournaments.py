import logging
import asyncio
import achallonge
import discord
import shutil

from abc import ABC
from typing import Mapping
from laggron_utils.logging import close_logger

from redbot.core import commands
from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator, cog_i18n

from .objects import Tournament, Match, ChallongeTournament
from .games import Games
from .registration import Registration
from .settings import Settings
from .streams import Streams
from .troubleshooting import Troubleshooting

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

    __version__ = "1.0.0b3"
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
            achallonge.set_credentials(data["credentials"]["username"], data["credentials"]["api"])
            data.update(game_data)
            tournament = await ChallongeTournament.from_saved_data(
                guild, self.data, self.__version__, data["tournament"], data
            )
            if tournament.phase == "ongoing":
                tournament.start_loop_task()
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
        if hasattr(error, "original") and isinstance(
            error.original, achallonge.ChallongeException
        ):
            await ctx.send(
                _(
                    "Error from Challonge: {error}\n"
                    "If this problem persists, contact T.O.s or an admin of the bot."
                ).format(error=error.original.args[0])
            )
        else:
            await self.bot.on_command_error(ctx, error, unhandled_by_cog=True)

    def cog_unload(self):
        log.debug("Unloading cog...")

        # remove all handlers from the logger, this prevents adding
        # multiple times the same handler if the cog gets reloaded
        close_logger(log)

        # cancel all pending tasks
        def cancel(task: asyncio.Task):
            if task is not None:
                task.cancel()

        tournament: Tournament
        for tournament in self.tournaments.values():
            cancel(tournament.loop_task)
            # cancel(tournament.debug_task)
        self.registration_loop.stop()

        # remove ranking data
        shutil.rmtree(cog_data_path(self) / "ranking", ignore_errors=True)
