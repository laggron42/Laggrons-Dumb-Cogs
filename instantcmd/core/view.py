import logging
import discord

from typing import TYPE_CHECKING, Type

from instantcmd.core import CodeSnippet
from instantcmd.core.exceptions import InvalidType

if TYPE_CHECKING:
    from redbot.core.bot import Red
    from redbot.core import Config

log = logging.getLogger("red.laggron.instantcmd.core.message_component")


class ViewSnippet(CodeSnippet[Type[discord.ui.View]]):
    """
    Represents a message component that can be attached to a view

    Attributes
    ----------
    base: Type[discord.ui.Item]
        The type of item represented by this instance (button, select menu...)
    """

    name = "view"

    def __str__(self) -> str:
        return self.value.__name__

    @property
    def verbose_name(self) -> str:
        return str(self)

    @property
    def description(self) -> str:
        return f"{self.name.title()} {self}"

    # literally nothing is required other than saving the instance
    def register(self):
        pass

    def unregister(self):
        pass
