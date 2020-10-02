from abc import ABC
import discord
from typing import TYPE_CHECKING, Mapping
from .objects import Tournament

if TYPE_CHECKING:
    from redbot.core import Config
    from redbot.core.bot import Red


class MixinMeta(ABC):
    """
    Base class for well behaved type hint detection with composite class.

    Basically, to keep developers sane when not all attributes are defined in each mixin.

    Credit to https://github.com/Cog-Creators/Red-DiscordBot (mod cog) for all mixin stuff.
    """

    def __init__(self):
        self.bot: Red
        self.data: Config
        self.tournaments: Mapping[int, Tournament]
        self.__version__: str

    def _restore_tournament(self, guild: discord.Guild, data: dict = None) -> Tournament:
        pass
