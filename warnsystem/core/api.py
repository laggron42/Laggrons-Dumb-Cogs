import asyncio
import discord
import logging
import re

from typing import List, Union, Optional, Iterable, Callable, Awaitable
from datetime import datetime, timedelta, timezone

from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.i18n import Translator

try:
    from redbot.core.modlog import get_modlog_channel as get_red_modlog_channel
except RuntimeError:
    pass  # running sphinx-build raises an error when importing this module

from warnsystem.core.warning import Warning
from warnsystem.core.objects import UnavailableMember
from warnsystem.core.cache import MemoryCache
from warnsystem.core import errors

log = logging.getLogger("red.laggron.warnsystem")
_ = Translator("WarnSystem", __file__)
id_pattern = re.compile(r"([0-9]{15,21})$")


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

    async def _start_timer(self, warning: Warning) -> bool:
        """Start the timer for a temporary mute/ban."""
        if not warning.duration:
            raise errors.BadArgument("No duration for this warning!")
        await self.cache.add_temp_action(warning)
        return True

    async def get_case(
        self, guild: discord.Guild, member: Union[discord.Member, UnavailableMember], index: int
    ) -> Warning:
        """
        Get a specific case for a member.

        Parameters
        ----------
        guild: discord.Guild
            The guild of the member.
        member: Union[discord.Member, UnavailableMember]
            The user you want to get the case from. Can be an :class:`UnavailableMember`
            if the member is not in the server.
        index: int
            The case index you want to get. Must be positive.

        Returns
        -------
        ~warnsystem.core.warning.Warning
            The warning found

        Raises
        ------
        ~warnsystem.errors.NotFound
            The case requested doesn't exist.
        """
        try:
            case = (await self.data.custom("MODLOGS", guild.id, member.id).x())[index - 1]
        except IndexError:
            raise errors.NotFound("The case requested doesn't exist.")
        else:
            return Warning.from_dict(self.bot, self.data, self.cache, guild, member, case, index)

    async def get_all_cases(
        self,
        guild: discord.Guild,
        member: Optional[Union[discord.Member, UnavailableMember]] = None,
    ) -> List[Warning]:
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
        List[Warning]
            A list of all cases of a user/guild. The cases are sorted from the oldest to the
            newest.
        """
        if member:
            return [
                Warning.from_dict(self.bot, self.data, self.cache, guild, member, x, i)
                for i, x in enumerate(await self.data.custom("MODLOGS", guild.id, member.id).x())
            ]
        logs = await self.data.custom("MODLOGS", guild.id).all()
        all_cases = []
        for member, content in logs.items():
            if member == "x":
                continue
            for i, log in enumerate(content["x"]):
                all_cases.append(
                    Warning.from_dict(self.bot, self.data, self.cache, guild, member, log, i)
                )
        return sorted(all_cases, key=lambda x: x.time)  # sorted from oldest to newest

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

                For technical reasons, the default channel is actually named ``"main"`` in the
                dict.

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
        _errors = []
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
                _errors.append(
                    _(
                        "Cannot edit permissions of the channel {channel} because of a "
                        "permission error (probably enforced permission for `Manage channel`)."
                    ).format(channel=channel.mention)
                )
            except discord.errors.HTTPException as e:
                _errors.append(
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
                _errors.append(
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
        return _errors

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
            The bot is trying to take actions on someone but his top role is higher
            than the bot's top role in the guild's hierarchy.
        ~warnsystem.errors.NotAllowedByHierarchy
            The moderator trying to warn someone is lower than him in the role hierarchy,
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
            warning = Warning(
                data=self.data,
                cache=self.cache,
                guild=guild,
                member=member,
                author=author,
                level=level,
                time=date,
                reason=reason,
                duration=time,
            )
            # send the message to the user
            if log_modlog or log_dm:
                modlog_e, user_e = await warning.get_embeds()
            if log_dm:
                try:
                    await member.send(embed=user_e)
                except (discord.errors.Forbidden, errors.UserNotFound):
                    modlog_e = (await warning.get_embeds(message_sent=False))[0]
                except discord.errors.NotFound:
                    raise
                except discord.errors.HTTPException as e:
                    modlog_e = (await warning.get_embeds(message_sent=False))[0]
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
                        await warning.mute(audit_reason)
                    elif level == 3:
                        await guild.kick(member, reason=audit_reason)
                    elif level == 4:
                        await guild.ban(
                            member,
                            reason=audit_reason,
                            delete_message_days=ban_days
                            or await self.data.guild(guild).bandays.softban(),
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
                            delete_message_days=ban_days
                            or await self.data.guild(guild).bandays.ban(),
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
                try:
                    warning.modlog_message = await mod_channel.send(embed=modlog_e)
                except Exception:
                    log.error(f"[Guild {guild.id}] Failed to send modlog message.", exc_info=True)
            await warning.save()

            # start timer if there is a temporary warning
            if time and (level == 2 or level == 5):
                await self._start_timer(warning)
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

            for member, warning in data.items():
                if (warning.time + warning.duration) > now:
                    continue

                # end of warn
                action_str = _("mute") if warning.level == 2 else _("ban")
                duration = warning._format_timedelta(warning.duration)
                reason = _(
                    "End of timed {action} of {member} requested by {author} that lasted "
                    "for {time}. Reason of the {action}: {reason}"
                ).format(
                    action=action_str,
                    member=member,
                    author=warning.author,
                    time=duration,
                    reason=warning.reason,
                )
                try:
                    if warning.level == 2:
                        await warning.unmute(reason=reason)
                    if warning.level == 5:
                        await guild.unban(member, reason=reason)
                        if await self.data.guild(guild).reinvite():
                            await reinvite(
                                guild,
                                member,
                                warning.reason,
                                duration,
                            )
                except discord.errors.Forbidden:
                    log.warn(
                        f"[Guild {guild.id}] I lost required permissions for "
                        f"ending the timed {action_str}. Member {member} (ID: {member.id}) "
                        "will stay as it is now."
                    )
                except discord.errors.HTTPException as e:
                    log.warn(
                        f"[Guild {guild.id}] Couldn't end the timed {action_str} of {member} "
                        f"(ID: {member.id}). He will stay as it is now.",
                        exc_info=e,
                    )
                else:
                    log.debug(
                        f"[Guild {guild.id}] Ended timed {action_str} of {member} (ID: "
                        f"{member.id}) taken on {warning._format_datetime(warning.time)} "
                        f"requested by {warning.author} (ID: {warning.author.id}) that lasted for "
                        f"{duration} for the reason {warning.reason}"
                        f"\nCurrent time: {now}\nExpected end time of warn: "
                        f"{warning._format_datetime(warning.time + warning.duration)}"
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
