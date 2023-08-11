import logging
import importlib.util
import re

from redbot.core.i18n import Translator
from redbot.core.bot import Red
from datetime import datetime, timedelta

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

from .warnsystem import WarnSystem
from .context_menus import context_warn

_ = Translator("WarnSystem", __file__)
log = logging.getLogger("red.laggron.warnsystem")


async def _save_backup(config):
    import json
    from datetime import datetime
    from redbot.core.data_manager import cog_data_path

    date = datetime.now().strftime("%d-%m-%Y-%H-%M-%S")
    path = cog_data_path(raw_name="WarnSystem") / f"settings-backup-{date}.json"
    full_data = {
        "260": {
            "GUILDS": await config.all_guilds(),
            "MODLOGS": await config.custom("MODLOGS").all(),
        }
    }
    data = json.dumps(full_data)
    with open(path.absolute(), "w") as file:
        file.write(data)
    log.info(f"Backup file saved at '{path.absolute()}', now starting conversion...")


async def _convert_to_v1(bot, config):
    def get_datetime(time: str) -> datetime:
        if isinstance(time, int):
            return datetime.fromtimestamp(time)
        try:
            time = datetime.strptime(time, "%a %d %B %Y %H:%M:%S")
        except ValueError:
            # seconds were added in an update, this might be a case made before that update
            time = datetime.strptime(time, "%a %d %B %Y %H:%M")
        return time

    def get_timedelta(text: str) -> timedelta:
        # that one is especially hard to convert
        # time is stored like this: "3 hours, 2 minutes and 30 seconds"
        # why did I even do this fuck me
        if isinstance(text, int):
            return timedelta(seconds=text)
        time = timedelta()
        results = re.findall(time_pattern, text)
        for match in results:
            amount = int(match[0])
            unit = match[1]
            if unit in units_name[0]:
                time += timedelta(days=amount * 366)
            elif unit in units_name[1]:
                time += timedelta(days=amount * 30.5)
            elif unit in units_name[2]:
                time += timedelta(weeks=amount)
            elif unit in units_name[3]:
                time += timedelta(days=amount)
            elif unit in units_name[4]:
                time += timedelta(hours=amount)
            elif unit in units_name[5]:
                time += timedelta(minutes=amount)
            else:
                time += timedelta(seconds=amount)
        return time

    for guild in bot.guilds:
        # update temporary warn to a dict instead of a list
        warns = await config.guild(guild).temporary_warns()
        if warns != {}:
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
        # change the way time is stored
        # instead of a long and heavy text, we use seconds since epoch
        modlogs = await config.custom("MODLOGS", guild.id).all()
        units_name = {
            0: (_("year"), _("years")),
            1: (_("month"), _("months")),
            2: (_("week"), _("weeks")),
            3: (_("day"), _("days")),
            4: (_("hour"), _("hours")),
            5: (_("minute"), _("minutes")),
            6: (_("second"), _("seconds")),
        }  # yes this can be translated
        separator = _(" and ")
        time_pattern = re.compile(
            (
                r"(?P<time>\d+)(?: )(?P<unit>{year}|{years}|{month}|"
                r"{months}|{week}|{weeks}|{day}|{days}|{hour}|{hours}"
                r"|{minute}|{minutes}|{second}|{seconds})(?:(,)|({separator}))?"
            ).format(
                year=units_name[0][0],
                years=units_name[0][1],
                month=units_name[1][0],
                months=units_name[1][1],
                week=units_name[2][0],
                weeks=units_name[2][1],
                day=units_name[3][0],
                days=units_name[3][1],
                hour=units_name[4][0],
                hours=units_name[4][1],
                minute=units_name[5][0],
                minutes=units_name[5][1],
                second=units_name[6][0],
                seconds=units_name[6][1],
                separator=separator,
            )
        )
        for member, modlog in modlogs.items():
            if member == "x":
                continue
            for i, log in enumerate(modlog["x"]):
                time = get_datetime(log["time"])
                modlogs[member]["x"][i]["time"] = int(time.timestamp())
                duration = log["duration"]
                if duration is not None:
                    modlogs[member]["x"][i]["duration"] = int(
                        get_timedelta(duration).total_seconds()
                    )
                    del modlogs[member]["x"][i]["until"]
        if modlogs:
            await config.custom("MODLOGS", guild.id).set(modlogs)


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
        await _save_backup(config)
        # we consider we have a safe backup at this point
        await _convert_to_v1(bot, config)
        await config.data_version.set("1.0")
        log.info(
            "All data successfully converted! The cog will now load. Keep the backup file for "
            "a bit since problems can occur after cog load."
        )
        # phew


async def setup(bot: Red):
    n = WarnSystem(bot)
    # the cog conflicts with the core Warnings cog, we must check that
    if "Warnings" in bot.cogs:
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
        raise CogLoadError(
            "After an update, the cog tried to perform changes to the saved data but an error "
            "occured. Read your console output or warnsystem.log (located over "
            "Red-DiscordBot/cogs/WarnSystem) for more details.\n"
            "**Do not try to load the cog again until the issue is resolved, the data might be"
            "corrupted.** Contacting support is advised (Laggron's support server or official "
            "3rd party cog support server, #support_laggrons-dumb-cogs channel)."
        ) from e
    await bot.add_cog(n)
    await n.cache.init_automod_enabled()
    n.task = bot.loop.create_task(n.api._loop_task())
    if n.cache.automod_enabled:
        n.api.enable_automod()
    bot.tree.add_command(context_warn)
    log.debug("Cog successfully loaded on the instance.")
