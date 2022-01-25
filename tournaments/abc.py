import discord
from abc import ABC
from typing import TYPE_CHECKING, Mapping, Optional
from .core import Tournament

if TYPE_CHECKING:
    from redbot.core.bot import Red
    from .tournaments import TournamentsConfig


class MixinMeta(ABC):
    """
    Base class for well behaved type hint detection with composite class.

    Basically, to keep developers sane when not all attributes are defined in each mixin.

    Credit to https://github.com/Cog-Creators/Red-DiscordBot (mod cog) for all mixin stuff.
    """

    def __init__(self):
        self.bot: Red
        self.data: TournamentsConfig
        self.tournaments: Mapping[int, Tournament]
        self.__version__: str

    def _restore_tournament(self, guild: discord.Guild, data: dict = None) -> Tournament:
        pass

    async def _get_settings(self, guild_id: int, config: Optional[str]) -> dict:
        pass
