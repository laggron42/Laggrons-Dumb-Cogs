# This file is used for logging errors and
# sending them to sentry.io for helping retke
# in fixing bugs.
#
# This will only be enabled if the main Sentry
# (for Red) is enabled.
#
# This file is 95% from Cog-Creators for core Red

import logging
import platform
import pathlib

from raven import Client
from raven.handlers.logging import SentryHandler
from redbot.core.bot import RedBase
from redbot.core.data_manager import cog_data_path
from distutils.version import StrictVersion


def create_log(cog_path: pathlib.Path):
    if not cog_path.exists():
        return
    path = cog_path / "logs"
    directories = [x for x in cog_path.iterdir() if x.is_dir()]
    if path not in directories:
        path.mkdir()
        (path / "error.log").touch()
        (path / "debug.log").touch()


class Sentry:
    """
    Automatically send errors to the cog author
    """

    def __init__(self, logger: logging.Logger, version: StrictVersion, bot: RedBase):
        self.bot = bot
        self.client = Client(
            dsn=(
                "https://ff90c52be55a43b1914be6dd26ac7b57:dc1b6820fcfc4a149a2ff276a12b6ccf"
                "@sentry.io/1253554"
            ),
            release=version,
        )
        self.format = logging.Formatter(
            "%(asctime)s %(levelname)s %(module)s %(funcName)s %(lineno)d: %(message)s",
            datefmt="[%d/%m/%Y %H:%M]",
        )
        self.logger = logger

        self.handler = self.sentry_log_init()
        create_log(cog_data_path(bot))
        self.file_handler_init()

    def sentry_log_init(self):
        """Initialize Sentry logger"""
        self.client.environment = f"{platform.system()} ({platform.release()})"
        self.client.user_context(
            {"id": self.bot.user.id, "name": str(self.bot.user), "owner_id": self.bot.owner_id}
        )
        handler = SentryHandler(self.client)
        handler.setFormatter(self.format)
        return handler

    def file_handler_init(self):
        """Initialize file handlers"""
        error_log = logging.FileHandler(cog_data_path(self.bot) / "logs/error.log")
        error_log.setLevel(logging.ERROR)
        error_log.setFormatter(self.format)
        debug_log = logging.FileHandler(cog_data_path(self.bot) / "logs/debug.log")
        debug_log.setLevel(logging.DEBUG)
        debug_log.setFormatter(self.format)
        self.logger.addHandler(error_log)
        self.logger.addHandler(debug_log)

    def enable(self):
        """Enable error reporting for Sentry."""
        self.logger.addHandler(self.handler)

    def disable(self):
        """Disable error reporting for Sentry."""
        self.logger.removeHandler(self.handler)
