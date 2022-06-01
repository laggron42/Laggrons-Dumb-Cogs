# InstantCommands by retke, aka El Laggron
# Idea by Malarne

import discord
import asyncio
import traceback
import logging

from typing import TypeVar, Type, Optional, List, Tuple, Iterator
from discord.ui import View
from laggron_utils.logging import close_logger

from redbot.core import commands
from redbot.core import checks
from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.chat_formatting import pagify

from instantcmd.utils import Listener
from instantcmd.components import CodeSnippetsList
from instantcmd.code_runner import cleanup_code, get_code_from_str, find_matching_type
from instantcmd.core import CodeSnippet, CommandSnippet, ListenerSnippet

log = logging.getLogger("red.laggron.instantcmd")
T = TypeVar("T")
CODE_SNIPPET = "CODE_SNIPPET"

# --- Glossary ---
#
# "code", "snippet" or "code snippet"
#   Refers to a block of code written by the user that returns an object
#   like a command or a listener that we will register. They are usually
#   objects derived from `instantcmd.core.core.CodeSnippet`


class InstantCommands(commands.Cog):
    """
    Generate a new command from a code snippet, without making a new cog.

    Documentation https://laggron.red/instantcommands.html
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.data = Config.get_conf(self, 260)

        self.data.init_custom(CODE_SNIPPET, 2)
        self.data.register_custom(CODE_SNIPPET, code=None, enabled=True, version=1)

        self.code_snippets: List[CodeSnippet] = []

    __author__ = ["retke (El Laggron)"]
    __version__ = "2.0.0"

    def load_code_snippet(self, code: CodeSnippet):
        """
        Register a code snippet
        """
        if code.enabled == False:
            log.debug(f"Skipping snippet {code} as it is disabled.")
            return
        try:
            code.register()
        except Exception:
            log.error(f"Failed to register snippet {code}", exc_info=True)
        else:
            code.registered = True

    async def load_all_code_snippets(self):
        """
        Reload all code snippets saved.
        This is executed on cog load.
        """
        for code in self.code_snippets:
            self.load_code_snippet(code)

    def unload_code_snippet(self, code: CodeSnippet):
        """
        Unregister a code snippet
        """
        if code.registered == False:
            return
        try:
            code.unregister()
        except Exception:
            log.error(f"Failed to unregister snippet {code}", exc_info=True)
        else:
            code.registered = False

    async def unload_all_code_snippets(self):
        """
        Unload all code snippets saved.
        This is executed on cog unload.
        """
        dev_values = await self.data.dev_values()
        for name, code in dev_values.items():
            try:
                function = self.get_function_from_str(code, name)
            except Exception as e:
                log.exception("An exception occurred while trying to resume dev value %s", name)
            else:
                self.bot.add_dev_env_value(name, function)
                log.debug(f"Added dev value %s", name)
        for code in self.code_snippets:
            self.unload_code_snippet(code)

    def get_code_snippets(
        self,
        enabled: Optional[bool] = True,
        registered: Optional[bool] = True,
        type: Optional[Type[CodeSnippet]] = None,
    ) -> Iterator[CodeSnippet]:
        """
        Get all saved code snippets.

        Parameters
        ----------
        enabled: Optional[bool]
            If `True`, only return enabled code snippets. Defaults to `True`.
        registered: Optional[bool]
            If `True`, only return registered code snippets (excluding the ones that failed to
            load). Defaults to `True`.
        type: Optional[Type[CodeSnippet]]
            Filter the results by the given type.

        Returns
        -------
        Iterator[CodeSnippet]
            An iterator of the results.
        """
        for code in self.code_snippets:
            if enabled and not code.enabled:
                continue
            if registered and not code.registered:
                continue
            if type and not isinstance(code, type):
                continue
            yield code

    async def _ask_for_edit(self, ctx: commands.Context, code: CodeSnippet) -> bool:
        msg = await ctx.send(
            f"That {code} is already registered with InstantCommands. "
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

    async def _read_from_file(self, ctx: commands.Context, msg: discord.Message) -> str:
        content = await msg.attachments[0].read()
        try:
            function_string = content.decode()
        except UnicodeDecodeError as e:
            log.error("Failed to decode file for instant command.", exc_info=e)
            await ctx.send(
                ":warning: Failed to decode the file, all invalid characters will be replaced."
            )
            function_string = content.decode(errors="replace")
        finally:
            return cleanup_code(function_string)

    async def _extract_code(
        self, ctx: commands.Context, code_string: Optional[str] = None
    ) -> Tuple[T, str]:
        if ctx.message.attachments:
            function_string = await self._read_from_file(ctx, ctx.message)
        elif code_string:
            function_string = cleanup_code(code_string)
        else:
            message = (
                # TODO: redo this message
                "You're about to add a new object object to the bot.\n"
                "Your next message will be the code of your object.\n\n"
                "If this is the first time you're adding instant commands, "
                "please read the wiki:\n"
                "https://laggron.red/instantcommands.html#usage"
            )
            await ctx.send(message)
            pred = MessagePredicate.same_context(ctx)
            try:
                response: discord.Message = await self.bot.wait_for(
                    "message", timeout=900, check=pred
                )
            except asyncio.TimeoutError:
                await ctx.send("Question timed out.")
                return

            if response.content == "" and response.attachments:
                function_string = await self._read_from_file(ctx, response)
            else:
                function_string = cleanup_code(response.content)

        env = {
            "bot": self.bot,
            "discord": discord,
            "commands": commands,
            "checks": checks,
            "asyncio": asyncio,
            "instantcmd_cog": self,
        }
        try:
            function = get_code_from_str(function_string, env)
        except Exception as e:
            exception = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            message = (
                f"An exception has occured while compiling your code:\n```py\n{exception}\n```"
            )
            for page in pagify(message):
                await ctx.send(page)
            return
        return function, function_string

    @checks.is_owner()
    @commands.group(aliases=["instacmd", "instantcommand"])
    async def instantcmd(self, ctx: commands.Context):
        """Instant Commands cog management"""
        pass

    @instantcmd.command(aliases=["add"])
    async def create(self, ctx: commands.Context, *, command: str = None):
        """
        Instantly generate a new object from a code snippet.

        The following objects are supported: commands, listeners
        You can upload a text file if the command is too long, but you should consider coding a \
cog at this point.
        """
        function, function_string = await self._extract_code(ctx, command)
        snippet_type = find_matching_type(function)
        # this is a CodeSnippet object (command, listener or whatever is currently supported)
        code_snippet = snippet_type(self.bot, function, function_string)

        # detecting if this name isn't already registered
        for saved_code in self.get_code_snippets(type=snippet_type):
            if str(saved_code) == str(code_snippet):
                edit = await self._ask_for_edit(ctx, code_snippet)
                if not edit:
                    return

        try:
            code_snippet.register()
        except Exception as e:
            log.error(
                f"Failed to register snippet {code_snippet} given by {ctx.author}", exc_info=e
            )
            exception = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            message = (
                f"An expetion has occured while registering your {code_snippet} to the bot:\n"
                f"```py\n{exception}\n```"
            )
            for page in pagify(message):
                await ctx.send(page)
            return

        code_snippet.registered = True
        await code_snippet.save(self.data)
        self.code_snippets.append(code_snippet)
        await ctx.send(f"Successfully added your new {code_snippet.name}.")

    @instantcmd.command(name="list")
    async def _list(self, ctx):
        """
        List all existing commands made using Instant Commands.
        """
        view = View(timeout=300)
        total = 0
        types = (CommandSnippet, ListenerSnippet)
        for type in types:
            objects = list(self.get_code_snippets(enabled=False, registered=False, type=type))
            if not objects:
                continue
            total += len(objects)
            view.add_item(CodeSnippetsList(self.bot, type, objects))
        if total == 0:
            await ctx.send("No instant command created.")
            return
        await ctx.send(f"{total} instant commands created so far!", view=view)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def instantcmdinfo(self, ctx: commands.Context):
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

    async def cog_unload(self):
        log.debug("Unloading cog...")
        # removes commands and listeners
        await self.unload_all_code_snippets()

        # remove all handlers from the logger, this prevents adding
        # multiple times the same handler if the cog gets reloaded
        close_logger(log)

    async def cog_load(self):
        await self.load_all_code_snippets()
