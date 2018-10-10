import logging
import asyncio
import platform

from raven import Client
from raven.handlers import SentryHandler
from raven_aiohttp import AioHttpTransport
from pathlib import Path
from typing import TYPE_CHECKING
from redbot.core.data_manager import cog_data_path

if TYPE_CHECKING:
    from redbot.core.bot import RedBase
    from distutils.version import StrictVersion


log = logging.getLogger("laggron.bettermod")
if logging.getLogger("red").isEnabledFor(logging.DEBUG):
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.INFO)


class Log:
    """
    Logging and error reporting management for BetterMod

    Credit to Cog-Creators for the code base.
    """

    def __init__(self, bot: "RedBase", version: "StrictVersion"):
        self.bot = bot
        self.client = Client(
            dsn=(
                "https://240c1316c99148d085acde231596bdb7:40f84ce62374493891d57e30bec5ee1c"
                "@sentry.io/1256932"
            ),
            release=version,
            transport=AioHttpTransport,
        )
        self.format = logging.Formatter(
            "%(asctime)s %(levelname)s %(module)s %(funcName)s %(lineno)d : %(message)s",
            datefmt="[%d/%m/%Y %H:%M]",
        )
        self.sentry_handler = self.init_logger()

    def init_logger(self) -> SentryHandler:
        # sentry stuff
        owner = self.bot.get_user(self.bot.owner_id)
        self.client.environment = f"{platform.system()} ({platform.release()})"
        self.client.user_context(
            {
                "id": self.bot.user.id,
                "name": str(self.bot.user),
                "owner": {"id": owner.id, "name": owner.name},
            }
        )
        sentry_handler = SentryHandler(self.client)
        sentry_handler.setFormatter(self.format)

        # logging to a log file
        log_path = cog_data_path(self.bot) / "bettermod.log"
        if log_path.is_file():
            file_logger = logging.FileHandler(log_path)
            file_logger.setLevel(logging.INFO)
            log.addHandler(file_logger)

        return sentry_handler

    def enable(self):
        """Enable error reporting for Sentry."""
        slog.addHandler(self.handler)

    def disable(self):
        """Disable error reporting for Sentry."""
        log.removeHandler(self.handler)
        loop = asyncio.get_event_loop()
        loop.create_task(self.close())

    async def close(self):
        """Wait for the Sentry client to send pending messages and shut down."""
        await self.client.remote.get_transport().close()
