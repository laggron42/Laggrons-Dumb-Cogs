import logging
import asyncio

# from redbot.core.errors import CogLoadError
from redbot.core.data_manager import cog_data_path
from pathlib import Path

from .warnsystem import WarnSystem
from .loggers import Log

log = logging.getLogger("laggron.warnsystem")
# this should be called after initializing the logger


# until release 3.1
class CogLoadError(Exception):
    pass


def create_cache(path: Path):
    """Creates a cache folder for the downloads"""
    if not path.exists():
        return
    cache = path / "cache"
    directories = [x for x in path.iterdir() if x.is_dir()]
    if cache not in directories:
        cache.mkdir()
        log.info(f"Created cache directory at {str(cache)}")


async def ask_enable_sentry(bot):
    owner = bot.get_user(bot.owner_id)

    def check(message):
        return message.author == owner and message.channel == owner.dm_channel

    if not owner.bot:  # make sure the owner is set
        await owner.send(
            _(
                "Hello, thanks for installing `warnsystem`. Would you like to enable error "
                "logging to help the developer to fix new errors? If you wish to "
                'opt in the process, please type "yes"'
            )
        )
        try:
            message = await bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            await owner.send(
                _(
                    "Request timed out. Error logging disabled by default. You can "
                    "change that by using the `[p]warnsysteminfo` command."
                )
            )
            return None
        if _("yes") in message.content.lower():
            await owner.send(
                _(
                    "Thank you for helping me with the development process!\n"
                    "You can disable this at anytime by using `[p]warnsysteminfo` command."
                )
            )
            log.info("Sentry error reporting was enabled for this instance.")
            return True
        else:
            await owner.send(
                _(
                    "The error logging was not enabled. You can change that by "
                    "using the `[p]warnsysteminfo` command."
                )
            )
            return False


async def setup(bot):
    global _
    n = WarnSystem(bot)
    _ = n.translator
    if "Warnings" in bot.cogs:
        raise CogLoadError(
            _(
                "You need to unload the Warnings cog to load "
                "this cog. Type `[p]unload warnings` and try again."
            )
        )
    sentry = Log(bot, n.__version__)
    n._set_log(sentry)
    create_cache(cog_data_path(n))
    if await n.data.enable_sentry() is None:
        response = await ask_enable_sentry(bot)
        await n.data.enable_sentry.set(response)
    if await n.data.enable_sentry():
        n.sentry.enable()
    bot.add_cog(n)
    log.debug("Cog successfully loaded on the instance.")
