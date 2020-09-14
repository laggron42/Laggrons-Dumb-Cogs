import logging
import importlib.util

from redbot.core.errors import CogLoadError

if not importlib.util.find_spec("laggron_utils"):
    raise CogLoadError(
        "You need the `laggron_utils` package for any cog from Laggron's Dumb Cogs. "
        "Use the command `[p]pipinstall git+https://github.com/retke/Laggron-utils.git` "
        "or type `pip3 install -U git+https://github.com/retke/Laggron-utils.git` in the "
        "terminal to install the library."
    )
if not importlib.util.find_spec("achallonge"):
    raise CogLoadError(
        "You need the `apychal` package for this cog. Use the command `[p]pipinstall apychal` "
        "or type `pip3 install -U apychal` in the terminal to install the library."
    )

from .tournaments import Tournaments
from laggron_utils import init_logger

log = logging.getLogger("red.laggron.tournaments")


async def setup(bot):
    init_logger(log, Tournaments.__class__.__name__)
    n = Tournaments(bot)
    bot.add_cog(n)
    await n.restore_tournaments()
    log.debug("Cog successfully loaded on the instance.")
