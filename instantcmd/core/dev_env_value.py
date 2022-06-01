import logging
import asyncio

from typing import TYPE_CHECKING, TypeVar, Callable
from redbot.core import commands

from instantcmd.core import CodeSnippet
from instantcmd.core.exceptions import InvalidType

if TYPE_CHECKING:
    from redbot.core.bot import Red
    from redbot.core import Config

T = TypeVar("T")
DevEnvValue = Callable[[commands.Context], T]
log = logging.getLogger("red.laggron.instantcmd.core.listener")


class DevEnv:
    """
    A class representing a dev env value for Redbot's dev cog.
    """

    def __init__(self, function: DevEnvValue, name: str):
        if asyncio.iscoroutinefunction(function):
            raise InvalidType("Dev env functions cannot be async.")
        self.func = function
        self.name = name
        self.id = id(function)

    def __call__(self, ctx: commands.Context):
        self.func(ctx)


class DevEnvSnippet(CodeSnippet[DevEnv]):
    """
    Represents a dev env value
    """

    name = "dev env value"

    def __init__(self, bot: "Red", config: "Config", dev_env: DevEnv, source: str):
        super().__init__(bot, config, dev_env, source)

    def __str__(self) -> str:
        return self.value.func.__name__

    @property
    def verbose_name(self) -> str:
        return self.value.name

    @property
    def description(self) -> str:
        return f'Value "{self.verbose_name}" assigned to {self}'

    def register(self):
        self.bot.add_dev_env_value(self.value.name, self.value.func)
        log.debug(
            f"Registered dev env value with name {self.verbose_name} "
            f"and assigned to function {self}"
        )

    def unregister(self):
        self.bot.remove_dev_env_value(self.value.name)
        log.debug(f"Removed dev env value with name {self.verbose_name}")
