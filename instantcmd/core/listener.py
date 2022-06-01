import logging

from typing import TYPE_CHECKING, Callable, Awaitable

from instantcmd.core import CodeSnippet

if TYPE_CHECKING:
    from redbot.core.bot import Red
    from redbot.core import Config

Awaitable = Callable[..., Awaitable]
log = logging.getLogger("red.laggron.instantcmd.core.listener")


class Listener:
    """
    A class representing a discord.py listener.
    """

    def __init__(self, function: Awaitable, name: str):
        self.func = function
        self.name = name
        self.id = id(function)

    def __call__(self, *args, **kwargs):
        self.func(*args, **kwargs)


class ListenerSnippet(CodeSnippet[Listener]):
    """
    Represents a listener
    """

    name = "listener"

    def __init__(self, bot: "Red", config: "Config", listener: Listener, source: str):
        super().__init__(bot, config, listener, source)

    def __str__(self) -> str:
        return self.value.func.__name__

    @property
    def verbose_name(self) -> str:
        return self.value.name

    @property
    def description(self) -> str:
        return f"Listens for event {self.verbose_name}"

    def register(self):
        self.bot.add_listener(self.value.func, name=self.value.name)
        if self.value.name == self.value.func.__name__:
            log.debug(f"Registered listener {self}")
        else:
            log.debug(f"Registered listener {self} listening for event {self.value.name}")

    def unregister(self):
        self.bot.remove_listener(self.value.func, name=self.value.name)
        if self.value.name == self.value.func.__name__:
            log.debug(f"Removed listener {self}")
        else:
            log.debug(f"Removed listener {self} listening for event {self.value.name}")
