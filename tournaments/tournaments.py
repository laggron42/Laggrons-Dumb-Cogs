import asyncio
import logging
import achallonge
import discord
import shutil

from abc import ABC
from typing import Mapping, Optional
from laggron_utils.logging import close_logger

from redbot.core import commands
from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.config import Group
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator, cog_i18n

from .objects import Tournament, ChallongeTournament
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


class TournamentsConfig(Config):
    """
    Just a shortcut for custom groups.

    This solution is NOT recommanded for Red. Object proxying is recommanded instead.
    However, I'm annoying af and want proper type hints, which is not possible with a proxy,
    so I go for the ugly method, sorry
    """

    def settings(self, *args, **kwargs) -> Group:
        return self.custom("SETTINGS", *args, *kwargs)


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

    default_global = {
        "data_version": "0.0"  # will be edited after config update, current version is 1.0
    }

    default_guild_settings = {
        "credentials": {"username": None, "api": None},  # challonge login info
        "tournament": {
            "config": None,
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

    default_settings = {
        "delay": None,
        "time_until_warn": {  # warn brackets taking too much time
            "bo3": None,  # time until warn in channel, then time until warning the T.O.s
            "bo5": None,  # in minutes
        },
        "autostop_register": None,
        "register": {"opening": None, "second_opening": None, "closing": None},
        "checkin": {"opening": None, "closing": None},
        "start_bo5": None,
        "channels": {
            "announcements": None,
            "ruleset": None,
            "category": None,
            "queue": None,
            "register": None,
            "stream": None,
            "to": None,
            "lag": None,
        },
        "roles": {
            "participant": None,
            "player": None,
            "streamer": None,
            "tester": None,
            "to": None,
        },
        "baninfo": None,
        "ranking": {"league_name": None, "league_id": None},
        "stages": None,
        "counterpicks": None,
    }

    def __init__(self, bot: Red):
        self.bot = bot
        self.data: TournamentsConfig = TournamentsConfig.get_conf(
            cog_instance=self, identifier=260, force_registration=True
        )
        self.tournaments: Mapping[int, Tournament] = {}

        self.data.register_global(**self.default_global)
        self.data.register_guild(**self.default_guild_settings)
        self.data.init_custom("SETTINGS", 2)  # guild ID > config name
        self.data.register_custom("SETTINGS", **self.default_settings)

        # see registration.py
        self.registration_loop.start()
        self.registration_loop_task_errors = 0

        # Useful dev tools
        try:
            self.bot.add_dev_env_value("tm_cog", lambda ctx: self)
            self.bot.add_dev_env_value("tm", lambda ctx: self.tournaments.get(ctx.guild.id))
        except AttributeError:
            if self.bot.get_cog("Dev") is not None:
                log.info(
                    "Customizable dev environment not available. Update to Red 3.4.6 if "
                    'you want the "tm" and "tm_cog" values available with the dev commands.'
                )
        except Exception as e:
            log.error("Couldn't load dev env values.", exc_info=e)

    __version__ = "1.1.15"
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

    async def _get_settings(self, guild_id: int, config: Optional[str]) -> dict:
        def overwrite_dict(default: dict, new: dict) -> dict:
            for key, value in new.items():
                if key not in default:
                    continue
                if value is None:
                    new[key] = default[key]
                elif isinstance(value, dict):
                    new[key] = overwrite_dict(default[key], value)
            return new

        cog_default = {
            "delay": 600,
            "time_until_warn": {  # warn brackets taking too much time
                "bo3": (
                    1500,
                    600,
                ),  # time until warn in channel, then time until warning the T.O.s
                "bo5": (1800, 600),  # in minutes
            },
            "autostop_register": False,
            "register": {"opening": 0, "second_opening": 0, "closing": 600},
            "checkin": {"opening": 3600, "closing": 900},
            "start_bo5": 0,
            "stages": [],
            "counterpicks": [],
        }
        credentials = await self.data.guild_from_id(guild_id).credentials()
        default = await self.data.settings(guild_id, None).all()
        default["credentials"] = credentials
        default = overwrite_dict(cog_default, default)
        if config is None:
            return default
        config = await self.data.settings(guild_id, config).all()
        config["credentials"] = credentials
        return overwrite_dict(default, config)

    async def _restore_tournament(
        self, guild: discord.Guild, tournament_data: dict = None
    ) -> Tournament:
        if tournament_data is None:
            tournament_data = await self.data.guild(guild).tournament()
        data = await self._get_settings(guild.id, tournament_data["config"])
        if tournament_data["tournament_type"] == "challonge":
            if any([x is None for x in data["credentials"].values()]):
                raise RuntimeError(
                    _("The challonge credentials were lost. Can't resume tournament.")
                )
            tournament = await ChallongeTournament.from_saved_data(
                self.bot, guild, self.data, self.__version__, tournament_data, data
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
                tournament = await self._restore_tournament(guild, data["tournament"])
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

        # Remove dev env values
        try:
            self.bot.remove_dev_env_value("tm")
            self.bot.remove_dev_env_value("tm_cog")
        except AttributeError:
            pass

        tournament: Tournament
        for tournament in self.tournaments.values():
            tournament.stop_loop_task()
        self.registration_loop.stop()

        # remove ranking data
        shutil.rmtree(cog_data_path(self) / "ranking", ignore_errors=True)
