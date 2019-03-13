import logging
from .roleinvite import RoleInvite

log = logging.getLogger("laggron.roleinvite")


async def setup(bot):
    n = RoleInvite(bot)
    bot.add_cog(n)
    log.debug("Cog successfully loaded on the instance.")
