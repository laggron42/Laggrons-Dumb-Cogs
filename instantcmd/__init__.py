import logging

from typing import TYPE_CHECKING, Dict
from .instantcmd import InstantCommands

from redbot.core.data_manager import cog_data_path
from redbot.core.errors import CogLoadError

if TYPE_CHECKING:
    from redbot.core.bot import Red
    from redbot.core import Config

log = logging.getLogger("red.laggron.instantcmd")


async def save_old_commands(bot: "Red", config: "Config", data: Dict[str, Dict[str, str]]):
    # save data
    path = cog_data_path(None, raw_name="InstantCommands") / "pre-2.0-backup"
    path.mkdir(exist_ok=True)

    commands = data.get("commands", {})
    dev_values = data.get("dev_values", {})
    commands_file_path = path / "commands.py"
    dev_values_file_path = path / "dev_env_values.py"

    if commands:
        with commands_file_path.open("w") as file:
            for name, content in commands.items():
                file.write("# ====================================\n")
                file.write(f'# command or listener "{name}"\n')
                file.write("# ====================================\n\n")
                file.write(content)
                file.write("\n\n\n")
        log.info(f"Backed up commands and listeners at {commands_file_path.absolute()}")

    if dev_values:
        with dev_values_file_path.open("w") as file:
            for name, content in commands.items():
                file.write("# ====================================\n")
                file.write(f'# dev env value "{name}"\n')
                file.write("# ====================================\n\n")
                file.write(content)
                file.write("\n\n\n")
        log.info(f"Backed up dev env values at {dev_values_file_path.absolute()}")

    await config.commands.clear()
    await config.dev_values.clear()
    log.warning("Deleted old data")

    await bot.send_to_owners(
        "**InstantCommands was updated to version 2.0!**\n"
        "The cog changed a lot, and even more new features are on the way. A lot of internal "
        "changes were done, which means it's migration time again! Don't worry, there shouldn't "
        "be much stuff to change.\n\n\n"
        "**Modifications to bring:**\n\n"
        "- **Commands:** Nothing is changed, but that had to be reset anyway for internal "
        "reasons :D (they were mixed with listeners, now it's separated)\n\n"
        "- **Listeners:** All listeners now require the decorator `instantcmd.utils.listener`. "
        "Example:\n"
        "```py\n"
        "from instantcmd.utils import listener\n\n"
        "@listener()\n"
        "async def on_member_join(member):\n"
        '    await member.send("Welcome new member!")  # don\'t do this\n\n'
        "return on_member_join\n"
        "```\n\n"
        "- **Dev env values:** Important changes for this, they have to be added like commands "
        "in the following form:\n"
        "```py\n"
        "from instantcmd.utils import dev_env_value\n\n"
        "@dev_env_value()\n"
        "def fluff_derg(ctx):\n"
        "    ID = 215640856839979008\n"
        "    if ctx.guild:\n"
        "        return ctx.guild.get_member(ID) or bot.get_user(ID)\n"
        "    else:\n"
        "        return bot.get_user(ID)\n\n"
        "return fluff_derg\n"
        "```\n\n"
        "A backup of your old commands and listeners was done in "
        f"`{commands_file_path.absolute()}`\n"
        "A backup of your old dev_env_values was done in "
        f"`{dev_values_file_path.absolute()}`\n\n"
        "The old config was removed, open these files and add the commands back, you should be "
        "good to go!\n"
        "Now there are only two commands, `create` and `list`, the rest is done through "
        "components. Anything can be toggled on/off in a click (without deletion), and more "
        "supported objects are on the way, like application commands, message components and "
        "cogs!\n"
        "By the way, glossary change due to the increasing number of supported objects, we're not "
        'referring to "commands" anymore, but "code snippets". The cog will keep its name.'
    )


async def setup(bot: "Red"):
    n = InstantCommands(bot)
    global_data = await n.data.all()
    if global_data.get("commands", {}) or global_data.get("dev_values", {}):
        log.info("Detected data from previous version, starting backup and removal")
        try:
            await save_old_commands(bot, n.data, global_data)
        except Exception:
            log.critical("Failed to backup and remove data for 2.0 update!", exc_info=True)
            raise CogLoadError("The cog failed to backup data for the 2.0 update!")
    await bot.add_cog(n)
