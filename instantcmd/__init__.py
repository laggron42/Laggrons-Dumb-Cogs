import logging
import asyncio

from redbot.core.data_manager import cog_data_path

from .instantcmd import InstantCommands
from .loggers import Log

log = logging.getLogger("laggron.instantcmd")
# this should be called after initializing the logger


async def ask_enable_sentry(bot):
    owner = bot.get_user(bot.owner_id)

    def check(message):
        return message.author == owner and message.channel == owner.dm_channel

    if not owner.bot:  # make sure the owner is set
        await owner.send(
            "Hello, thanks for installing `instantcmd`. Would you like to enable error "
            "logging to help the developer to fix new errors? If you wish to "
            'opt in the process, please type "yes"'
        )
        try:
            message = await bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            await owner.send(
                "Request timed out. Error logging disabled by default. You can "
                "change that by using the `[p]instantcmdinfo` command."
            )
            return None
        if "yes" in message.content.lower():
            await owner.send(
                "Thank you for helping me with the development process!\n"
                "You can disable this at anytime by using `[p]instantcmdinfo` command."
            )
            log.info("Sentry error reporting was enabled for this instance.")
            return True
        else:
            await owner.send(
                "The error logging was not enabled. You can change that by "
                "using the `[p]instantcmdinfo` command."
            )
            return False


async def ask_reset(bot, commands):
    owner = bot.get_user(bot.owner_id)

    def check(message):
        return message.author == owner and message.channel == owner.dm_channel

    if not owner.bot:
        await owner.send(
            "InstantCommands was updated to its first release! Internal code was modified "
            "to allow more features to be implemented, such as using `bot` in listeners "
            "or storing values with Config.\n"
            "It is needed to reset all of your instant commands and listeners to be "
            "ready for this version.\n\n"
            "**Modifications to bring:** Instead of providing only the desired function, "
            "you can now put whatever you want in your code snippet, but you must return "
            "your command/function at the end.\n\n"
            "Example:\n"
            "```py\n"
            "@commands.command()\n"
            "async def hello(ctx):\n"
            '    await ctx.send("Hello world!")\n\n'
            "return hello\n"
            "```"
        )
        path = cog_data_path(None, raw_name="InstantCommands") / "commands_backup.txt"
        with path.open(mode="w") as file:
            text = ""
            for name, command in commands.items():
                text += f"[Command/listener: {name}]\n{command}\n\n\n"
            file.write(text)
            log.debug(f"Wrote backup file at {path}")
        await owner.send(
            "A file was successfully written as a backup of what you previously did at the "
            f"following path:\n```{str(path)}```\n"
            "Please read the docs if you want to know what exactly changed, and what you must "
            "do\nhttps://laggrons-dumb-cogs.readthedocs.io/instantcommands.html"
        )


async def setup(bot):
    n = InstantCommands(bot)
    sentry = Log(bot, n.__version__)
    sentry.enable_stdout()
    n._set_log(sentry)
    if await n.data.enable_sentry() is None:
        response = await ask_enable_sentry(bot)
        await n.data.enable_sentry.set(response)
    if await n.data.enable_sentry():
        n.sentry.enable()
    if not await n.data.updated_body():
        commands = await n.data.commands()
        if commands:
            # the data is outdated and must be cleaned to be ready for the new version
            await ask_reset(bot, commands)
            await n.data.commands.set({})
        await n.data.updated_body.set(True)
    bot.add_cog(n)
    log.debug("Cog successfully loaded on the instance.")
