import asyncio
import discord
import logging
import os
import sys

from copy import deepcopy
from typing import Union, Optional
from datetime import datetime, timedelta

try:
    from redbot.core.modlog import get_modlog_channel as get_red_modlog_channel
except RuntimeError:
    pass  # running sphinx-build raises an error when importing this module

from .warnsystem import _  # translator
from . import errors

log = logging.getLogger("laggron.warnsystem")
if logging.getLogger("red").isEnabledFor(logging.DEBUG):
    # debug mode enabled
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.WARNING)


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

    def __init__(self, bot, config):
        self.bot = bot
        self.data = config

        # importing this here prevents a RuntimeError when building the documentation
        # TODO find another solution

    def _get_datetime(self, time: str) -> datetime:
        return datetime.strptime(time, "%a %d %B %Y %H:%M")

    def _format_timedelta(self, time: timedelta):
        """Format a timedelta object into a string"""
        # blame python for not creating a strftime attribute
        plural = lambda name, amount: name[0] if amount > 1 else name[1]
        strings = []

        seconds = time.total_seconds()
        years, seconds = divmod(seconds, 31622400)
        months, seconds = divmod(seconds, 2635200)
        weeks, seconds = divmod(seconds, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        units = [years, months, weeks, hours, minutes, seconds]

        for i, value in enumerate(units):
            if value < 1:
                continue
            # tuples inspired from mikeshardmind
            # https://github.com/mikeshardmind/SinbadCogs/blob/v3/scheduler/time_utils.py#L29
            units_name = {
                0: (_("year"), _("years")),
                1: (_("month"), _("months")),
                2: (_("week"), _("weeks")),
                3: (_("hour"), _("hours")),
                4: (_("minute"), _("minute")),
                5: (_("second"), _("second")),
            }
            unit_name = plural(units_name.get(i), len(value))
            strings.append(f"{round(value)} {unit_name}")
        string = ", ".join(strings[:-1])
        if len(strings) > 1:
            string += _(" and ") + strings[-1]
        else:
            string = strings[0]
        return string

    async def _start_timer(self, guild: discord.Guild, case: dict) -> bool:
        """Start the timer for a temporary mute/ban."""
        if not case["until"]:
            raise errors.BadArgument("No duration for this warning!")
        async with self.data.guild(guild).temporary_warns() as warns:
            warns.append(case)
        return True

    async def _mute(self, member: discord.Member, reason: Optional[str] = None):
        """Mute an user on the guild."""
        guild = member.guild
        role = guild.get_role(await self.data.guild(guild).mute_role())
        if not role:
            raise errors.MissingMuteRole("You need to create the mute role before doing this.")
        await member.add_roles(role, reason=reason)

    async def _unmute(self, member: discord.Member, reason: str):
        """Unmute an user on the guild."""
        guild = member.guild
        role = guild.get_role(await self.data.guild(guild).mute_role())
        if not role:
            raise errors.MissingMuteRole(
                f"Lost the mute role on guild {guild.name} (ID: {guild.id}"
            )
        await member.remove_roles(role, reason=reason)

    async def _create_case(
        self,
        guild: discord.Guild,
        user: discord.User,
        author: Union[discord.Member, str],
        level: int,
        time: datetime,
        reason: Optional[str] = None,
        duration: Optional[timedelta] = None,
    ) -> dict:
        """Create a new case for a member. Don't call this, call warn instead."""
        data = {
            "level": level,
            "author": author
            if not isinstance(author, (discord.User, discord.Member))
            else author.id,
            "reason": reason,
            "time": time.strftime("%a %d %B %Y %H:%M"),
            "duration": None if not duration else self._format_timedelta(duration),
            "until": None
            if not duration
            else (datetime.today() + duration).strftime("%a %d %B %Y %H:%M"),
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
        ~warnsystem.errors.BadArgument
            The reason is above 1024 characters. Due to Discord embed rules, you have to make it
            shorter.
        ~warnsystem.errors.NotFound
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
        member: Union[discord.Member, discord.User],
        author: Union[discord.Member, str],
        level: int,
        reason: Optional[str] = None,
        time: Optional[timedelta] = None,
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
        member: Union[discord.Member, discord.User]
            The warned member. Should only be :class:`discord.User` in case of a hack ban.
        author: Union[discord.Member, str]
            The moderator that warned the user. If it's not a Discord user, you can specify a
            :py:class:`str` instead (e.g. "Automod").
        level: int
            The level of the warning which should be between 1 and 5.
        reason: Optional[str]
            The reason of the warning.
        time: Optional[timedelta]
            The time before the action ends. Only for mute and ban.
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
        }.get(level, default=(_("unknown")))
        mod_message = ""
        if not reason:
            reason = _("No reason was provided.")
            mod_message = _("\nEdit this with `[p]warnings @{name}`").format(name=str(member))
        logs = await self.data.custom("MODLOGS", guild.id, member.id).x()

        # prepare the status field
        total_warns = len(logs) + 1
        total_type_warns = (
            len([x for x in logs if x["level"] == level]) + 1
        )  # number of warns of the received type

        # a lambda that returns a string; if True is given, a third person sentence is returned
        # (modlog), if False is given, a first person sentence is returned (DM user)
        current_status = lambda x: _(
            "{who} now {verb} {total} {warning} ({total_type} {action}{plural_type})"
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
        today = datetime.today().strftime("%a %d %B %Y %H:%M")
        if time:
            duration = self._format_timedelta(time)
        else:
            duration = _("*[No time given]*")
        format_description = lambda x: x.format(
            invite=invite, member=member, mod=author, duration=duration, time=today
        )

        # embed for the modlog
        log_embed = discord.Embed()
        log_embed.set_author(name=f"{member.name} | {member.id}", icon_url=member.avatar_url)
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
        log_embed.set_footer(text=today)
        log_embed.set_thumbnail(url=await self.data.guild(guild).thumbnails.get_raw(level))
        log_embed.color = await self.data.guild(guild).colors.get_raw(level)
        log_embed.url = await self.data.guild(guild).url()
        if not message_sent:
            log_embed.description += _(
                "\n\n***The message couldn't be delivered to the member. We may don't "
                "have a server in common or he blocked me/messages from this guild.***"
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

        Parameters
        ----------
        guild: discord.Guild
            The guild you want to set up the mute in.

        Returns
        -------
        bool
            *   :py:obj:`True` if the role was successfully created.
            *   :py:obj:`False` if the role already exists.
            *   :py:class:`list` of :py:class:`str` if some channel updates failed, containing
                the message explaining the error for each message

        Raises
        ------
        ~warnsystem.errors.MissingPermissions
            The bot lacks the :attr:`discord.PermissionOverwrite.create_roles` permission.
        discord.errors.HTTPException
            Creating the role failed.
        """
        role = await self.data.guild(guild).mute_role()
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
        errors = []
        for channel in [x for x in guild.channels if isinstance(x, discord.TextChannel)]:
            try:
                await channel.set_permissions(
                    role,
                    send_messages=False,
                    add_reactions=False,
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
                    f"Couldn't edit permissions of {channel} (ID: {channel.id}) in guild "
                    f"{guild.name} (ID: {guild.id}) for setting up the mute role because "
                    "of an HTTPException.",
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
                    f"Couldn't edit permissions of {channel} (ID: {channel.id}) in guild "
                    f"{guild.name} (ID: {guild.id}) for setting up the mute role because "
                    "of an unknwon error.",
                    exc_info=e,
                )
        await self.data.guild(guild).mute_role.set(role.id)
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
        member: Union[discord.Member, int],
        author: Union[discord.Member, str],
        level: int,
        reason: Optional[str] = None,
        time: Optional[timedelta] = None,
        log_modlog: bool = True,
        log_dm: bool = True,
        take_action: bool = True,
    ) -> bool:
        """
        Set a warning on a member of a Discord guild and log it with the WarnSystem system.

        .. tip:: The message that comes with the following exceptions are already
            translated and ready to be sent to Discord:

            *   :class:`~warnsystem.errors.NotFound`
            *   :class:`~warnsystem.errors.LostPermissions`
            *   :class:`~warnsystem.errors.MemberTooHigh`
            *   :class:`~warnsystem.errors.MissingPermissions`

        Parameters
        ----------
        guild: discord.Guild
            The guild of the member to warn
        member: Union[discord.Member, int]
            The member that will be warned. It can be an :py:class:`int` only if you need to
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

        Raises
        ------
        ~warnsystem.errors.InvalidLevel
            The level must be an :py:class:`int` between 1 and 5.
        ~warnsystem.errors.BadArgument
            You need to provide a valid :class:`discord.Member` object, except for a
            hackban where a :class:`discord.User` works.
        ~warnsystem.errors.NotFound
            You provided an :py:class:`int` for a hackban, but the bot couldn't find
            it by calling :func:`discord.Client.get_user_info`.
        ~warnsystem.errors.MissingMuteRole
            You're trying to mute someone but the mute role was not setup yet.
            You can fix this by calling :func:`~warnsystem.api.API.maybe_create_mute_role`.
        ~warnsystem.errors.LostPermissions
            The bot lost a permission to do something (it had the perm before). This
            can be lost permissions for sending messages to the modlog channel or
            interacting with the mute role.
        ~warnsystem.errors.MemberTooHigh
            The bot is trying to take actions on someone but his top role is higher
            than the bot's top role in the guild's hierarchy.
        ~warnsystem.errors.NotAllowedByHierarchy
            The moderator trying to warn someone is lower than him in the role hierarchy,
            while the bot still has permissions to act. This is raised only if the
            hierarchy check is enabled.
        ~warnsystem.errors.MissingPermissions
            The bot lacks a permissions to do something. Can be adding role, kicking
            or banning members.
        discord.errors.HTTPException
            Unknown error from Discord API. It's recommanded to catch this
            potential error too.
        """
        if not isinstance(level, int) or not 1 <= level <= 5:
            raise errors.InvalidLevel("The level must be between 1 and 5.")
        if isinstance(member, int):
            if level != 5:
                raise errors.BadArgument(
                    "You need to provide a valid discord.Member object for this action."
                )
            try:
                # we re-create a discord.User object to do not break the functions
                member = await self.bot.get_user_info(member)
            except discord.errors.NotFound:
                raise errors.NotFound(_("The requested member does not exist."))

        # we get the modlog channel now to make sure it exists before doing anything
        mod_channel = await self.get_modlog_channel(guild, level)

        # check that the mute role exists
        mute_role = guild.get_role(await self.data.guild(guild).mute_role())
        if not mute_role and level == 2:
            raise errors.MissingMuteRole("You need to create the mute role before doing this.")

        # we check for all permission problem that can occur before calling the API
        if not all(
            [  # checks if the bot has send_messages and embed_links permissions in modlog channel
                getattr(mod_channel.permissions_for(guild.me), x)
                for x in ["send_messages", "embed_links"]
            ]
        ):
            raise errors.LostPermissions(
                _(
                    "I need the `Send messages` and `Embed links` "
                    "permissions in {channel} to do this."
                ).format(channel=mod_channel.mention)
            )
        if (
            level > 1
            and isinstance(member, discord.Member)
            and guild.me.top_role.position <= member.top_role.position
        ):
            # check if the member is below the bot in the roles's hierarchy
            raise errors.MemberTooHigh(
                _(
                    "Cannot take actions on this member, he is above me in the roles hierarchy. "
                    "Modify the hierarchy so my top role ({bot_role}) is above {member_role}."
                ).format(bot_role=guild.me.top_role.name, member_role=member.top_role.name)
            )
        if (
            isinstance(member, discord.Member)
            and await self.data.guild(guild).respect_hierarchy()
            and (
                member.top_role >= author.top_role
                and not (self.bot.is_owner(author) or author.owner)
            )
        ):
            raise errors.NotAllowedByHierarchy(
                "The moderator is lower than the member in the servers's role hierarchy."
            )
        if level > 2 and isinstance(member, discord.Member) and member == guild.owner:
            raise errors.MissingPermissions(_("I can't take actions on the owner of the guild."))
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
                    )
                )
        if level == 3:
            # kick
            if not guild.me.guild_permissions.kick_members:
                raise errors.MissingPermissions(
                    _("I can't kick members, please give me this permission to continue.")
                )
        if level == 4 or level == 5:
            # softban or ban
            if not guild.me.guild_permissions.ban_members:
                raise errors.MissingPermissions(
                    _("I can't ban members, please give me this permission to continue.")
                )

        # send the message to the user
        if log_modlog or log_dm:
            modlog_e, user_e = await self.get_embeds(guild, member, author, level, reason, time)
        if log_dm:
            try:
                await member.send(embed=user_e)
            except discord.errors.Forbidden:
                modlog_e, user_e = await self.get_embeds(
                    guild, member, author, level, reason, time, message_sent=False
                )
            except discord.errors.HTTPException as e:
                modlog_e, user_e = await self.get_embeds(
                    guild, member, author, level, reason, time, message_sent=False
                )
                log.warn(
                    f"Couldn't send a message to {member} (ID: {member.id}) "
                    "because of an HTTPException.",
                    exc_info=e,
                )

        # take actions
        if take_action:
            action = {1: _("warn"), 2: _("mute"), 3: _("kick"), 4: _("softban"), 5: _("ban")}.get(
                level, default=_("unknown")
            )
            if reason and not reason.endswith("."):
                reason += "."
            audit_reason = (
                _(
                    "WarnSystem {action} requested by {author} (ID: "
                    "{author.id}) against {member} for "
                ).format(author=author, member=member, action=action)
                + (
                    _("the following reason:\n{reason}").format(reason=reason)
                    if reason
                    else _("no reason.")
                )
                + (
                    _("\n\nDuration: {time}").format(time=self._format_timedelta(time))
                    if time
                    else ""
                )
            )
            if level == 2:
                await self._mute(member, audit_reason)
            if level == 3:
                await guild.kick(member, reason=audit_reason)
            if level == 4:
                await guild.ban(
                    member,
                    reason=audit_reason,
                    delete_message_days=await self.data.guild(guild).bandays.softban(),
                )
                await guild.unban(
                    member,
                    reason=_("Unbanning the softbanned member after cleaning up the messages."),
                )
            if level == 5:
                await guild.ban(
                    member,
                    reason=audit_reason,
                    delete_message_days=await self.data.guild(guild).bandays.ban(),
                )

        # actions were taken, time to log
        if log_modlog:
            await mod_channel.send(embed=modlog_e)
        data = await self._create_case(guild, member, author, level, datetime.now(), reason, time)

        # start timer if there is a temporary warning
        if time and (level == 2 or level == 5):
            data["member"] = member.id
            await self._start_timer(guild, data)

        # all good!
        return True

    async def _check_endwarn(self):
        async def reinvite(guild, user, reason, duration):
            channel = None
            # find an ideal channel for the invite
            # we get the one with the most members in the order of the guild
            try:
                channel = sorted(
                    [
                        x
                        for x in guild.text_channels
                        if x.permissions_for(guild.me).create_instant_invite
                    ],
                    key=lambda x: (x.position, len(x.members)),
                )[0]
            except IndexError:
                # can't find a valid channel
                log.info(
                    f"Can't find a channel where I can create an invite in guild {guild} "
                    f"(ID: {guild.id}) when reinviting {member} after its unban."
                )
                return

            try:
                invite = await channel.create_invite(max_uses=1)
            except Exception as e:
                log.warn(
                    f"Couldn't create an invite for guild {guild} (ID: {guild.id} to reinvite "
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
                        f"Couldn't reinvite member {member} (ID: {member.id}) on guild "
                        f"{guild} (ID: {guild.id}) after its temporary ban."
                    )

        guilds = await self.data.all_guilds()
        now = datetime.today()

        for guild, data in guilds.items():
            guild = self.bot.get_guild(guild)
            if not guild:
                continue
            data = data["temporary_warns"]
            to_remove = []
            for action in data:
                taken_on = action["time"]
                until = self._get_datetime(action["until"])
                member = guild.get_member(action["member"])
                author = guild.get_member(action["author"])
                case_reason = action["reason"]
                level = action["level"]
                action_str = _("mute") if level == 2 else _("ban")
                action_past = "muted" if level == 2 else "banned"
                if not member:
                    if level == 2:
                        to_remove.append(action)
                        continue
                    else:
                        member = await self.bot.get_user_info(action["member"])
                reason = _(
                    "End of timed {action} of {member} requested by {author} that lasted "
                    "for {time}. Reason of the {action}: {reason}"
                ).format(
                    action=action_str,
                    member=member,
                    author=author if author else action["author"],
                    time=action["duration"],
                    reason=case_reason,
                )
                if until < now:
                    # end of warn
                    try:
                        if level == 2:
                            await self._unmute(member, reason=reason)
                        if level == 5:
                            await guild.unban(member, reason=reason)
                            if await self.data.guild(guild).reinvite():
                                await reinvite(guild, member, case_reason, action["duration"])
                    except discord.errors.Forbidden:
                        log.warn(
                            f"I lost required permissions for ending the timed {action_str}. "
                            f"Member {member} (ID: {member.id}) from guild {guild} (ID: "
                            f"{guild.id}) will stay as it is now."
                        )
                    except discord.errors.HTTPException as e:
                        log.warn(
                            f"Couldn't end the timed {action_str} of {member} (ID: "
                            f"{member.id}) from guild {guild} (ID: {guild.id}). He will stay "
                            "as it is now.",
                            exc_info=e,
                        )
                    else:
                        log.debug(
                            f"{member} was successfully un{action_past} on guild {guild} (ID: "
                            f'{guild.id}), ending the warn set on {taken_on} for the reason "'
                            f'{case_reason}".'
                        )
                    to_remove.append(action)
            for item in to_remove:
                data.remove(item)
            if to_remove:
                await self.data.guild(guild).temporary_warns.set(data)

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
