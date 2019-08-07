import logging
from .nsfw import NSFW

log = logging.getLogger("laggron.nsfw")


async def setup(bot):
    n = NSFW(bot)
    bot.add_cog(n)
    log.debug("Cog successfully loaded on the instance.")
