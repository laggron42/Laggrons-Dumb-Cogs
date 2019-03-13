import logging
from .say import Say

log = logging.getLogger("laggron.say")


async def setup(bot):
    n = Say(bot)
    bot.add_cog(n)
    log.debug("Cog successfully loaded on the instance.")
