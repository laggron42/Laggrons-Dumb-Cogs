import pathlib
import asyncio

from .say import Say

from redbot.core.data_manager import cog_data_path


def create_cache(path: pathlib.Path):
    if not path.exists():
        return
    directories = [x for x in path.iterdir() if x.is_dir()]
    if (path / "cache") not in directories:
        (path / "cache").mkdir()


async def ask_enable_sentry(bot, _):
    owner = bot.get_user(bot.owner_id)

    def check(message):
        return message.author == owner and message.channel == owner.dm_channel

    if not owner.bot:  # make sure the owner is set
        await owner.send(
            _(
                "Hello, thanks for installing `say`. Would you like to enable error "
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
                    "change that by using the `[p]sayinfo` command."
                )
            )
            return None
        if "yes" in message.content.lower():
            await owner.send(
                _(
                    "Thank you for helping me with the development process!\n"
                    "You can disable this at anytime by using `[p]sayinfo` command."
                )
            )
            return True
        else:
            await owner.send(
                _(
                    "The error logging was not enabled. You can change that by "
                    "using the `[p]sayinfo` command."
                )
            )
            return False


async def setup(bot):
    n = Say(bot)
    create_cache(cog_data_path(n))
    if await n.data.enable_sentry() is None:
        response = await ask_enable_sentry(bot, n.translator)
        await n.data.enable_sentry.set(response)
    if await n.data.enable_sentry():
        n.sentry.enable()
    bot.add_cog(n)
