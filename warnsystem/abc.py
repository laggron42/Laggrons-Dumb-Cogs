from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redbot.core import Config
    from redbot.core.bot import Red
    from .cache import MemoryCache
    from .api import API


class MixinMeta(ABC):
    """
    Base class for well behaved type hint detection with composite class.

    Basically, to keep developers sane when not all attributes are defined in each mixin.

    Credit to https://github.com/Cog-Creators/Red-DiscordBot (mod cog) for all mixin stuff.
    """

    def __init__(self):
        self.bot: Red
        self.data: Config
        self.cache: MemoryCache
        self.api: API
