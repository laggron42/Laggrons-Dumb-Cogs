import asyncio
import discord
import logging
import re
import functools

from copy import deepcopy
from collections import namedtuple
from typing import Union, Optional, Iterable, Callable, Awaitable
from datetime import datetime, timedelta, timezone
from multiprocessing import TimeoutError
from multiprocessing.pool import Pool
from discord.asset import Asset

from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.commands import BadArgument, MemberConverter

try:
    from redbot.core.modlog import get_modlog_channel as get_red_modlog_channel
except RuntimeError:
    pass  # running sphinx-build raises an error when importing this module

from .cache import MemoryCache
from . import errors

log = logging.getLogger("red.laggron.warnsystem")
_ = Translator("WarnSystem", __file__)
id_pattern = re.compile(r"([0-9]{15,21})$")


class SafeMember:
    def __init__(self, member: discord.Member) -> None:
        self.name = str(member.name)
        self.display_name = str(member.display_name)
        self.nick = str(member.nick)
        self.id = str(member.id)
        self.mention = str(member.mention)
        self.color = str(member.color)
        self.colour = str(member.colour)
        self.created_at = str(member.created_at)
        self.joined_at = str(member.joined_at)

    def __str__(self):
        return self.name

    def __getattr__(self, name):
        return self


class FakeRole:
    """
    We need to fake some attributes of roles for the class UnavailableMember
    """

    position = 0
    colour = None


class UnavailableMember(discord.Object, discord.abc.Messageable):
    """
    A class that reproduces the behaviour of a discord.Member instance, except
    the member is not in the guild. This is used to prevent calling bot.fetch_info
    which has a very high cooldown.
    """

    def __init__(self, bot, state, user_id: int):
        super().__init__(user_id)
        self.bot = bot
        self._state = state
        self.id = user_id
        self.top_role = FakeRole()
        self.nick = None
        self.joined_at = None

    @property
    def display_avatar(self) -> Asset:
        return Asset._from_default_avatar(
            self._state, (self.id >> 22) % len(discord.enums.DefaultAvatar)
        )

    @property
    def colour(self) -> discord.Colour:
        return self.top_role.colour

    @property
    def color(self) -> discord.Colour:
        return self.colour

    @classmethod
    def _check_id(cls, member_id):
        if not id_pattern.match(member_id):
            raise ValueError(f"You provided an invalid ID: {member_id}")
        return int(member_id)

    @classmethod
    async def convert(cls, ctx, text):
        try:
            member = await MemberConverter().convert(ctx, text)
        except BadArgument:
            pass
        else:
            return member
        try:
            member_id = cls._check_id(text)
        except ValueError:
            raise BadArgument(
                _(
                    "The given member cannot be found.\n"
                    "If you're trying to hackban, the user ID is not valid."
                )
            )
        return cls(ctx.bot, ctx._state, member_id)

    @property
    def name(self):
        return "Unknown"

    @property
    def display_name(self):
        return "Unknown"

    @property
    def mention(self):
        return f"<@{self.id}>"

    def __str__(self):
        return "Unknown#0000"

    # the 3 following functions were copied from the discord.User class, credit to Rapptz
    # https://github.com/Rapptz/discord.py/blob/master/discord/user.py#L668

    @property
    def dm_channel(self):
        """Optional[:class:`DMChannel`]: Returns the channel associated with this user if it exists.
        If this returns ``None``, you can create a DM channel by calling the
        :meth:`create_dm` coroutine function.
        """
        return self._state._get_private_channel_by_user(self.id)

    async def create_dm(self):
        """Creates a :class:`DMChannel` with this user.
        This should be rarely called, as this is done transparently for most
        people.
        """
        found = self.dm_channel
        if found is not None:
            return found

        state = self._state
        data = await state.http.start_private_message(self.id)
        return state.add_dm_channel(data)

    async def _get_channel(self):
        channel = await self.create_dm()
        return channel


class API:
    """
    Interact with WarnSystem from your cog.

    To import the cog and use the functions, type this in your code:

    .. code-block:: python

        warnsystem = bot.get_cog('WarnSystem').api

    .. warning:: If ``warnsystem`` is :py:obj:`None`, the cog is
      not loaded/installed. You won't be able to interact with
      the API at this point.

    .. tip:: You can get the cog version by doing this

        .. code-block:: python

            version = bot.get_cog('WarnSystem').__version__
    """

    def __init__(self, bot: Red, config: Config, cache: MemoryCache):
        self.bot = bot
        self.data = config
        self.cache = cache
        self.re_pool = Pool(maxtasksperchild=1000)
        self.regex_timeout = 1
        self.warned_guilds = []  # see automod_check_for_autowarn
        self.antispam = {}  # see automod_process_antispam
        self.antispam_warn_queue = {}  # see automod_warn
        self.automod_warn_task: asyncio.Task

    def _get_datetime(self, time: int) -> datetime:
        return datetime.fromtimestamp(int(time), tz=timezone.utc)

    def _get_timedelta(self, time: int) -> timedelta:
        return timedelta(seconds=int(time))

    def _format_datetime(self, time: datetime):
        return time.strftime("%a %d %B %Y %H:%M:%S")

    def _format_timedelta(self, time: timedelta):
        """Format a timedelta object into a string"""
        # blame python for not creating a strftime attribute
        plural = lambda name, amount: name[1] if amount > 1 else name[0]
        strings = []

        seconds = time.total_seconds()
        years, seconds = divmod(seconds, 31622400)
        months, seconds = divmod(seconds, 2635200)
        weeks, seconds = divmod(seconds, 604800)
        days, seconds = divmod(seconds, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        units = [years, months, weeks, days, hours, minutes, seconds]

        # tuples inspired from mikeshardmind
        # https://github.com/mikeshardmind/SinbadCogs/blob/v3/scheduler/time_utils.py#L29
        units_name = {
            0: (_("year"), _("years")),
            1: (_("month"), _("months")),
            2: (_("week"), _("weeks")),
            3: (_("day"), _("days")),
            4: (_("hour"), _("hours")),
            5: (_("minute"), _("minutes")),
            6: (_("second"), _("seconds")),
        }
        for i, value in enumerate(units):
            if value < 1:
                continue
            unit_name = plural(units_name.get(i), value)
            strings.append(f"{round(value)} {unit_name}")
        string = ", ".join(strings[:-1])
        if len(strings) > 1:
            string += _(" and ") + strings[-1]
        else:
            string = strings[0]
        return string

    async def _start_timer(self, guild: discord.Guild, member: discord.Member, case: dict) -> bool:
        """Start the timer for a temporary mute/ban."""
        if not case["duration"]:
            raise errors.BadArgument("No duration for this warning!")
        await self.cache.add_temp_action(guild, member, case)
        return True

    async def _mute(self, member: discord.Member, reason: Optional[str] = None):
        """Mute an user on the guild."""
        old_roles = []
        guild = member.guild
        mute_role = guild.get_role(await self.cache.get_mute_role(guild))
        remove_roles = await self.data.guild(guild).remove_roles()
        if not mute_role:
            raise errors.MissingMuteRole("You need to create the mute role before doing this.")
        if remove_roles:
            old_roles = member.roles.copy()
            old_roles.remove(guild.default_role)
            old_roles = [
                x for x in old_roles if x.position < guild.me.top_role.position and not x.managed
            ]
            fails = []
            for role in old_roles:
                try:
                    await member.remove_roles(role, reason=reason)
                except discord.errors.HTTPException:
                    fails.append(role)
            if fails:
                log.warn(
                    f"[Guild {guild.id}] Failed to remove roles from {member} (ID: {member.id}) "
                    f"while muting. Roles: {', '.join([f'{x.name} ({x.id})' for x in fails])}",
                )
        await member.add_roles(mute_role, reason=reason)
        return old_roles

    async def _unmute(self, member: discord.Member, reason: str, old_roles: list = None):
        """Unmute an user on the guild."""
        guild = member.guild
        mute_role = guild.get_role(await self.cache.get_mute_role(guild))
        if not mute_role:
            raise errors.MissingMuteRole(
                f"Lost the mute role on guild {guild.name} (ID: {guild.id}"
            )
        await member.remove_roles(mute_role, reason=reason)
        await member.add_roles(*old_roles, reason=reason)

    async def _create_case(
        self,
        guild: discord.Guild,
        user: discord.User,
        author: Union[discord.Member, str],
        level: int,
        time: datetime,
        reason: Optional[str] = None,
        duration: Optional[timedelta] = None,
        roles: Optional[list] = None,
        modlog_message: Optional[discord.Message] = None,
    ) -> dict:
        """Create a new case for a member. Don't call this, call warn instead."""
        data = {
            "level": level,
            "author": author
            if not isinstance(author, (discord.User, discord.Member))
            else author.id,
            "reason": reason,
            "time": int(time.timestamp()),  # seconds since epoch
            "duration": None if not duration else duration.total_seconds(),
            "roles": [] if not roles else [x.id for x in roles],
        }
        if modlog_message:
            data["modlog_message"] = {
                "channel_id": modlog_message.channel.id,
                "message_id": modlog_message.id,
            }
        async with self.data.custom("MODLOGS", guild.id, user.id).x() as logs:
            logs.append(data)
        return data

    async def get_case(
        self, guild: discord.Guild, user: Union[discord.User, discord.Member], index: int
    ) -> dict:
        """
        Get a specific case for a user.

        Parameters
        ----------
        guild: discord.Guild
            The guild of the member.
        user: Union[discord.User, discord.Member]
            The user you want to get the case from. Can be a :class:`discord.User` if the member is
            not in the server.
        index: int
            The case index you want to get. Must be positive.

        Returns
        -------
        dict
            A :py:class:`dict` which has the following body:

            .. code-block: python3

                {
                    "level"     : int,  # between 1 and 5, the warning level
                    "author"    : Union[discord.Member, str],  # the member that warned the user
                    "reason"    : Optional[str],  # the reason of the warn, can be None
                    "time"      : datetime.datetime,  # the date when the warn was set
                }

        Raises
        ------
        ~warnsystem.errors.NotFound
            The case requested doesn't exist.
        """
        try:
            case = (await self.data.custom("MODLOGS", guild.id, user.id).x())[index - 1]
        except IndexError:
            raise errors.NotFound("The case requested doesn't exist.")
        else:
            time = case["time"]
            if time:
                case["time"] = self._get_datetime(time)
            return case

    async def get_all_cases(
        self, guild: discord.Guild, user: Optional[Union[discord.User, discord.Member]] = None
    ) -> list:
        """
        Get all cases for a member of a guild.

        Parameters
        ----------
        guild: discord.Guild
            The guild where you want to get the cases from.
        user: Optional[Union[discord.User, discord.Member]]
            The user you want to get the cases from. If this arguments is omitted, all cases of
            the guild are returned.

        Returns
        -------
        list
            A list of all cases of a user/guild. The cases are sorted from the oldest to the
            newest.

            If you specified a user, you should get something like this:

            .. code-block:: python3

                [
                    {  # case #1
                        "level"     : int,  # between 1 and 5, the warning level
                        "author"    : Union[discord.Member, str],  # the member that warned the user
                        "reason"    : Optional[str],  # the reason of the warn, can be None
                        "time"      : datetime.datetime,  # the date when the warn was set
                    },
                    {
                        # case #2
                    },
                    # ...
                ]

            However, if you didn't specify a user, you got all cases of the guild. As for the user,
            you will get a :py:class:`list` of the cases, with another key for specifying the
            warned user:

            .. code-block:: python3

                {  # case #1
                    "level"     : int,  # between 1 and 5, the warning level
                    "author"    : Union[discord.Member, str],  # the member that warned the user
                    "reason"    : Optional[str],  # the reason of the warn, can be None
                    "time"      : datetime.datetime,  # the date when the warn was set

                    "member"    : discord.User,  # the member warned, this key is specific to guild
                }
        """
        if user:
            return await self.data.custom("MODLOGS", guild.id, user.id).x()
        logs = await self.data.custom("MODLOGS", guild.id).all()
        all_cases = []
        for member, content in logs.items():
            if member == "x":
                continue
            for log in content["x"]:
                time = log["time"]
                if time:
                    log["time"] = self._get_datetime(time)
                # gotta get that state somehow
                log["member"] = self.bot.get_user(int(member)) or UnavailableMember(
                    self.bot, self.bot.user._state, member
                )
                log["author"] = self.bot.get_user(int(log["author"])) or UnavailableMember(
                    self.bot, self.bot.user._state, log["author"]
                )
                all_cases.append(log)
        return sorted(all_cases, key=lambda x: x["time"])  # sorted from oldest to newest

    async def edit_case(
        self,
        guild: discord.Guild,
        user: Union[discord.User, discord.Member],
        index: int,
        new_reason: str,
    ) -> bool:
        """
        Edit the reason of a case.

        Parameters
        ----------
        guild: discord.Guild
            The guild where you want to get the case from.
        user: Union[discord.User, discord.Member]
            The user you want to get the case from.
        index: int
            The number of the case you want to edit.
        new_reason: str
            The new reason to set.

        Returns
        -------
        bool
            :py:obj:`True` if the action succeeded.

        Raises
        ------
        ~warnsystem.errors.BadArgument
            The reason is above 1024 characters. Due to Discord embed rules, you have to make it
            shorter.
        ~warnsystem.errors.NotFound
            The case requested doesn't exist.
        """

        async def edit_message(channel_id: int, message_id: int, new_reason: str):
            channel: discord.TextChannel = guild.get_channel(channel_id)
            if channel is None:
                log.warn(
                    f"[Guild {guild.id}] Failed to edit modlog message. "
                    f"Channel {channel_id} not found."
                )
                return False
            try:
                message: discord.Message = await channel.fetch_message(message_id)
            except discord.errors.NotFound:
                log.warn(
                    f"[Guild {guild.id}] Failed to edit modlog message. "
                    f"Message {message_id} in channel {channel.id} not found."
                )
                return False
            except discord.errors.Forbidden:
                log.warn(
                    f"[Guild {guild.id}] Failed to edit modlog message. "
                    f"No permissions to fetch messages in channel {channel.id}."
                )
                return False
            except discord.errors.HTTPException as e:
                log.error(
                    f"[Guild {guild.id}] Failed to edit modlog message. API exception raised.",
                    exc_info=e,
                )
                return False
            try:
                embed: discord.Embed = message.embeds[0]
                embed.set_field_at(
                    len(embed.fields) - 2, name=_("Reason"), value=new_reason, inline=False
                )
            except IndexError as e:
                log.error(
                    f"[Guild {guild.id}] Failed to edit modlog message. Embed is malformed.",
                    exc_info=e,
                )
                return False
            try:
                await message.edit(embed=embed)
            except discord.errors.HTTPException as e:
                log.error(
                    f"[Guild {guild.id}] Failed to edit modlog message. "
                    "Unknown error when attempting message edition.",
                    exc_info=e,
                )
                return False
            return True

        if len(new_reason) > 1024:
            raise errors.BadArgument("The reason must not be above 1024 characters.")
        case = await self.get_case(guild, user, index)
        case["reason"] = new_reason
        case["time"] = int(case["time"].timestamp())
        try:
            channel_id, message_id = case["modlog_message"].values()
        except KeyError:
            pass
        else:
            await edit_message(channel_id, message_id, new_reason)
        async with self.data.custom("MODLOGS", guild.id, user.id).x() as logs:
            logs[index - 1] = case
        log.debug(
            f"[Guild {guild.id}] Edited case #{index} from member {user} (ID: {user.id}). "
            f"New reason: {new_reason}"
        )
        return True

    async def delete_case(
        self,
        guild: discord.Guild,
        user: Union[discord.Member, UnavailableMember],
        index: int,
    ):
        async def delete_message(channel_id: int, message_id: int):
            channel: discord.TextChannel = guild.get_channel(channel_id)
            if channel is None:
                log.warn(
                    f"[Guild {guild.id}] Failed to delete modlog message. "
                    f"Channel {channel_id} not found."
                )
                return False
            try:
                message: discord.Message = await channel.fetch_message(message_id)
            except discord.errors.NotFound:
                log.warn(
                    f"[Guild {guild.id}] Failed to delete modlog message. "
                    f"Message {message_id} in channel {channel.id} not found."
                )
                return False
            except discord.errors.Forbidden:
                log.warn(
                    f"[Guild {guild.id}] Failed to delete modlog message. "
                    f"No permissions to fetch messages in channel {channel.id}."
                )
                return False
            except discord.errors.HTTPException as e:
                log.error(
                    f"[Guild {guild.id}] Failed to delete modlog message. API exception raised.",
                    exc_info=e,
                )
                return False
            try:
                await message.delete()
            except discord.errors.HTTPException as e:
                log.error(
                    f"[Guild {guild.id}] Failed to delete modlog message. "
                    "Unknown error when attempting message deletion.",
                    exc_info=e,
                )
                return False
            return True

        case = await self.get_case(guild, user, index)
        can_unmute = False
        add_roles = False
        if case["level"] == 2:
            mute_role = guild.get_role(await self.cache.get_mute_role(guild))
            member = guild.get_member(user)
            if member:
                if mute_role and mute_role in member.roles:
                    can_unmute = True
                add_roles = await self.data.guild(guild).remove_roles()
        if can_unmute:
            await member.remove_roles(mute_role, reason=_("Warning deleted."))
        async with self.data.custom("MODLOGS", guild.id, user.id).x() as logs:
            try:
                roles = logs[index - 1]["roles"]
            except KeyError:
                roles = []
            try:
                channel_id, message_id = logs[index - 1]["modlog_message"].values()
            except KeyError:
                pass
            else:
                await delete_message(channel_id, message_id)
            logs.remove(logs[index - 1])
        if add_roles and roles:
            roles = [guild.get_role(x) for x in roles]
            await member.add_roles(*roles, reason=_("Adding removed roles back after unmute."))
        log.debug(f"[Guild {guild.id}] Removed case #{index} from member {user} (ID: {user.id}).")
        return True

    async def get_modlog_channel(
        self, guild: discord.Guild, level: Optional[Union[int, str]] = None
    ) -> discord.TextChannel:
        """
        Get the WarnSystem's modlog channel on the current guild.

        When you call this, the channel is get with the following order:

        #.  Get the modlog channel associated to the type, if provided
        #.  Get the defult modlog channel set with WarnSystem
        #.  Get the Red's modlog channel associated to the server

        Parameters
        ----------
        guild: discord.Guild
            The guild you want to get the modlog from.
        level: Optional[Union[int, str]]
            Can be an :py:class:`int` between 1 and 5, a :py:class:`str` (``"all"``)
            or :py:obj:`None`.

            *   If the argument is omitted (or :py:obj:`None` is provided), the default modlog
                channel will be returned.

            *   If an :py:class:`int` is given, the modlog channel associated to this warning
                level will be returned. If a specific channel was not set for this level, the
                default modlog channel will be returned instead.

            *   If ``"all"`` is returned, a :py:class:`dict` will be returned. It should be built
                like this:

                .. code-block:: python3

                    {
                        "main"      : 012345678987654321,
                        "1"         : None,
                        "2"         : None,
                        "3"         : None,
                        "4"         : 478065433996537900,
                        "5"         : 567943553912O46428,
                    }

                A dict with the possible channels is returned, associated with an :py:class:`int`
                corresponding to the channel ID set, or :py:obj:`None` if it was not set.

                For technical reasons, the default channel is actually named ``"main"`` in the dict.

        Returns
        -------
        channel: discord.TextChannel
            The channel requested.

            .. note:: It can be :py:obj:`None` if the channel doesn't exist anymore.

        Raises
        ------
        ~warnsystem.errors.NotFound
            There is no modlog channel set with WarnSystem or Red, ask the user to set one.
        """
        # raise errors if the arguments are wrong
        if level:
            msg = "The level must be an int between 1 and 5 ; or a string that " 'should be "all"'
            if not isinstance(level, int) and level != "all":
                raise errors.InvalidLevel(msg)
            elif isinstance(level, int) and not 1 <= level <= 5:
                raise errors.InvalidLevel(msg)

        if level == "all":
            return await self.data.guild(guild).channels.all()
        default_channel = await self.data.guild(guild).channels.main()
        if level:
            channel = await self.data.guild(guild).channels.get_raw(str(level))
        else:
            return default_channel

        if not default_channel and not channel:
            # warnsystem default channel doesn't exist, let's try to get Red's one
            try:
                return await get_red_modlog_channel(guild)
            except RuntimeError:
                raise errors.NotFound("No modlog found from WarnSystem or Red")

        return self.bot.get_channel(channel if channel else default_channel)

    async def get_embeds(
        self,
        guild: discord.Guild,
        member: Union[discord.Member, UnavailableMember],
        author: Union[discord.Member, str],
        level: int,
        reason: Optional[str] = None,
        time: Optional[timedelta] = None,
        date: Optional[datetime] = None,
        message_sent: bool = True,
    ) -> tuple:
        """
        Return two embeds, one for the modlog and one for the member.

        .. warning:: Unlike for the warning, the arguments are not checked and won't raise errors
            if they are wrong. It is recommanded to call :func:`~warnsystem.api.API.warn` and let
            it generate the embeds instead.

        Parameters
        ----------
        guild: discord.Guild
            The Discord guild where the warning takes place.
        member: Union[discord.Member, UnavailableMember]
            The warned member. Should only be :class:`UnavailableMember` in case of a hack ban.
        author: Union[discord.Member, str]
            The moderator that warned the user. If it's not a Discord user, you can specify a
            :py:class:`str` instead (e.g. "Automod").
        level: int
            The level of the warning which should be between 1 and 5.
        reason: Optional[str]
            The reason of the warning.
        time: Optional[timedelta]
            The time before the action ends. Only for mute and ban.
        date: Optional[datetime]
            When the action was taken.
        message_sent: bool
            Set to :py:obj:`False` if the embed couldn't be sent to the warned user.

        Returns
        -------
        tuple
            A :py:class:`tuple` with the modlog embed at index 0, and the user embed at index 1.
        """
        action = {
            1: (_("warn"), _("warns")),
            2: (_("mute"), _("mutes")),
            3: (_("kick"), _("kicks")),
            4: (_("softban"), _("softbans")),
            5: (_("ban"), _("bans")),
        }.get(level, _("unknown"))
        mod_message = ""
        if not reason:
            reason = _("No reason was provided.")
            mod_message = _("\nEdit this with `[p]warnings {id}`").format(id=member.id)
        logs = await self.data.custom("MODLOGS", guild.id, member.id).x()

        # prepare the status field
        total_warns = len(logs) + 1
        total_type_warns = (
            len([x for x in logs if x["level"] == level]) + 1
        )  # number of warns of the received type

        # a lambda that returns a string; if True is given, a third person sentence is returned
        # (modlog), if False is given, a first person sentence is returned (DM user)
        current_status = lambda x: _(
            "{who} now {verb} {total} {warning} ({total_type} {action})"
        ).format(
            who=_("The member") if x else _("You"),
            verb=_("has") if x else _("have"),
            total=total_warns,
            warning=_("warnings") if total_warns > 1 else _("warning"),
            total_type=total_type_warns,
            action=action[1] if total_type_warns > 1 else action[0],
        )

        # we set any value that can be used multiple times
        invite = None
        log_description = await self.data.guild(guild).embed_description_modlog.get_raw(level)
        if "{invite}" in log_description:
            try:
                invite = await guild.create_invite(max_uses=1)
            except Exception:
                invite = _("*[couldn't create an invite]*")
        user_description = await self.data.guild(guild).embed_description_user.get_raw(level)
        if "{invite}" in user_description and not invite:
            try:
                invite = await guild.create_invite(max_uses=1)
            except Exception:
                invite = _("*[couldn't create an invite]*")
        if date:
            today = date.strftime("%a %d %B %Y %H:%M")
        else:
            today = datetime.now(timezone.utc)
        if time:
            duration = self._format_timedelta(time)
        else:
            duration = _("*[No time given]*")

        def format_description(text):
            try:
                return text.format(
                    invite=invite,
                    member=SafeMember(member),
                    mod=SafeMember(author),
                    duration=duration,
                    time=today,
                )
            except Exception:
                log.error(
                    f"[Guild {guild.id}] Failed to format description in embed", exc_info=True
                )
                return "Failed to format field."

        link = re.search(r"(https?://)\S+\.(jpg|jpeg|png|gif|webm)", reason)

        # embed for the modlog
        log_embed = discord.Embed()
        log_embed.set_author(
            name=f"{member.name} | {member.id}", icon_url=member.display_avatar.url
        )
        log_embed.title = _("Level {level} warning ({action})").format(
            level=level, action=action[0]
        )
        log_embed.description = format_description(log_description)
        log_embed.add_field(name=_("Member"), value=member.mention, inline=True)
        log_embed.add_field(name=_("Moderator"), value=author.mention, inline=True)
        if time:
            log_embed.add_field(name=_("Duration"), value=duration, inline=True)
        log_embed.add_field(name=_("Reason"), value=reason + mod_message, inline=False)
        log_embed.add_field(name=_("Status"), value=current_status(True), inline=False)
        log_embed.timestamp = date
        log_embed.set_thumbnail(url=await self.data.guild(guild).thumbnails.get_raw(level))
        log_embed.colour = await self.data.guild(guild).colors.get_raw(level)
        log_embed.url = await self.data.guild(guild).url()
        if link:
            log_embed.set_image(url=link.group())
        if not message_sent:
            log_embed.description += _(
                "\n\n***The message could not be delivered to the user. They may have DMs "
                "disabled, blocked the bot, or may not have a mutual server.***"
            )

        # embed for the member in DM
        user_embed = deepcopy(log_embed)
        user_embed.set_author(name="")
        user_embed.description = format_description(user_description)
        if mod_message:
            user_embed.set_field_at(3 if time else 2, name=_("Reason"), value=reason)
        user_embed.remove_field(4 if time else 3)  # removes status field (gonna be added back)
        user_embed.remove_field(0)  # removes member field
        user_embed.add_field(name=_("Status"), value=current_status(False), inline=False)
        if time:
            user_embed.set_field_at(
                1, name=_("Duration"), value=self._format_timedelta(time), inline=True
            )
        if not await self.data.guild(guild).show_mod():
            user_embed.remove_field(0)  # called twice, removing moderator field

        return (log_embed, user_embed)

    async def maybe_create_mute_role(self, guild: discord.Guild) -> bool:
        """
        Create the mod role for WarnSystem if it doesn't exist.
        This will also edit all channels to deny the following permissions to this role:

        *   ``send_messages``
        *   ``add_reactions``
        *   ``speak``

        Parameters
        ----------
        guild: discord.Guild
            The guild you want to set up the mute in.

        Returns
        -------
        Union[bool, list]
            *   :py:obj:`False` if the role already exists.
            *   :py:class:`list` if the role was created, with a list of errors for each channel.
                Empty list means completly successful edition.

        Raises
        ------
        ~warnsystem.errors.MissingPermissions
            The bot lacks the :attr:`discord.Permissions.create_roles` permission.
        discord.errors.HTTPException
            Creating the role failed.
        """
        role = await self.cache.get_mute_role(guild)
        role = guild.get_role(role)
        if role:
            return False

        if not guild.me.guild_permissions.manage_roles:
            raise errors.MissingPermissions(
                _("I can't manage roles, please give me this permission to continue.")
            )

        # no mod role on this guild, let's create one
        role = await guild.create_role(
            name="Muted",
            reason=_(
                "WarnSystem mute role. This role will be assigned to the muted members, "
                "feel free to move it or modify its channel permissions."
            ),
        )
        await asyncio.sleep(0.5)  # prevents an error when repositionning the role
        await role.edit(
            position=guild.me.top_role.position - 1,
            reason=_(
                "Modifying role's position, keep it under my top role so "
                "I can add it to muted members."
            ),
        )
        perms = discord.PermissionOverwrite(send_messages=False, add_reactions=False, speak=False)
        errors = []
        for channel in guild.channels:
            try:
                await channel.set_permissions(
                    target=role,
                    overwrite=perms,
                    reason=_(
                        "Setting up WarnSystem mute. All muted members will have this role, "
                        "feel free to edit its permissions."
                    ),
                )
            except discord.errors.Forbidden:
                errors.append(
                    _(
                        "Cannot edit permissions of the channel {channel} because of a "
                        "permission error (probably enforced permission for `Manage channel`)."
                    ).format(channel=channel.mention)
                )
            except discord.errors.HTTPException as e:
                errors.append(
                    _(
                        "Cannot edit permissions of the channel {channel} because of "
                        "an unknown error."
                    ).format(channel=channel.mention)
                )
                log.warn(
                    f"[Guild {guild.id}] Couldn't edit permissions of {channel} (ID: "
                    f"{channel.id}) for setting up the mute role because of an HTTPException.",
                    exc_info=e,
                )
            except Exception as e:
                errors.append(
                    _(
                        "Cannot edit permissions of the channel {channel} because of "
                        "an unknown error."
                    ).format(channel=channel.mention)
                )
                log.error(
                    f"[Guild {guild.id}] Couldn't edit permissions of {channel} (ID: "
                    f"{channel.id}) for setting up the mute role because of an unknwon error.",
                    exc_info=e,
                )
        await self.cache.update_mute_role(guild, role)
        return errors

    async def format_reason(self, guild: discord.Guild, reason: str = None) -> str:
        """
        Reformat a reason with the substitutions set on the guild.

        Parameters
        ----------
        guild: discord.Guild
            The guild where the warn is set.
        reason: str
            The string you want to reformat.

        Returns
        -------
        str
            The reformatted string
        """
        if not reason:
            return
        substitutions = await self.data.guild(guild).substitutions()
        for key, substitute in substitutions.items():
            reason = reason.replace(f"[{key}]", substitute)
        return reason

    async def warn(
        self,
        guild: discord.Guild,
        members: Iterable[Union[discord.Member, UnavailableMember]],
        author: Union[discord.Member, str],
        level: int,
        reason: Optional[str] = None,
        time: Optional[timedelta] = None,
        date: Optional[datetime] = None,
        ban_days: Optional[int] = None,
        log_modlog: Optional[bool] = True,
        log_dm: Optional[bool] = True,
        take_action: Optional[bool] = True,
        automod: Optional[bool] = True,
        progress_tracker: Optional[Callable[[int], Awaitable[None]]] = None,
    ) -> bool:
        """
        Set a warning on a member of a Discord guild and log it with the WarnSystem system.

        .. tip:: The message that comes with the following exceptions are already
            translated and ready to be sent to Discord:

            *   :class:`~warnsystem.errors.NotFound`
            *   :class:`~warnsystem.errors.LostPermissions`
            *   :class:`~warnsystem.errors.MemberTooHigh`
            *   :class:`~warnsystem.errors.MissingPermissions`
            *   :class:`~warnsystem.errors.SuicidePrevention`

        Parameters
        ----------
        guild: discord.Guild
            The guild of the member to warn
        member: Iterable[Union[discord.Member, UnavailableMember]]
            The member that will be warned. It can be an instance of
            :py:class:`warnsystem.api.UnavailableMember` if you need
            to ban someone not in the guild.
        author: Union[discord.Member, str]
            The member that called the action, which will be associated to the log.
        level: int
            An :py:class:`int` between 1 and 5, specifying the warning level:

            #.  Simple DM warning
            #.  Mute (can be temporary)
            #.  Kick
            #.  Softban
            #.  Ban (can be temporary ban, or hack ban, if the member is not in the server)
        reason: Optional[str]
            The optional reason of the warning. It is strongly recommanded to set one.
        time: Optional[timedelta]
            The time before cancelling the action. This only works for a mute or a ban.
        date: Optional[datetime]
            When the action was taken. Only use if you want to overwrite the current date and time.
        ban_days: Optional[int]
            Overwrite number of days of messages to delete for a ban. Only used for warnings
            level 4 or 5. If this is omitted, the bot will fall back to the user defined setting.
        log_modlog: Optional[bool]
            Specify if an embed should be posted to the modlog channel. Default to :py:obj:`True`.
        log_dm: Optional[bool]
            Specify if an embed should be sent to the warned user. Default to :py:obj:`True`.
        take_action: Optional[bool]
            Specify if the bot should take action on the member (mute, kick, softban, ban). If set
            to :py:obj:`False`, the bot will only send a log embed to the member and in the modlog.
            Default to :py:obj:`True`.
        automod: Optional[bool]
            Set to :py:obj:`False` to skip automod, preventing multiple warnings at once and
            saving performances. Automod might trigger on a next warning though.
        progress_tracker: Optional[Callable[[int], Awaitable[None]]]
            an async callable (function or lambda) which takes one argument to follow the progress
            of the warn. The argument is the number of warns committed. Here's an example:

            .. code-block:: python3

                i = 0
                message = await ctx.send("Mass warn started...")

                async def update_count(count):
                    i = count

                async def update_msg():
                    await message.edit(content=f"{i}/{len(members)} members warned.")
                    await asyncio.sleep(1)

                await api.warn(guild, members, ctx.author, 1, progress_tracker=update_count)

        Returns
        -------
        dict
            A dict of members which couldn't be warned associated to the exception related.


        Raises
        ------
        ~warnsystem.errors.InvalidLevel
            The level must be an :py:class:`int` between 1 and 5.
        ~warnsystem.errors.BadArgument
            You need to provide a valid :class:`discord.Member` object, except for a
            hackban where a :class:`discord.User` works.
        ~warnsystem.errors.MissingMuteRole
            You're trying to mute someone but the mute role was not setup yet.
            You can fix this by calling :func:`~warnsystem.api.API.maybe_create_mute_role`.
        ~warnsystem.errors.LostPermissions
            The bot lost a permission to do something (it had the perm before). This
            can be lost permissions for sending messages to the modlog channel or
            interacting with the mute role.
        ~warnsystem.errors.MemberTooHigh
            The bot is trying to take actions on someone but their top role is higher
            than the bot's top role in the guild's hierarchy.
        ~warnsystem.errors.NotAllowedByHierarchy
            The moderator trying to warn someone is lower than them in the role hierarchy,
            while the bot still has permissions to act. This is raised only if the
            hierarchy check is enabled.
        ~warnsystem.errors.MissingPermissions
            The bot lacks a permissions to do something. Can be adding role, kicking
            or banning members.
        discord.errors.NotFound
            When the user ID provided for hackban isn't recognized by Discord.
        discord.errors.HTTPException
            Unknown error from Discord API. It's recommanded to catch this
            potential error too.
        """

        async def warn_member(member: Union[discord.Member, UnavailableMember], audit_reason: str):
            nonlocal i
            roles = []
            # permissions check
            if level > 1 and guild.me.top_role.position <= member.top_role.position:
                # check if the member is below the bot in the roles's hierarchy
                return errors.MemberTooHigh(
                    _(
                        "Cannot take actions on this member, they are "
                        "above me in the roles hierarchy. Modify "
                        "the hierarchy so my top role ({bot_role}) is above {member_role}."
                    ).format(bot_role=guild.me.top_role.name, member_role=member.top_role.name)
                )
            if await self.data.guild(guild).respect_hierarchy() and (
                not (await self.bot.is_owner(author) or author.id == guild.owner_id)
                and member.top_role.position >= author.top_role.position
            ):
                return errors.NotAllowedByHierarchy(
                    "The moderator is lower than the member in the servers's role hierarchy."
                )
            if level > 2 and member.id == guild.owner_id:
                return errors.MissingPermissions(
                    _("I can't take actions on the owner of the guild.")
                )
            if member == guild.me:
                return errors.SuicidePrevention(
                    _(
                        "Why would you warn me? I did nothing wrong :c\n"
                        "(use a manual kick/ban instead, warning the bot will cause issues)"
                    )
                )
            # send the message to the user
            if log_modlog or log_dm:
                modlog_e, user_e = await self.get_embeds(
                    guild, member, author, level, reason, time, date
                )
            if log_dm:
                try:
                    await member.send(embed=user_e)
                except (discord.errors.Forbidden, errors.UserNotFound):
                    modlog_e = (
                        await self.get_embeds(
                            guild, member, author, level, reason, time, date, message_sent=False
                        )
                    )[0]
                except discord.errors.NotFound:
                    raise
                except discord.errors.HTTPException as e:
                    modlog_e = (
                        await self.get_embeds(
                            guild, member, author, level, reason, time, date, message_sent=False
                        )
                    )[0]
                    log.warn(
                        f"[Guild {guild.id}] Couldn't send a message to {member} "
                        f"(ID: {member.id}) because of an HTTPException.",
                        exc_info=e,
                    )
            # take actions
            if take_action:
                audit_reason = audit_reason.format(member=member)
                try:
                    if level == 2:
                        roles = await self._mute(member, audit_reason)
                    elif level == 3:
                        await guild.kick(member, reason=audit_reason)
                    elif level == 4:
                        await guild.ban(
                            member,
                            reason=audit_reason,
                            delete_message_seconds=(
                                ban_days or await self.data.guild(guild).bandays.softban()
                            )
                            * 24
                            * 3600,
                        )
                        await guild.unban(
                            member,
                            reason=_(
                                "Unbanning the softbanned member after cleaning up the messages."
                            ),
                        )
                    elif level == 5:
                        await guild.ban(
                            member,
                            reason=audit_reason,
                            delete_message_seconds=(
                                ban_days or await self.data.guild(guild).bandays.ban()
                            )
                            * 24
                            * 3600,
                        )
                except discord.errors.HTTPException as e:
                    log.warn(
                        f"[Guild {guild.id}] Failed to warn {member} because of "
                        "an unknown error from Discord.",
                        exc_info=e,
                    )
                    return e
            # actions were taken, time to log
            if log_modlog:
                modlog_message = await mod_channel.send(embed=modlog_e)
            else:
                modlog_message = None
            data = await self._create_case(
                guild, member, author, level, date, reason, time, roles, modlog_message
            )
            # start timer if there is a temporary warning
            if time and (level == 2 or level == 5):
                await self._start_timer(guild, member, data)
            if automod:
                # This function can be pretty heavy, and the response can be seriously delayed
                # because of this, so we make it a side process instead
                self.bot.loop.create_task(
                    self.automod_check_for_autowarn(guild, member, author, level)
                )
            self.bot.dispatch(
                "warnsystem_warn",
                member=member,
                author=author,
                level=level,
                reason=reason,
                time=time,
                date=date,
            )
            i += 1
            if progress_tracker:
                await progress_tracker(i)

        if not 1 <= level <= 5:
            raise errors.InvalidLevel("The level must be between 1 and 5.")
        # we get the modlog channel now to make sure it exists before doing anything
        if log_modlog:
            mod_channel = await self.get_modlog_channel(guild, level)
        # check if the mute role exists
        mute_role = guild.get_role(await self.cache.get_mute_role(guild))
        if not mute_role and level == 2:
            raise errors.MissingMuteRole("You need to create the mute role before doing this.")
        # we check for all permission problem that can occur before calling the API
        # checks if the bot has send_messages and embed_links permissions in modlog channel
        if not (
            guild.me.guild_permissions.send_messages and guild.me.guild_permissions.embed_links
        ):
            raise errors.LostPermissions(
                _(
                    "I need the `Send messages` and `Embed links` "
                    "permissions in {channel} to do this."
                ).format(channel=mod_channel.mention)
            )
        if level == 2:
            # mute with role
            if not guild.me.guild_permissions.manage_roles:
                raise errors.MissingPermissions(
                    _("I can't manage roles, please give me this permission to continue.")
                )
            if mute_role.position >= guild.me.top_role.position:
                raise errors.LostPermissions(
                    _(
                        "The mute role `{mute_role}` was moved above my top role `{my_role}`. "
                        "Please move the roles so my top role is above the mute role."
                    ).format(mute_role=mute_role.name, my_role=guild.me.top_role.name)
                )
        if level == 3:
            # kick
            if not guild.me.guild_permissions.kick_members:
                raise errors.MissingPermissions(
                    _("I can't kick members, please give me this permission to continue.")
                )
        if level >= 4:
            # softban or ban
            if not guild.me.guild_permissions.ban_members:
                raise errors.MissingPermissions(
                    _("I can't ban members, please give me this permission to continue.")
                )

        action = {1: _("warn"), 2: _("mute"), 3: _("kick"), 4: _("softban"), 5: _("ban")}.get(
            level, _("unknown")
        )
        audit_reason = _(
            "[WarnSystem] {action} requested by {author} (ID: {author.id}) against {member}. "
        ).format(
            author=author, action=action, member="{member}"
        )  # member will be edited later
        if time:
            audit_reason += _("\n\nDuration: {time} ").format(time=self._format_timedelta(time))
        if reason:
            if len(audit_reason + reason) < 490:
                audit_reason += _("Reason: {reason}").format(reason=reason)
            else:
                audit_reason += _("Reason too long to be shown.")
        if not date:
            date = datetime.now(timezone.utc)

        i = 0
        fails = [await warn_member(x, audit_reason) for x in members if x]
        # all good!
        return list(filter(None, fails))

    async def _check_endwarn(self):
        async def reinvite(guild, user, reason, duration):
            channel = next(
                (
                    c  # guild.text_channels is already sorted by position
                    for c in guild.text_channels
                    if c.permissions_for(guild.me).create_instant_invite
                ),
                None,
            )
            if channel is None:
                # can't find a valid channel
                log.info(
                    f"[Guild {guild.id}] Can't find a text channel where I can create an invite "
                    f"when reinviting {member} (ID: {member.id}) after its unban."
                )
                return

            try:
                invite = await channel.create_invite(max_uses=1)
            except Exception as e:
                log.warn(
                    f"[Guild {guild.id}] Couldn't create an invite to reinvite "
                    f"{member} (ID: {member.id}) after its unban.",
                    exc_info=e,
                )
            else:
                try:
                    await member.send(
                        _(
                            "You were unbanned from {guild}, your temporary ban (reason: "
                            "{reason}) just ended after {duration}.\nYou can join back using this "
                            "invite: {invite}"
                        ).format(guild=guild.name, reason=reason, duration=duration, invite=invite)
                    )
                except discord.errors.Forbidden:
                    # couldn't send message to the user, quite common
                    log.info(
                        f"[Guild {guild.id}] Couldn't reinvite member {member} "
                        f"(ID: {member.id}) after its temporary ban."
                    )

        now = datetime.now(timezone.utc)
        for guild in self.bot.guilds:
            data = await self.cache.get_temp_action(guild)
            if not data:
                continue
            to_remove = []
            for member_id, action in data.items():
                member_id = int(member_id)
                try:
                    taken_on = self._get_datetime(action["time"])
                    duration = self._get_timedelta(action["duration"])
                except ValueError as e:
                    log.error(
                        f"[Guild {guild.id}] Time or duration cannot be fetched. This is "
                        "probably leftovers from the conversion of post 1.3 data. Removing the "
                        f"temp warning, not taking actions... Member: {member_id}, data: {action}",
                        exc_info=e,
                    )
                    to_remove.append(UnavailableMember(self.bot, guild._state, member_id))
                    continue
                author = guild.get_member(action["author"])
                member = guild.get_member(member_id)
                case_reason = action["reason"]
                level = action["level"]
                action_str = _("mute") if level == 2 else _("ban")
                if not member:
                    member = UnavailableMember(self.bot, guild._state, member_id)
                    if level == 2:
                        to_remove.append(member)
                        continue
                roles = list(filter(None, [guild.get_role(x) for x in action.get("roles") or []]))

                reason = _(
                    "End of timed {action} of {member} requested by {author} that lasted "
                    "for {time}. Reason of the {action}: {reason}"
                ).format(
                    action=action_str,
                    member=member,
                    author=author if author else action["author"],
                    time=self._format_timedelta(duration),
                    reason=case_reason,
                )
                if (taken_on + duration) < now:
                    # end of warn
                    try:
                        if level == 2:
                            await self._unmute(member, reason=reason, old_roles=roles)
                        if level == 5:
                            await guild.unban(member, reason=reason)
                            if await self.data.guild(guild).reinvite():
                                await reinvite(
                                    guild,
                                    member,
                                    case_reason,
                                    self._format_timedelta(timedelta(seconds=action["duration"])),
                                )
                    except discord.errors.Forbidden:
                        log.warn(
                            f"[Guild {guild.id}] I lost required permissions for "
                            f"ending the timed {action_str}. Member {member} (ID: {member_id}) "
                            "will stay as it is now."
                        )
                    except discord.errors.HTTPException as e:
                        log.warn(
                            f"[Guild {guild.id}] Couldn't end the timed {action_str} of {member} "
                            f"(ID: {member_id}). He will stay as it is now.",
                            exc_info=e,
                        )
                    else:
                        log.debug(
                            f"[Guild {guild.id}] Ended timed {action_str} of {member} (ID: "
                            f"{member_id}) taken on {self._format_datetime(taken_on)} requested "
                            f"by {author} (ID: {author.id if author else action['author']}) "
                            f"that lasted for {self._format_timedelta(duration)} for the "
                            f"reason {case_reason}\n"
                            f"Current time: {now}\nExpected end time of warn: "
                            f"{self._format_datetime(taken_on + duration)}"
                        )
                    to_remove.append(member)
            if to_remove:
                await self.cache.bulk_remove_temp_action(guild, to_remove)

    async def _loop_task(self):
        """
        This is an infinite loop task started with the cog that will check\
        if a temporary warn (mute or ban) is over, and cancel the action if it's true.

        The loop runs every 10 seconds.
        """
        await self.bot.wait_until_ready()
        log.debug(
            "Starting infinite loop for unmutes and unbans. Canel the "
            'task with bot.get_cog("WarnSystem").task.cancel()'
        )
        errors = 0
        while True:
            try:
                await self._check_endwarn()
            except Exception as e:
                errors += 1
                if errors >= 3:
                    # more than 3 errors in our loop, let's shut down the loop
                    log.critical(
                        "The loop for unmutes and unbans encountered a third error. To prevent "
                        "more damages, the loop will be cancelled. Timed mutes and bans no longer "
                        "works for now. Reload the cog to start the loop back. If the problem "
                        "persists, report the error and update the cog.",
                        exc_info=e,
                    )
                    return
                log.error(
                    "Error in loop for unmutes and unbans. The loop will be resumed.", exc_info=e
                )
            await asyncio.sleep(10)

    # automod stuff
    def enable_automod(self):
        """
        Enable automod checks and listeners on the bot.
        """
        log.info("Enabling automod listeners and event loops.")
        self.bot.add_listener(self.automod_on_message, name="on_message")
        self.automod_warn_task = self.bot.loop.create_task(self.automod_warn_loop())

    def disable_automod(self):
        """
        Disable automod checks and listeners on the bot.
        """
        log.info("Disabling automod listeners and event loops.")
        self.bot.remove_listener(self.automod_on_message, name="on_message")
        if hasattr(self, "automod_warn_task"):
            self.automod_warn_task.cancel()

    async def _check_if_automod_valid(self, message: discord.Message):
        guild = message.guild
        member = message.author
        if not guild:
            return False
        if member.bot:
            return False
        if guild.owner_id == member.id:
            return False
        if not self.cache.is_automod_enabled(guild):
            return False
        if await self.bot.is_automod_immune(message):
            return False
        if await self.bot.is_mod(member):
            return False
        return True

    async def automod_on_message(self, message: discord.Message):
        if not await self._check_if_automod_valid(message):
            return
        # we run all tasks concurrently
        # results are returned in the same order (either None or an exception)
        regex_exception, antispam_exception = await asyncio.gather(
            self.automod_process_regex(message),
            self.automod_process_antispam(message),
            return_exceptions=True,
        )
        if regex_exception:
            log.error(
                f"[Guild {message.guild.id}] Error while processing message for regex automod.",
                exc_info=regex_exception,
            )
        if antispam_exception:
            log.error(
                f"[Guild {message.guild.id}] Error while processing message for antispam system.",
                exc_info=antispam_exception,
            )

    async def automod_on_message_edit(self, before: discord.Message, after: discord.Message):
        if not await self._check_if_automod_valid(after):
            return
        try:
            await self.automod_process_regex(after)
        except Exception as e:
            log.error(
                f"[Guild {after.guild.id}] Error while "
                "processing edited message for regex automod.",
                exc_info=e,
            )

    async def _safe_regex_search(self, regex: re.Pattern, message: discord.Message):
        """
        Mostly safe regex search to prevent reDOS from user defined regex patterns

        This works by running the regex pattern inside a process pool defined at the
        cog level and then checking that process in the default executor to keep
        things asynchronous. If the process takes too long to complete we log a
        warning and remove the trigger from trying to run again.

        This function was fully made by TrustyJAID for Trusty-cogs/retrigger (amazing cog btw)
        https://github.com/TrustyJAID/Trusty-cogs/blob/f08a88040dcc67291a463517a70dcbbe702ba8e3/retrigger/triggerhandler.py#L494
        """
        guild = message.guild
        try:
            process = self.re_pool.apply_async(regex.findall, (message.content,))
            task = functools.partial(process.get, timeout=self.regex_timeout)
            new_task = self.bot.loop.run_in_executor(None, task)
            search = await asyncio.wait_for(new_task, timeout=self.regex_timeout + 5)
        except TimeoutError:
            error_msg = (
                f"[Guild {guild.id}] Automod: regex process took too long. "
                f"Removing from memory. Offending regex: {regex.pattern}"
            )
            log.warning(error_msg)
            return (False, [])
            # we certainly don't want to be performing multiple triggers if this happens
        except asyncio.TimeoutError:
            error_msg = (
                f"[Guild {guild.id}] Automod: regex asyncio timed out. "
                f"Removing from memory. Offending regex: {regex.pattern}"
            )
            log.warning(error_msg)
            return (False, [])
        except Exception:
            log.error(
                f"[Guild {guild.id}] Automod regex encountered an error with {regex.pattern}",
                exc_info=True,
            )
            return (True, [])
        else:
            return (True, search)

    async def automod_process_regex(self, message: discord.Message):
        guild = message.guild
        member = message.author
        all_regex = await self.cache.get_automod_regex(guild)
        for name, regex in all_regex.items():
            result = await self._safe_regex_search(regex["regex"], message)
            if not result[1]:
                if result[0] is False:
                    await self.cache.remove_automod_regex(guild, name)
                continue
            time = None
            if regex["time"]:
                time = self._get_timedelta(regex["time"])
            level = regex["level"]
            reason = regex["reason"].format(guild=guild, channel=message.channel, member=member)
            fail = await self.warn(guild, [member], guild.me, level, reason, time)
            if fail:
                log.warn(
                    f"[Guild {guild.id}] Regex automod warn on member {member} ({member.id})\n"
                    f"Level: {level}. Time: {time}. Reason: {reason}\n"
                    f"Original message: {message.content}\n"
                    f"Automatic warn failed due to the following exception:",
                    exc_info=fail[0],
                )
            else:
                log.info(
                    f"[Guild {guild.id}] Regex automod warn on member {member} ({member.id})\n"
                    f"Level: {level}. Time: {time}. Reason: {reason}\n"
                    f"Original message: {message.content}"
                )

    async def automod_process_antispam(self, message: discord.Message):
        # we store the data in self.antispam
        # keys are as follow: GUILD_ID > CHANNEL_ID > MEMBER_ID = tuple
        # tuple contains list timestamps of recent messages + check if the member was warned
        # if the antispam is triggered once, we send a message in the chat (refered as text warn)
        # if it's triggered a second time, an actual warn is given
        guild = message.guild
        channel = message.channel
        member = message.author
        antispam_data = await self.cache.get_automod_antispam(guild)
        if antispam_data is False:
            return
        for word in antispam_data["whitelist"]:
            if word in message.content:
                return

        # we slowly go across each key, if it doesn't exist, data is created then the
        # function ends since there's no data to check
        InitialData = namedtuple("InitialData", ["messages", "warned"])
        data = InitialData(messages=[], warned=False)
        try:
            guild_data = self.antispam[guild.id]
        except KeyError:
            self.antispam[guild.id] = {channel.id: {member.id: data}}
            return
        else:
            pass
        try:
            channel_data = guild_data[channel.id]
        except KeyError:
            self.antispam[guild.id][channel.id] = {member.id: data}
            return
        else:
            del guild_data
        try:
            data = channel_data[member.id]
        except KeyError:
            pass
        del channel_data

        data.messages.append(message.created_at)
        # now we've got our list of timestamps, just gotta clean the old ones
        data = data._replace(
            messages=self._automod_clean_old_messages(
                antispam_data["delay"], message.created_at, data.messages
            )
        )
        if len(data.messages) <= antispam_data["max_messages"]:
            # antispam not triggered, we can exit now
            self.antispam[guild.id][channel.id][member.id] = data
            return
        # at this point, user is considered to be spamming
        # we cleanup their x last messages (max_messages + 1), then either send a text warn
        # or perform an actual warnsystem warn (I'm confusing ik)
        if (
            data.warned is False
            or (datetime.now() - data.warned).total_seconds()
            < antispam_data["delay_before_action"]
        ):
            bot_message = await channel.send(
                _("{member} you're sending messages too fast!").format(member=member.mention),
                delete_after=5,
            )
            data = InitialData(messages=[], warned=bot_message.created_at)
        else:
            # already warned once within delay_before_action, gotta take actions
            warn_data = antispam_data["warn"]
            warn_data["author"] = guild.me
            if warn_data["time"]:
                warn_data["time"] = self._get_timedelta(warn_data["time"])
            try:
                self.antispam_warn_queue[guild.id][member] = warn_data
            except KeyError:
                self.antispam_warn_queue[guild.id] = {member: warn_data}
            # also reset the data
            data = InitialData(messages=[], warned=message.created_at)
        self.antispam[guild.id][channel.id][member.id] = data

    def _automod_clean_old_messages(self, delay: int, current_time: datetime, messages: list):
        """
        We don't keep messages older than the delay in the cache
        """
        message: datetime
        delta: timedelta
        new_list = []
        for message in messages:
            delta = current_time - message
            if delta.total_seconds() <= delay:
                new_list.append(message)
        return new_list

    def _automod_clean_cache(
        self, guild: discord.Guild, channel: discord.TextChannel, member: discord.Member
    ):
        """
        We quickly end up with a dict filled with empty values, we gotta clean that.
        """
        del self.automod[guild.id][channel.id][member.id]
        if not self.automod[guild.id][channel.id]:
            del self.automod[guild.id][channel.id]
            if not self.automod[guild.id]:
                del self.automod[guild.id]

    async def automod_check_for_autowarn(
        self, guild: discord.Guild, member: discord.Member, author: discord.Member, level: int
    ):
        """
        Iterate through member's modlog, looking for possible automatic warns.

        Level is the last warning's level, which will filter a lot of possible autowarns and,
        therefore, save performances.

        This can be a heavy call if there are a lot of possible autowarns and a long modlog.
        """
        t = datetime.now()
        try:
            await self._automod_check_for_autowarn(guild, member, author, level)
        except Exception as e:
            log.error(f"[Guild {guild.id}] A problem occured with automod check.", exc_info=e)
        time_taken: timedelta = datetime.now() - t
        if time_taken.total_seconds() > 10 and guild.id not in self.warned_guilds:
            self.warned_guilds.append(guild.id)
            log.warning(
                f"[Guild {guild.id}] Automod check took a long time! Time taken: {time_taken}\n"
                "Try to reduce the amount of warns/autowarns or blame Laggron for poorly "
                "written code (second option is preferred).\nThis warning will not show again "
                "for this guild until reload."
            )

    async def _automod_check_for_autowarn(
        self, guild: discord.Guild, member: discord.Member, author: discord.Member, level: int
    ):
        """
        Prevents having to put this whole function into a try/except block.
        """
        if not self.cache.is_automod_enabled(guild):
            return
        # starting the iteration through warnings can cost performances
        # so we look for conditions that confirms the member cannot be affected by automod
        if await self.bot.is_automod_immune(member):
            return
        warns = await self.get_all_cases(guild, member)
        if len(warns) < 2:
            return  # autowarn can't be triggered with a single warning in the modlog
        autowarns = await self.data.guild(guild).automod.warnings()
        # remove all autowarns that are locked to a specific level
        # where the last warning's level doesn't correspond
        # also remove autowarns that are automod only if warn author isn't the bot

        def is_autowarn_valid(warn):
            if author.id != self.bot.user.id and warn["automod_only"]:
                return False
            return warn["level"] == 0 or warn["level"] == level

        autowarns = list(filter(is_autowarn_valid, autowarns))
        if not autowarns:
            return  # no autowarn to iterate through
        for i, autowarn in enumerate(autowarns):
            # prepare for iteration
            autowarns[i]["count"] = 0
            # if the condition is met (within the specified time? not an automatic warn?)
            # we increase this value until reaching the given limit
            time = autowarn["time"]
            if time:
                until = datetime.now(timezone.utc) - timedelta(seconds=time)
                autowarns[i]["until"] = until
        del time
        found_warnings = {}  # we fill this list with the valid autowarns, there can be more than 1
        for warn in warns[::-1]:
            to_remove = []  # list of autowarns to remove during the iteration (duration expired)
            taken_on = datetime.fromtimestamp(warn["time"], timezone.utc)
            for i, autowarn in enumerate(autowarns):
                try:
                    if autowarn["until"] >= taken_on:
                        to_remove.append(i)
                        continue
                except KeyError:
                    pass
                autowarns[i]["count"] += 1
                if autowarns[i]["count"] == autowarn["number"]:
                    found_warnings[i] = autowarn["warn"]
                if autowarns[i]["count"] > autowarn["number"]:
                    # value exceeded, no need to continue, it's already done for this one warn
                    to_remove.append(i)
                    del found_warnings[i]
            for index in reversed(to_remove):
                autowarns.pop(index)
            if not autowarns:
                # we could be out of autowarns to check after a certain time
                # no need to continue the iteration
                break
        del to_remove, taken_on, autowarns
        for i, warn in found_warnings.items():
            try:
                await self.warn(
                    guild,
                    members=[member],
                    author=guild.me,
                    level=warn["level"],
                    reason=warn["reason"],
                    time=self._get_timedelta(warn["duration"]) if warn["duration"] else None,
                )
            except Exception as e:
                log.error(
                    f"[Guild {guild.id}] Failed to perform automod warn on member {member} "
                    f"({member.id}). Needed to perform automatic warn {i}",
                    exc_info=e,
                )
            else:
                log.debug(
                    f"[Guild {guild.id}] Successfully performed automatic "
                    f"warn {i} on member {member} ({member.id})."
                )

    async def automod_warn_loop(self):
        # since this is asyncronous code, sometimes there can be too many warnings performed
        # especially with message antispam, since it treats multiple messages simultaneously
        # instead, we have a dict of warnings to perform, and we remove it only once the warn is
        # done. That way, duplicate warnings won't happen.

        async def warn(member: discord.Member, data: dict):
            guild = member.guild
            try:
                await self.warn(guild, [member], **data)
            except Exception as e:
                log.error(
                    f"Cannot perform autowarn on member {member} ({member.id}). Data: {data}",
                    exc_info=e,
                )
            finally:
                await asyncio.sleep(1)
                del self.antispam_warn_queue[guild.id][member]
                if not self.antispam_warn_queue[guild.id]:
                    del self.antispam_warn_queue[guild.id]

        async def loop():
            guild: discord.Guild
            member: discord.Member
            coros = []
            for guild_id, data in self.antispam_warn_queue.items():
                for member, value in data.items():
                    coros.append(warn(member, value))
            coros = asyncio.gather(*coros, return_exceptions=True)
            await coros

        errors = 0
        while True:
            try:
                await loop()
            except Exception as e:
                errors += 1
                if errors >= 3:
                    # more than 3 errors in our loop, let's shut down the loop
                    log.critical(
                        "The loop for automod warnings encountered a third error. To prevent "
                        "more damages, the loop will be cancelled. Timed mutes and bans no longer "
                        "works for now. Reload the cog to start the loop back. If the problem "
                        "persists, report the error and update the cog.",
                        exc_info=e,
                    )
                    return
                log.error(
                    "Error in loop for automod warnings. The loop will be resumed.", exc_info=e
                )
            await asyncio.sleep(1)
