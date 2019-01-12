import signal
import logging
import sys

from redbot.core.commands import Cog

log = logging.getLogger("red")  # core actions


class SignalHandler(Cog):
    """
    A cog that shutdowns the bot correctly when SIGTERM is received.

    This hidden cog can be considered as an alternative to this PR until release 3.1.0
    https://github.com/Cog-Creators/Red-DiscordBot/pull/2286/files
    """

    def __init__(self, bot):
        self.bot = bot

    async def sigterm_handler(self):
        log.info("SIGTERM received. Exiting...")
        await self.bot.shutdown(restart=False)
        sys.exit(0)

    def __unload(self):
        self.bot.loop.remove_signal_handler(signal.SIGTERM)
