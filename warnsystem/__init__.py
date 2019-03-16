import logging

try:
    from redbot.core.errors import CogLoadError
except ImportError:
    CogLoadError = RuntimeError
from .warnsystem import WarnSystem

log = logging.getLogger("laggron.warnsystem")


async def setup(bot):
    n = WarnSystem(bot)
    # the cog conflicts with the core Warnings cog, we must check that
    if "Warnings" in bot.cogs:
        raise CogLoadError(
            "You need to unload the Warnings cog to load "
            "this cog. Type `[p]unload warnings` and try again."
        )
    bot.add_cog(n)
    log.debug("Cog successfully loaded on the instance.")
