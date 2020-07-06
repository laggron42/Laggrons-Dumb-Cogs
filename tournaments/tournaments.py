import discord
import logging

from abc import ABC

from redbot.core import commands
from redbot.core import checks
from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n

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
    def __init__(self, bot: Red):
        self.bot = bot
        self.data = Config.get_conf(cog_instance=self, identifier=260)
