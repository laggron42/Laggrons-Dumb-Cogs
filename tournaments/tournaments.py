import discord
import logging

from abc import ABC
from typing import Optional

from redbot.core import commands
from redbot.core import checks
from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n

from .dataclass import ChallongeTournament
from .games import Games
from .registration import Registration
from .settings import Settings
from .streams import Streams

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
    Games, Registration, Settings, Streams, commands.Cog, metaclass=CompositeMetaClass
):

    default_guild_settings = {
        "credentials": {"username": None, "api": None},  # challonge login info
        "current_phase": None,  # possible values are "setup", "register", "checkin", "run"
        "delay": 10,
        "register": {"opening": 0, "closing": 10},
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
            "register_start": None,
            "register_stop": None,
            "checkin_start": None,
            "checkin_stop": None,
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
        self.data = Config.get_conf(cog_instance=self, identifier=260)
        self.tournament: Optional[ChallongeTournament] = None

        self.data.register_guild(**self.default_guild_settings)
        self.data.init_custom("GAME", 2)  # guild ID > game name
        self.data.register_custom("GAME", **self.default_game_settings)
