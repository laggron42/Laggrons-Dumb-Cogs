import logging
import importlib.util

from .warnsystem import WarnSystem

try:
    from redbot.core.errors import CogLoadError
except ImportError:
    CogLoadError = RuntimeError

if not importlib.util.find_spec("dateutil"):
    raise CogLoadError(
        "You need the `python-dateutil` package for this cog. "
        "Use the command `[p]pipinstall python-dateutil` or type "
        "`pip3 install python-dateutil` in the terminal to install the library."
    )

log = logging.getLogger("laggron.warnsystem")


def _save_backup(config):
    import json
    from datetime import datetime
    from redbot.core.data_manager import cog_data_path

    date = datetime.now().strftime("%d-%m-%Y-%H-%M-%S")
    path = cog_data_path(raw_name="WarnSystem") / f"settings-backup-{date}.json"
    data = json.dumps(config.driver.data)
    with open(path.absolute(), "w") as file:
        file.write(data)
    log.info(f"Backup file saved at '{path.absolute()}', now starting conversion...")


async def _convert_to_v1(bot, config):
    for guild in bot.guilds:
        warns = await config.guild(guild).temporary_warns()
        if warns == {}:
            continue
        if warns:
            new_dict = {}
            for case in warns:
                member = case["member"]
                del case["member"]
                new_dict[member] = case
            await config.guild(guild).temporary_warns.set(new_dict)
        else:
            # config does not update [] to {}
            # we fill a dict with random values to force config to set a dict
            # then we empty that dict
            await config.guild(guild).temporary_warns.set({None: None})
            await config.guild(guild).temporary_warns.set({})


async def update_config(bot, config):
    """
    Warnsystem 1.3.0 requires an update with the config body.
    Temporary warns are stored as a dict instead of a list.
    """
    if await config.data_version() == "0.0":
        all_guilds = await config.all_guilds()
        if not any("temporary_warns" in x for x in all_guilds.values()):
            await config.data_version.set("1.0")
            return
        log.info(
            "WarnSystem 1.3.0 changed the way data is stored. Your data will be updated. "
            "A copy will be created. If something goes wrong and the data is not usable, keep "
            "that file safe and ask support on how to recover the data."
        )
        # perform a backup, any exception MUST be raised
        await bot.loop.run_in_executor(None, _save_backup, config)
        # we consider we have a safe backup at this point
        await _convert_to_v1(bot, config)
        await config.data_version.set("1.0")
        log.info(
            "All data successfully converted! The cog will now load. Keep the backup file for "
            "a bit since problems can occur after cog load."
        )
        # phew


async def setup(bot):
    n = WarnSystem(bot)
    # the cog conflicts with the core Warnings cog, we must check that
    if "Warnings" in bot.cogs:
        log.handlers = []  # still need some cleaning up
        raise CogLoadError(
            "You need to unload the Warnings cog to load "
            "this cog. Type `[p]unload warnings` and try again."
        )
    try:
        await update_config(bot, n.data)
    except Exception as e:
        log.critical(
            "Cannot update config. Data can be corrupted, do not try to load the cog."
            "Contact support for further instructions.",
            exc_info=e,
        )
        log.handlers = []  # still need some cleaning up
        raise CogLoadError(
            "After an update, the cog tried to perform changes to the saved data but an error "
            "occured. Read your console output or warnsystem.log (located over "
            "Red-DiscordBot/cogs/WarnSystem) for more details.\n"
            "**Do not try to load the cog again until the issue is resolved, the data might be"
            "corrupted.** Contacting support is advised (Laggron's support server or official "
            "3rd party cog support server, #support_laggrons-dumb-cogs channel)."
        ) from e
    bot.add_cog(n)
    n.task = bot.loop.create_task(n._loop_task())
    log.debug("Cog successfully loaded on the instance.")
