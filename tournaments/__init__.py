import logging
import importlib.util

from redbot.core.errors import CogLoadError

dependencies = {
    "laggron_utils": "git+https://github.com/retke/Laggron-utils.git",
    "achallonge": "apychal",
    "aiofiles": "aiofiles",
}

for dependency, package in dependencies.items():
    if not importlib.util.find_spec(dependency):
        raise CogLoadError(
            f"You need the `{dependency}` package for this cog. Use the command `[p]pipinstall "
            f"{package}` or type `pip3 install -U {package}` "
            "in the terminal to install the library."
        )

from .tournaments import Tournaments
from laggron_utils import init_logger

log = logging.getLogger("red.laggron.tournaments")


async def restore_tournaments(bot, cog):
    await bot.wait_until_ready()
    await cog.restore_tournaments()


async def setup(bot):
    init_logger(log, "Tournaments")
    n = Tournaments(bot)
    bot.add_cog(n)
    bot.loop.create_task(restore_tournaments(bot, n))
    log.debug("Cog successfully loaded on the instance.")
