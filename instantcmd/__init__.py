import logging
import importlib.util
from .instantcmd import InstantCommands

from redbot.core.data_manager import cog_data_path
from redbot.core.errors import CogLoadError
from laggron_utils import init_logger

if not importlib.util.find_spec("laggron_utils"):
    raise CogLoadError(
        "You need the `laggron_utils` package for any cog from Laggron's Dumb Cogs. "
        "Use the command `[p]pipinstall git+https://github.com/retke/Laggron-utils.git` "
        "or type `pip3 install -U git+https://github.com/retke/Laggron-utils.git` in the "
        "terminal to install the library."
    )

log = logging.getLogger("red.laggron.instantcmd")


async def ask_reset(bot, commands):
    owner = bot.get_user(bot.owner_id)

    def check(message):
        return message.author == owner and message.channel == owner.dm_channel

    if not owner:
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
            log.info(f"Wrote backup file at {path}")
        await owner.send(
            "A file was successfully written as a backup of what you previously did at the "
            f"following path:\n```{str(path)}```\n"
            "Please read the docs if you want to know what exactly changed, and what you must "
            "do\nhttps://laggrons-dumb-cogs.readthedocs.io/instantcommands.html"
        )


async def setup(bot):
    init_logger(log, InstantCommands.__class__.__name__, "instantcmd")
    n = InstantCommands(bot)
    if not await n.data.updated_body():
        commands = await n.data.commands()
        if commands:
            # the data is outdated and must be cleaned to be ready for the new version
            await ask_reset(bot, commands)
            await n.data.commands.set({})
        await n.data.updated_body.set(True)
    await bot.add_cog(n)
    log.debug("Cog successfully loaded on the instance.")
