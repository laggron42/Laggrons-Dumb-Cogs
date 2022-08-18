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
    n = Say(bot)
    await bot.add_cog(n)
    log.debug("Cog successfully loaded on the instance.")
