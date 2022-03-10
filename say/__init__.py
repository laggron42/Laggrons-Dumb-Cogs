import asyncio
import logging
import importlib.util

from .say import Say

from typing import TYPE_CHECKING
from discord import app_commands
from redbot.core.errors import CogLoadError
from laggron_utils import init_logger

if TYPE_CHECKING:
    from redbot.core.bot import Red

if not importlib.util.find_spec("laggron_utils"):
    raise CogLoadError(
        "You need the `laggron_utils` package for any cog from Laggron's Dumb Cogs. "
        "Use the command `[p]pipinstall git+https://github.com/retke/Laggron-utils.git` "
        "or type `pip3 install -U git+https://github.com/retke/Laggron-utils.git` in the "
        "terminal to install the library."
    )

log = logging.getLogger("red.laggron.say")


async def setup(bot: "Red"):
    init_logger(log, "Say")
    try:
        if not hasattr(bot, "tree"):
            bot.tree = app_commands.CommandTree(bot)
    except AttributeError:
        raise CogLoadError("This cog requires the latest discord.py 2.0.0a.") from None
    n = Say(bot)
    bot.add_cog(n)
    asyncio.create_task(_setup(bot))
    log.debug("Cog successfully loaded on the instance.")


async def _setup(bot: "Red"):
    if bot.user:
        assert isinstance(bot.tree, app_commands.CommandTree)
        log.debug("Added slash command /say, syncing...")
        await bot.tree.sync(guild=None)
        log.debug("Slash commands now synced...")


def teardown(bot: "Red"):
    if bot.user:
        assert isinstance(bot.tree, app_commands.CommandTree)
        # delay the slash removal a bit in case this is a reload
        asyncio.get_event_loop().call_later(2, asyncio.create_task, bot.tree.sync(guild=None))
