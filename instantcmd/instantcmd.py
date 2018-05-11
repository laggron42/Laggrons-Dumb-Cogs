import discord
import asyncio # for coroutine checks
import inspect # for checking is value is a class
import traceback

from discord.ext import commands
from redbot.core import checks
from redbot.core import Config
from redbot.core.utils.chat_formatting import pagify

class InstantCommands:
    """
    Generate a new command from a code snippet, without making a new cog.
    Report a bug or ask a question: https://discord.gg/WsTGeQ
    Full documentation and FAQ: https://github.com/retke/Laggrons-Dumb-Cogs/wiki
    """

    def __init__(self, bot):
        self.bot = bot
        self.data = Config.get_conf(self, 260)

        def_global = {
            "commands" : {}
        }

        self.data.register_global(**def_global)

    __author__ = "retke (El Laggron)"
    __version__ = "Laggrons-Dumb-Cogs/instantcmd indev"
    # indev means in development


    # from DEV cog, made by Cog Creators (tekulvw)
    @staticmethod
    def cleanup_code(content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith('```') and content.endswith('```'):
            return '\n'.join(content.split('\n')[1:-1])

        # remove `foo`
        return content.strip('` \n')


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

        def check(message):
            return message.author == ctx.author and message.channel == ctx.channel

        await ctx.send("You're about to create a new command. \n"
                        "Your next message will be the code of the command. \n\n"
                        "If this is the first time you're adding instant commands, "
                        "please read the wiki:\n"
                        "<https://github.com/retke/Laggrons-Dumb-Cogs/wiki>")

        try:
            response = await self.bot.wait_for("message", timeout=900, check=check)
        except asyncio.TimeoutError:
            await ctx.send("Question timed out.")
            return
            
        function = self.cleanup_code(response.content)

        # we get all existing functions in this process
        # then we compare to the one after executing the code snippet
        # so we can find the function name
        old_locals = dict(locals()) # we get its dict so it is a static value

        try:
            exec(function)
        except Exception as e:
            message = ("An exception has occured while compiling your code:\n"
                        "```py\n"
                        "{}```".format("".join(traceback.format_exception(type(e),
                                        e, e.__traceback__))))
            for page in pagify(message):
                await ctx.send(page)
            return
        
        new_locals = dict(locals())
        new_locals.pop('old_locals') # we only want the exec() functions

        function = [b for a, b in new_locals.items() if a not in old_locals]
        # if the user used the command correctly, we should have one async function

        if len(function) != 1:
            message = "Error: You need to create one async function in your code snippet:\n"
            if len(function) < 1:
                await ctx.send(message + "- No function detected")
            elif len(function) > 1:
                await ctx.send(message + "- More than one function found")
            elif inspect.isclass(function[0]):
                await ctx.send(message + "- You cannot give a class")
            elif not asyncio.iscoroutine(function[0]):
                await ctx.send(message + "- Function is not a coroutine")

        function = function[0]

        try:
            self.bot.add_command(function)
        except Exception as e:
            message = ("An expetion has occured while adding the command to discord.py:\n"
                        "```py\n"
                        "{}```".format("".join(traceback.format_exception(type(e),
                                      e, e.__traceback__))))
            for page in pagify(message):
                await ctx.send(page)

        await ctx.send("The command {} was successfully added. "
                        "It will appear under `No category` in the help message.")