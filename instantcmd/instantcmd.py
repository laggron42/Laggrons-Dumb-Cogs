# InstantCommands by retke, aka El Laggron
# Idea by Malarne

import discord
import asyncio
import traceback
import textwrap
import logging
import os
import sys

from redbot.core import commands
from redbot.core import checks
from redbot.core import Config
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.chat_formatting import pagify

from .utils import Listener

log = logging.getLogger("laggron.instantcmd")
log.setLevel(logging.DEBUG)

BaseCog = getattr(commands, "Cog", object)

# Red 3.0 backwards compatibility, thanks Sinbad
listener = getattr(commands.Cog, "listener", None)
if listener is None:

    def listener(name=None):
        return lambda x: x


class FakeListener:
    """
    A fake listener used to remove the extra listeners.

    This is needed due to how extra listeners works, and how the cog stores these.
    When adding a listener to the list, we get its ID. Then, when we need to remove\
    the listener, we call this fake class with that ID, so discord.py thinks this is\
    that listener.

    Credit to mikeshardmind for finding this solution. For more info, please look at this issue:
    https://github.com/Rapptz/discord.py/issues/1284
    """

    def __init__(self, idx):
        self.idx = idx

    def __eq__(self, function):
        return self.idx == id(function)


class InstantCommands(BaseCog):
    """
    Generate a new command from a code snippet, without making a new cog.

    Report a bug or ask a question: https://discord.gg/AVzjfpR
    Full documentation and FAQ: https://laggrons-dumb-cogs.readthedocs.io/instantcommands.html
    """

    def __init__(self, bot):
        self.bot = bot
        self.data = Config.get_conf(self, 260)

        def_global = {"commands": {}, "updated_body": False}
        self.data.register_global(**def_global)
        self.listeners = {}

        # these are the availables values when creating an instant cmd
        self.env = {"bot": self.bot, "discord": discord, "commands": commands, "checks": checks}
        # resume all commands and listeners
        bot.loop.create_task(self.resume_commands())
        self._init_logger()

    __author__ = ["retke (El Laggron)"]
    __version__ = "1.1.1"

    def _init_logger(self):
        log_format = logging.Formatter(
            f"%(asctime)s %(levelname)s {self.__class__.__name__}: %(message)s",
            datefmt="[%d/%m/%Y %H:%M]",
        )
        # logging to a log file
        # file is automatically created by the module, if the parent foler exists
        cog_path = cog_data_path(self)
        if cog_path.exists():
            log_path = cog_path / f"{os.path.basename(__file__)[:-3]}.log"
            file_handler = logging.FileHandler(log_path)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(log_format)
            log.addHandler(file_handler)

        # stdout stuff
        stdout_handler = logging.StreamHandler()
        stdout_handler.setFormatter(log_format)
        # if --debug flag is passed, we also set our debugger on debug mode
        if logging.getLogger("red").isEnabledFor(logging.DEBUG):
            stdout_handler.setLevel(logging.DEBUG)
        else:
            stdout_handler.setLevel(logging.INFO)
        log.addHandler(stdout_handler)
        self.stdout_handler = stdout_handler

    # def get_config_identifier(self, name):
    # """
    # Get a random ID from a string for Config
    # """

    # random.seed(name)
    # identifier = random.randint(0, 999999)
    # self.env["config"] = Config.get_conf(self, identifier)

    def get_function_from_str(self, command, name=None):
        """
        Execute a string, and try to get a function from it.
        """

        # self.get_config_identifier(name)
        to_compile = "def func():\n%s" % textwrap.indent(command, "  ")
        sys.path.append(os.path.dirname(__file__))
        exec(to_compile, self.env)
        sys.path.remove(os.path.dirname(__file__))
        result = self.env["func"]()
        if not result:
            raise RuntimeError("Nothing detected. Make sure to return a command or a listener")
        return result

    def load_command_or_listener(self, function):
        """
        Add a command to discord.py or create a listener
        """

        if isinstance(function, commands.Command):
            self.bot.add_command(function)
            log.debug(f"Added command {function.name}")
        else:
            if not isinstance(function, Listener):
                function = Listener(function, function.__name__)
            self.bot.add_listener(function.func)
            self.listeners[function.func.__name__] = (function.id, function.name)
            if function.name != function.func.__name__:
                log.debug(
                    f"Added listener {function.func.__name__} listening for the "
                    f"event {function.name} (ID: {function.id})"
                )
            else:
                log.debug(f"Added listener {function.name} (ID: {function.id})")

    async def resume_commands(self):
        """
        Load all instant commands made.
        This is executed on load with __init__
        """

        _commands = await self.data.commands()
        for name, command_string in _commands.items():
            function = self.get_function_from_str(command_string, name)
            self.load_command_or_listener(function)

    async def remove_commands(self):
        async with self.data.commands() as _commands:
            for command in _commands:
                if command in self.listeners:
                    # remove a listener
                    listener_id, name = self.listeners[command]
                    self.bot.remove_listener(FakeListener(listener_id), name=name)
                    log.debug(f"Removed listener {command} due to cog unload.")
                else:
                    # remove a command
                    self.bot.remove_command(command)
                    log.debug(f"Removed command {command} due to cog unload.")

    # from DEV cog, made by Cog Creators (tekulvw)
    @staticmethod
    def cleanup_code(content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:-1])

        # remove `foo`
        return content.strip("` \n")

    async def _ask_for_edit(self, ctx: commands.Context, kind: str) -> bool:
        msg = await ctx.send(
            f"That {kind} is already registered with InstantCommands. "
            "Would you like to replace it?"
        )
        pred = ReactionPredicate.yes_or_no(msg, ctx.author)
        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        try:
            await self.bot.wait_for("reaction_add", check=pred, timeout=30)
        except asyncio.TimeoutError:
            await ctx.send("Cancelled.")
            return False
        if not pred.result:
            await ctx.send("Cancelled.")
            return False
        return True

    @checks.is_owner()
    @commands.group(aliases=["instacmd", "instantcommand"])
    async def instantcmd(self, ctx):
        """Instant Commands cog management"""
        pass

    @instantcmd.command(aliases=["add"])
    async def create(self, ctx):
        """
        Instantly generate a new command from a code snippet.

        If you want to make a listener, give its name instead of the command name.
        You can upload a text file if the command is too long, but you should consider coding a\
            cog at this point.
        """

        async def read_from_file(msg: discord.Message):
            content = await msg.attachments[0].read()
            try:
                function_string = content.decode()
            except UnicodeDecodeError as e:
                log.error(f"Failed to decode file for instant command.", exc_info=e)
                await ctx.send(
                    ":warning: Failed to decode the file, all invalid characters will be replaced."
                )
                function_string = content.decode(errors="replace")
            finally:
                return self.cleanup_code(function_string)

        if ctx.message.attachments:
            function_string = await read_from_file(ctx.message)
        else:
            await ctx.send(
                "You're about to create a new command. \n"
                "Your next message will be the code of the command. \n\n"
                "If this is the first time you're adding instant commands, "
                "please read the wiki:\n"
                "<https://laggrons-dumb-cogs.readthedocs.io/instantcommands.html>"
            )
            pred = MessagePredicate.same_context(ctx)
            try:
                response: discord.Message = await self.bot.wait_for(
                    "message", timeout=900, check=pred
                )
            except asyncio.TimeoutError:
                await ctx.send("Question timed out.")
                return

            if response.content == "" and response.attachments:
                function_string = await read_from_file(response)
            else:
                function_string = self.cleanup_code(response.content)

        try:
            function = self.get_function_from_str(function_string)
        except Exception as e:
            exception = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            message = (
                f"An exception has occured while compiling your code:\n```py\n{exception}\n```"
            )
            for page in pagify(message):
                await ctx.send(page)
            return
        # if the user used the command correctly, we should have one async function

        if isinstance(function, commands.Command):
            async with self.data.commands() as _commands:
                if function.name in _commands:
                    response = await self._ask_for_edit(ctx, "command")
                    if response is False:
                        return
                    self.bot.remove_command(function.name)
                    log.debug(f"Removed command {function.name} due to incoming overwrite (edit).")
            try:
                self.bot.add_command(function)
            except Exception as e:
                exception = "".join(traceback.format_exception(type(e), e, e.__traceback__))
                message = (
                    "An expetion has occured while adding the command to discord.py:\n"
                    f"```py\n{exception}\n```"
                )
                for page in pagify(message):
                    await ctx.send(page)
                return
            else:
                async with self.data.commands() as _commands:
                    _commands[function.name] = function_string
                await ctx.send(f"The command `{function.name}` was successfully added.")
                log.debug(f"Added command {function.name}")

        else:
            if not isinstance(function, Listener):
                function = Listener(function, function.__name__)
            async with self.data.commands() as _commands:
                if function.func.__name__ in _commands:
                    response = await self._ask_for_edit(ctx, "listener")
                    if response is False:
                        return
                    listener_id, listener_name = self.listeners[function.func.__name__]
                    self.bot.remove_listener(FakeListener(listener_id), name=listener_name)
                    del listener_id, listener_name
                    log.debug(
                        f"Removed listener {function.name} due to incoming overwrite (edit)."
                    )
            try:
                self.bot.add_listener(function.func, name=function.name)
            except Exception as e:
                exception = "".join(traceback.format_exception(type(e), e, e.__traceback__))
                message = (
                    "An expetion has occured while adding the listener to discord.py:\n"
                    f"```py\n{exception}\n```"
                )
                for page in pagify(message):
                    await ctx.send(page)
                return
            else:
                self.listeners[function.func.__name__] = (function.id, function.name)
                async with self.data.commands() as _commands:
                    _commands[function.func.__name__] = function_string
                if function.name != function.func.__name__:
                    await ctx.send(
                        f"The listener `{function.func.__name__}` listening for the "
                        f"event `{function.name}` was successfully added."
                    )
                    log.debug(
                        f"Added listener {function.func.__name__} listening for the "
                        f"event {function.name} (ID: {function.id})"
                    )
                else:
                    await ctx.send(f"The listener {function.name} was successfully added.")
                    log.debug(f"Added listener {function.name} (ID: {function.id})")

    @instantcmd.command(aliases=["del", "remove"])
    async def delete(self, ctx, command_or_listener: str):
        """
        Remove a command or a listener from the registered instant commands.
        """
        command = command_or_listener
        async with self.data.commands() as _commands:
            if command not in _commands:
                await ctx.send("That instant command doesn't exist")
                return
            if command in self.listeners:
                text = "listener"
                function, name = self.listeners[command]
                self.bot.remove_listener(FakeListener(function), name=name)
            else:
                text = "command"
                self.bot.remove_command(command)
            _commands.pop(command)
        await ctx.send(f"The {text} `{command}` was successfully removed.")

    @instantcmd.command(name="list")
    async def _list(self, ctx):
        """
        List all existing commands made using Instant Commands.

        If a command name is given and found in the Instant commands list, the code will be shown.
        """
        message = "List of instant commands:\n" "```Diff\n"
        _commands = await self.data.commands()
        for name, command in _commands.items():
            message += f"+ {name}\n"
        message += (
            "```\n"
            "You can show the command source code by typing "
            f"`{ctx.prefix}instacmd source <command>`"
        )
        if _commands == {}:
            await ctx.send("No instant command created.")
            return
        for page in pagify(message):
            await ctx.send(message)

    @instantcmd.command()
    async def source(self, ctx: commands.Context, command: str):
        """
        Show the code of an instantcmd command or listener.
        """
        _commands = await self.data.commands()
        if command not in _commands:
            await ctx.send("Command not found.")
            return
        message = (
            f"Source code for `{ctx.prefix}{command}`:\n" + "```Py\n" + _commands[command] + "```"
        )
        for page in pagify(message):
            await ctx.send(page)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def instantcmdinfo(self, ctx):
        """
        Get informations about the cog.
        """
        await ctx.send(
            "Laggron's Dumb Cogs V3 - instantcmd\n\n"
            "Version: {0.__version__}\n"
            "Author: {0.__author__}\n"
            "Github repository: https://github.com/retke/Laggrons-Dumb-Cogs/tree/v3\n"
            "Discord server: https://discord.gg/AVzjfpR\n"
            "Documentation: http://laggrons-dumb-cogs.readthedocs.io/\n\n"
            "Support my work on Patreon: https://www.patreon.com/retke"
        ).format(self)

    @listener()
    async def on_command_error(self, ctx, error):
        if not isinstance(error, commands.CommandInvokeError):
            return
        if not ctx.command.cog_name == self.__class__.__name__:
            # That error doesn't belong to the cog
            return
        async with self.data.commands() as _commands:
            if ctx.command.name in _commands:
                log.info(f"Error in instant command {ctx.command.name}.", exc_info=error.original)
                return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(
                "I need the `Add reactions` and `Manage messages` in the "
                "current channel if you want to use this command."
            )
        log.removeHandler(self.stdout_handler)  # remove console output since red also handle this
        log.error(
            f"Exception in command '{ctx.command.qualified_name}'.\n\n", exc_info=error.original
        )
        log.addHandler(self.stdout_handler)  # re-enable console output for warnings

    # correctly unload the cog
    def __unload(self):
        self.cog_unload()

    def cog_unload(self):
        log.debug("Unloading cog...")

        async def unload():
            # removes commands and listeners
            await self.remove_commands()

            # remove all handlers from the logger, this prevents adding
            # multiple times the same handler if the cog gets reloaded
            log.handlers = []

        # I am forced to put everything in an async function to execute the remove_commands
        # function, and then remove the handlers. Using loop.create_task on remove_commands only
        # executes it after removing the log handlers, while it needs to log...
        self.bot.loop.create_task(unload())
