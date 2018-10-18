import discord
import logging
import inspect

from copy import deepcopy
from typing import Union, Optional
from datetime import datetime, timedelta

from .bettermod import _  # translator
from . import errors

log = logging.getLogger("laggron.bettermod")
if logging.getLogger("red").isEnabledFor(logging.DEBUG):
    # debug mode enabled
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.WARNING)


class API:
    """
    Interact with BetterMod from your cog.

    To import the cog and use the functions, type this in your code:

    .. code-block:: python

        bettermod = bot.get_cog('BetterMod').api

    .. warning:: If ``bettermod`` is :py:obj:`None`, the cog is
      not loaded/installed. You won't be able to interact with
      the API at this point.

    .. tip:: You can get the cog version by doing this

        .. code-block:: python

            version = bot.get_cog('BetterMod').__version__
    """

    def __init__(self, bot, config):
        self.bot = bot
        self.data = config

        # importing this here prevents a RuntimeError when building the documentation
        global get_red_modlog_channel
        from redbot.core.modlog import get_modlog_channel as get_red_modlog_channel

    def _log_call(self, stack):
        """Create a debug log for each BMod API call."""
        try:
            caller = (
                stack[0][3],
                stack[1][0].f_locals["self"].__class__,
                stack[1][0].f_code.co_name,
            )
            if caller[1] != self:
                log.debug(f"API.{caller[0]} called by {caller[1].__name__}.{caller[2]}")
        except Exception:
            # this should not block the action
            pass

    def _get_datetime(self, time: str) -> datetime:
        return datetime.strptime(time, "%a %d %B %Y %H:%M")

    async def _create_case(
        self,
        guild: discord.Guild,
        user: discord.User,
        author: Union[discord.Member, str],
        level: int,
        time: datetime,
        reason: Optional[str] = None,
        duration: Optional[datetime] = None,
        success: bool = True,
    ):
        """Create a new case for a member. Don't call this, call warn instead."""
        data = {
            "level": level,
            "author": author if not isinstance(author, discord.User) else author.id,
            "reason": reason,
            "time": time.strftime("%a %d %B %Y %H:%M"),
            "success": success,
            "duration": None if not duration else duration.strftime("%a %d %B %Y %H:%M"),
        }
        async with self.data.custom("MODLOGS", guild.id, user.id).x() as logs:
            logs.append(data)

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
                    "success"   : bool,  # if the action was successful
                }

        Raises
        ------
        ~bettermod.errors.NotFound
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
                        "success"   : bool,  # if the action was successful
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
                    "success"   : bool,  # if the action was successful

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
                author = guild.get_member(log["author"])
                time = log["time"]
                if time:
                    log["time"] = self._get_datetime(time)
                log["member"] = self.bot.get_user(member)
                log["author"] = author if author else log["author"]  # can be None or a string
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
        ~bettermod.errors.BadArgument
            The reason is above 1024 characters. Due to Discord embed rules, you have to make it
            shorter.
        ~bettermod.errors.NotFound
            The case requested doesn't exist.
        """
        if len(new_reason) > 1024:
            raise errors.BadArgument("The reason must not be above 1024 characters.")
        case = await self.get_case(guild, user, index)
        case["reason"] = new_reason
        case["time"] = case["time"].strftime("%a %d %B %Y %H:%M")
        async with self.data.custom("MODLOGS", guild.id, user.id).x() as logs:
            logs[index - 1] = case
        return True

    async def get_modlog_channel(
        self, guild: discord.Guild, level: Optional[Union[int, str]] = None
    ) -> discord.TextChannel:
        """
        Get the BetterMod's modlog channel on the current guild.

        When you call this, the channel is get with the following order:

        #.  Get the modlog channel associated to the type, if provided
        #.  Get the defult modlog channel set with BetterMod
        #.  Get the Red's modlog channel associated to the server

        Parameters
        ----------
        guild: discord.Guild
            The guild you want to get the modlog from.
        level: Optional[Union[int, str]]
            Can be an :py:class:`int` between 1 and 5, a :py:class:`str` (``"all"``
            or ``"report"``) or :py:obj:`None`.

            *   If the argument is omitted (or :py:obj:`None` is provided), the default modlog
                channel will be returned.

            *   If an :py:class:`int` is given, the modlog channel associated to this warning
                level will be returned. If a specific channel was not set for this level, the
                default modlog channel will be returned instead.

            *   If ``"report"`` is given, the channel associated to the reports will be returned.
                If a specific channel was not set for reports, the default modlog channel will
                be returned instead.

            *   If ``"all"`` is returned, a :py:class:`dict` will be returned. It should be built
                like this:

                .. code-block:: python3

                    {
                        "main"      : 012345678987654321,
                        "report"    : 579084368900053345,
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
        NotFound
            There is no modlog channel set with BetterMod or Red, ask the user to set one.
        """
        self._log_call(inspect.stack())

        # raise errors if the arguments are wrong
        if level:
            msg = (
                "The level must be an int between 1 and 5 ; or a string that "
                'should be "all" or "report"'
            )
            if not isinstance(level, int) and all([x != level for x in ["all", "report"]]):
                raise errors.InvalidLevel(msg)
            elif isinstance(level, int) and not 1 <= level <= 5:
                raise errors.InvalidLevel(msg)

        default_channel = await self.data.guild(guild).channels.main()
        if level:
            channel = await self.data.guild(guild).channels.get_raw(str(level))
        else:
            return default_channel

        if not default_channel and not channel:
            # bettermod default channel doesn't exist, let's try to get Red's one
            try:
                return await get_red_modlog_channel(guild)
            except RuntimeError:
                raise errors.NotFound("No modlog found from BetterMod or Red")

        return self.bot.get_channel(channel if channel else default_channel)

    async def get_embeds(
        self,
        guild: discord.Guild,
        member: Union[discord.Member, discord.User],
        author: Union[discord.Member, str],
        level: int,
        reason: Optional[str] = None,
        time: Optional[timedelta] = None,
        action_fail: Optional[str] = None,
    ) -> tuple:
        """
        Return two embeds, one for the modlog and one for the member.

        Parameters
        ----------
        guild: discord.Guild
            The Discord guild where the warning takes place.
        member: Union[discord.Member, discord.User]
            The warned member. Should only be :class:`discord.User` in case of a hack ban.
        author: Union[discord.Member, str]
            The moderator that warned the user. If it's not a Discord user, you can specify a
            :py:class:`str` instead (e.g. "Automod").
        level: int
            The level of the warning which should be between 1 and 5.
        reason: Optional[str]
            The reason of the warning.
        time: timedelta
            The time before the action ends. Only for mute and ban.
        action_fail: Optional[str]
            The message shown to the moderators if the action failed.

        Returns
        -------
        tuple
            A :py:class:`tuple` with the modlog embed at index 0, and the user embed at index 1.

        .. warning:: Unlike for the warning, the arguments are not checked and won't raise errors
            if they are wrong. It is recommanded to call :func:`~bettermod.api.API.warn` and let
            it generate the embeds instead.
        """
        action = (
            _("mute")
            if level == 2
            else _("kick")
            if level == 3
            else _("softban")
            if level == 4
            else _("ban")
            if level == 5
            else _("warn")
        )
        success = None
        if action_fail:
            success = (
                _("The bot couldn't {action} the user for the following reason: ").format(
                    action=action
                )
                + action_fail
            )
        if not reason:
            reason = _("No reason was provided.\nEdit this with `[p]warnings @{name}`").format(
                name=str(member)
            )
        logs = await self.data.member(member).logs()
        total_warns = len(logs) + 1
        total_type_warns = (
            len([x for x in logs if x["level"] == level]) + 1
        )  # number of warns of the received type
        current_status = lambda x: _(
            "{who} now {verb} {total} warning{plural} ({total_type} {action}{plural_type})"
        ).format(
            who=_("The member") if x else _("You"),
            verb=_("has") if x else _("have"),
            total=total_warns,
            total_type=total_type_warns,
            action=action,
            plural="s" if total_warns > 1 else "",
            plural_type="s" if total_type_warns > 1 else "",
        )

        # embed for the modlog
        log_embed = discord.Embed()
        log_embed.set_author(name=f"{member.name} | {member.id}", icon_url=member.avatar_url)
        log_embed.title = _("Level {level} warning ({action})").format(level=level, action=action)
        log_embed.description = _("A member got a level {level} warning.\n\n{successful}").format(
            level=level, successful=success if success else ""
        )
        log_embed.add_field(name=_("Member"), value=member.mention, inline=True)
        log_embed.add_field(name=_("Moderator"), value=author.mention, inline=True)
        log_embed.add_field(name=_("Reason"), value=reason, inline=False)
        log_embed.add_field(name=_("Status"), value=current_status(True), inline=False)
        log_embed.set_footer(text=datetime.today().strftime("%a %d %B %Y %H:%M"))
        log_embed.set_thumbnail(url=await self.data.guild(guild).thumbnails.get_raw(level))
        log_embed.color = await self.data.guild(guild).colors.get_raw(level)

        # embed for the member in DM
        user_embed = deepcopy(log_embed)
        user_embed.set_author(name="")
        user_embed.description = _("The moderation team set you a level {level} warning.").format(
            level=level
        )
        user_embed.set_field_at(3, name=_("Status"), value=current_status(False), inline=False)
        user_embed.remove_field(0)  # removes member field
        if not await self.data.guild(guild).show_mod():
            user_embed.remove_field(0)  # called twice, removing moderator field

        return (log_embed, user_embed)

    async def warn(
        self,
        guild: discord.Guild,
        member: Union[discord.Member, discord.User],
        author: Union[discord.Member, str],
        level: int,
        reason: Optional[str] = None,
        time: Optional[timedelta] = None,
        log_modlog: bool = True,
        log_dm: bool = True,
        take_action: bool = True,
    ) -> bool:
        """
        Set a warning on a member of a Discord guild and log it with the BetterMod system.

        Parameters
        ----------
        guild: discord.Guild
            The guild of the member to warn
        member: Union[discord.Member, discord.User]
            The member that will be warned. It can be a :class:`discord.User` only if you need to
            ban someone not in the guild.
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
        log_modlog: bool
            Specify if an embed should be posted to the modlog channel. Default to :py:obj:`True`.
        log_dm: bool
            Specify if an embed should be sent to the warned user. Default to :py:obj:`True`.
        take_action: bool
            Specify if the bot should take action on the member (mute, kick, softban, ban). If set
            to :py:obj:`False`, the bot will only send a log embed to the member and in the modlog.
            Default to :py:obj:`True`.

        Returns
        -------
        bool
            :py:obj:`True` if the action was successful.
        """
        self._log_call(inspect.stack())

        if not 1 <= level <= 5:
            raise errors.InvalidLevel("The level must be between 1 and 5.")
        if isinstance(level, discord.User) and level != 5:
            raise errors.BadArgument(
                "You need to provide a valid discord.Member object for this action."
            )
        if not log_modlog and not log_dm and not take_action:
            raise errors.BadArgument(
                "I have nothing to do! Please set one of these arguments to True to continue: "
                "log_modlog, log_dm, take_action"
            )

        await self._create_case(member)

        modlog_msg, user_msg = await self.get_embeds(guild, member, author, level, reason, time)
