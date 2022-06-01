import logging

from typing import TYPE_CHECKING, TypeVar

from redbot.core import commands

from instantcmd.core import CodeSnippet

if TYPE_CHECKING:
    from redbot.core.bot import Red
    from redbot.core import Config

Command = TypeVar("Command", bound=commands.Command)
log = logging.getLogger("laggron.instantcmd.core.command")


class CommandSnippet(CodeSnippet[Command]):
    """
    Represents a text command from discord.ext.commands
    """

    name = "command"

    def __init__(self, bot: "Red", config: "Config", command: Command, source: str):
        super().__init__(bot, config, command, source)

    def __str__(self) -> str:
        return self.value.callback.__name__

    @property
    def verbose_name(self) -> str:
        return self.value.name

    @property
    def description(self) -> str:
        return f"Command {self.verbose_name}"

    def register(self):
        self.bot.add_command(self.value)
        log.debug(f"Registered command {self}")

    def unregister(self):
        if self.bot.remove_command(self.value.name) is not None:
            log.debug(f"Removed command {self}")
        else:
            log.warning(f"Tried to remove command {self} but it was not registered")
