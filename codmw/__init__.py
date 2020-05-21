import logging
from .codmw import CODMW

log = logging.getLogger("laggron.codmw")


def setup(bot):
    n = CODMW(bot)
    bot.add_cog(n)
    log.debug("Cog successfully loaded on the instance.")
