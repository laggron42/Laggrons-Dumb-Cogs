import logging
import asyncio
import platform

from raven import Client
from raven.handlers.logging import SentryHandler
from raven_aiohttp import AioHttpTransport
from typing import TYPE_CHECKING
from redbot.core.data_manager import cog_data_path
from redbot.core import __version__ as red_version

if TYPE_CHECKING:
    from redbot.core.bot import RedBase
    from distutils.version import StrictVersion


log = logging.getLogger("laggron.say")
if logging.getLogger("red").isEnabledFor(logging.DEBUG):
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.INFO)


class Log:
    """
    Logging and error reporting management for Say

    Credit to Cog-Creators for the code base.
    """

    def __init__(self, bot: "RedBase", version: "StrictVersion"):
        self.bot = bot
        self.client = Client(
            dsn=(
                "https://ff90c52be55a43b1914be6dd26ac7b57:dc1b6820fcfc4a149a2ff276a12b6ccf"
                "@sentry.io/1253554"
            ),
            release=version,
            transport=AioHttpTransport,
        )
        self.format = logging.Formatter(
            "%(asctime)s %(levelname)s Say: %(message)s", datefmt="[%d/%m/%Y %H:%M]"
        )
        self.sentry_handler, self.stdout_handler = self.init_logger()

    def init_logger(self) -> SentryHandler:
        # sentry stuff
        owner = self.bot.get_user(self.bot.owner_id)
        self.client.environment = f"{platform.system()} ({platform.release()})"
        self.client.user_context(
            {
                "id": self.bot.user.id,
                "name": str(self.bot.user),
                "Owner": f"{str(owner)} (ID: {owner.id})" if owner else "Not defined",
            }
        )
        self.client.tags_context({"red_version": red_version})
        sentry_handler = SentryHandler(self.client)
        sentry_handler.setLevel(logging.ERROR)  # only send errors

        # logging to a log file
        # file is automatically created by the module, if the parent foler exists
        cog_path = cog_data_path(raw_name="Say")
        if cog_path.exists():
            log_path = cog_path / "say.log"
            file_logger = logging.FileHandler(log_path)
            file_logger.setLevel(logging.DEBUG)
            file_logger.setFormatter(self.format)
            log.addHandler(file_logger)

        # stdout stuff
        stdout_handler = logging.StreamHandler()
        stdout_handler.setFormatter(self.format)

        return (sentry_handler, stdout_handler)

    def enable(self):
        """Enable error reporting for Sentry."""
        log.addHandler(self.sentry_handler)

    def disable(self):
        """Disable error reporting for Sentry."""
        log.removeHandler(self.sentry_handler)
        loop = asyncio.get_event_loop()
        loop.create_task(self.close())

    def enable_stdout(self):
        log.addHandler(self.stdout_handler)

    def disable_stdout(self):
        log.removeHandler(self.stdout_handler)

    async def close(self):
        """Wait for the Sentry client to send pending messages and shut down."""
        await self.client.remote.get_transport().close()
