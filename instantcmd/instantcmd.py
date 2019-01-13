# InstantCommands by retke, aka El Laggron
# Idea by Malarne

import discord
import asyncio  # for coroutine checks
import traceback
import textwrap
import logging

from typing import TYPE_CHECKING
from redbot.core import commands
from redbot.core import checks
from redbot.core import Config
from redbot.core.utils.predicates import MessagePredicate
from redbot.core.utils.chat_formatting import pagify

if TYPE_CHECKING:
    from .loggers import Log

BaseCog = getattr(commands, "Cog", object)


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
        self.sentry = None
        self.data = Config.get_conf(self, 260)

        def_global = {"commands": {}, "enable_sentry": None, "updated_body": False}
        self.data.register_global(**def_global)
        self.listeners = {}

        # these are the availables values when creating an instant cmd
        self.env = {"bot": self.bot, "discord": discord, "commands": commands, "checks": checks}
        # resume all commands and listeners
        bot.loop.create_task(self.resume_commands())

    __author__ = "retke (El Laggron)"
    __version__ = "1.0.0"
    __info__ = {
        "bot_version": "3.0.0b9",
        "description": "Command and listener maker from a code snippet through Discord",
        "hidden": False,
        "install_msg": (
            "Thanks for installing instantcmd. Please check the wiki "
            "for all informations about the cog.\n"
            "https://laggrons-dumb-cogs.readthedocs.io/\n"
            "Everything you need to know about setting up the cog is here.\n\n"
            "Please keep in mind that you must know Python and discord.py for "
            "that cog. Try to create normal cogs if you don't already know how "
            "it works."
        ),
        "required_cogs": [],
        "requirements": [],
        "short": "Instant command maker",
        "tags": ["command", "listener", "code"],
    }

    def _set_log(self, sentry: "Log"):
        self.sentry = sentry
        global log
        log = logging.getLogger("laggron.instantcmd")

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
        exec(to_compile, self.env)
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
        else:
            self.bot.add_listener(function)
            self.listeners[function.__name__] = id(function)

    async def resume_commands(self):
        """
        Load all instant commands made.
        This is executed on load with __init__
        """

        _commands = await self.data.commands()
        for name, command_string in _commands.items():
            function = self.get_function_from_str(command_string, name)
            self.load_command_or_listener(function)

    # from DEV cog, made by Cog Creators (tekulvw)
    @staticmethod
    def cleanup_code(content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:-1])

        # remove `foo`
        return content.strip("` \n")

    @checks.is_owner()
    @commands.group(aliases=["instacmd", "instantcommand"])
    async def instantcmd(self, ctx):
        """Instant Commands cog management"""

        if not ctx.invoked_subcommand:
            await ctx.send_help()

    @instantcmd.command()
    async def create(self, ctx):
        """
        Instantly generate a new command from a code snippet.

        If you want to make a listener, give its name instead of the command name.
        """
        await ctx.send(
            "You're about to create a new command. \n"
            "Your next message will be the code of the command. \n\n"
            "If this is the first time you're adding instant commands, "
            "please read the wiki:\n"
            "<https://laggrons-dumb-cogs.readthedocs.io/instantcommands.html>"
        )
        pred = MessagePredicate.same_context(ctx)
        try:
            response = await self.bot.wait_for("message", timeout=900, check=pred)
        except asyncio.TimeoutError:
            await ctx.send("Question timed out.")
            return

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
                    await ctx.send("Error: That listener is already registered.")
                    return
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

        else:
            async with self.data.commands() as _commands:
                if function.__name__ in _commands:
                    await ctx.send("Error: That listener is already registered.")
                    return
            try:
                self.bot.add_listener(function)
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
                self.listeners[function.__name__] = id(function)
                async with self.data.commands() as _commands:
                    _commands[function.__name__] = function_string
                await ctx.send(f"The listener `{function.__name__}` was successfully added.")

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
                self.bot.remove_listener(FakeListener(self.listeners[command]), name=command)
            else:
                text = "command"
                self.bot.remove_command(command)
            _commands.pop(command)
        await ctx.send(f"The {text} `{command}` was successfully removed.")

    @instantcmd.command()
    async def info(self, ctx, command: str = None):
        """
        List all existing commands made using Instant Commands.

        If a command name is given and found in the Instant commands list, the code will be shown.
        """

        if not command:
            message = "List of instant commands:\n" "```Diff\n"
            _commands = await self.data.commands()

            for name, command in _commands.items():
                message += f"+ {name}\n"
            message += (
                "```\n"
                "*Hint:* You can show the command source code by typing "
                f"`{ctx.prefix}instacmd info <command>`"
            )

            if _commands == {}:
                await ctx.send("No instant command created.")
                return

            for page in pagify(message):
                await ctx.send(message)

        else:
            _commands = await self.data.commands()

            if command not in _commands:
                await ctx.send("Command not found.")
                return

            message = (
                f"Source code for `{ctx.prefix}{command}`:\n"
                + "```Py\n"
                + _commands[command]
                + "```"
            )
            for page in pagify(message):
                await ctx.send(page)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def instantcmdinfo(self, ctx, sentry: str = None):
        """
        Get informations about the cog.

        Type `sentry` after your command to modify its status.
        """
        current_status = await self.data.enable_sentry()
        status = lambda x: "enable" if x else "disable"

        if sentry is not None and "sentry" in sentry:
            await ctx.send(
                "You're about to {} error logging. Are you sure you want to do this? Type "
                "`yes` to confirm.".format(status(not current_status))
            )
            predicate = MessagePredicate.yes_or_no(ctx)
            try:
                await self.bot.wait_for("message", timeout=60, check=predicate)
            except asyncio.TimeoutError:
                await ctx.send("Request timed out.")
            else:
                if predicate.result:
                    await self.data.enable_sentry.set(not current_status)
                    if not current_status:
                        # now enabled
                        self.sentry.enable()
                        await ctx.send(
                            "Upcoming errors will be reported automatically for a faster fix. "
                            "Thank you for helping me with the development process!"
                        )
                    else:
                        # disabled
                        self.sentry.disable()
                        await ctx.send("Error logging has been disabled.")
                    log.info(
                        f"Sentry error reporting was {status(not current_status)}d "
                        "on this instance."
                    )
                else:
                    await ctx.send(
                        "Okay, error logging will stay {}d.".format(status(current_status))
                    )
                return

        message = (
            "Laggron's Dumb Cogs V3 - instantcmd\n\n"
            "Version: {0.__version__}\n"
            "Author: {0.__author__}\n"
            "Sentry error reporting: {1}d (type `{2}instantcmdinfo sentry` to change this)\n\n"
            "Github repository: https://github.com/retke/Laggrons-Dumb-Cogs/tree/v3\n"
            "Discord server: https://discord.gg/AVzjfpR\n"
            "Documentation: http://laggrons-dumb-cogs.readthedocs.io/\n\n"
            "Support my work on Patreon: https://www.patreon.com/retke"
        ).format(self, status(current_status), ctx.prefix)
        await ctx.send(message)

    # error handling
    def _set_context(self, data):
        self.sentry.client.extra_context(data)

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
        log.propagate = False  # let's remove console output for this since Red already handle this
        context = {
            "command": {
                "invoked": f"{ctx.author} (ID: {ctx.author.id})",
                "command": f"{ctx.command.name} (cog: {ctx.cog})",
                "arguments": ctx.kwargs,
            }
        }
        if ctx.guild:
            context["guild"] = f"{ctx.guild.name} (ID: {ctx.guild.id})"
        self.sentry.disable_stdout()  # remove console output since red also handle this
        log.error(
            f"Exception in command '{ctx.command.qualified_name}'.\n\n", exc_info=error.original
        )
        self.sentry.enable_stdout()  # re-enable console output for warnings
        self._set_context({})  # remove context for future logs

    # correctly unload the cog
    def __unload(self):
        log.debug("Cog unloaded from the instance.")

        # remove all handlers from the logger, this prevents adding
        # multiple times the same handler if the cog gets reloaded
        log.handlers = []
