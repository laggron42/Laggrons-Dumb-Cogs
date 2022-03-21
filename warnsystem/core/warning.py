import discord
import logging
import re

from typing import TYPE_CHECKING, List, Optional, Tuple, Union
from datetime import datetime, timedelta, timezone
from copy import deepcopy

from redbot.core.i18n import Translator

from warnsystem.core.objects import UnavailableMember, SafeMember
from warnsystem.core.errors import BadArgument, MissingMuteRole

if TYPE_CHECKING:
    from redbot.core.bot import Red
    from redbot.core import Config
    from warnsystem.core.cache import MemoryCache

_ = Translator("WarnSystem", __file__)
log = logging.getLogger("red.laggron.warnsystem")
LINK_SEARCH = re.compile(r"(https?://)\S+\.(jpg|jpeg|png|gif|webm)")


class Warning:
    __slots__ = (
        "data",
        "cache",
        "guild",
        "member",
        "author",
        "level",
        "time",
        "reason",
        "duration",
        "roles",
        "modlog_message",
        "index",
    )

    def __init__(
        self,
        data: "Config",
        cache: "MemoryCache",
        guild: discord.Guild,
        member: Union[discord.Member, UnavailableMember],
        author: Union[discord.Member, UnavailableMember],
        level: int,
        time: Optional[datetime] = None,
        reason: Optional[str] = None,
        duration: Optional[timedelta] = None,
        roles: Optional[List[discord.Role]] = None,
        modlog_message: Optional[Union[discord.Message, discord.PartialMessage]] = None,
    ):
        self.data = data
        self.cache = cache
        self.guild = guild
        self.member = member
        self.author = author
        self.level = level
        self.time = time or datetime.now(timezone.utc)
        self.reason = reason
        self.duration = duration
        self.roles = roles
        self.modlog_message = modlog_message
        self.index: Optional[int] = None

    # ----- saving stuff -----

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "author": self.author
            if not isinstance(self.author, (discord.User, discord.Member))
            else self.author.id,
            "reason": self.reason,
            "time": int(self.time.timestamp()),  # seconds since epoch
            "duration": None if not self.duration else self.duration.total_seconds(),
            "roles": [] if not self.roles else [x.id for x in self.roles],
            "modlog_message": {
                "channel_id": self.modlog_message.channel.id,
                "message_id": self.modlog_message.id,
            },
        }

    @classmethod
    def from_dict(
        cls,
        bot: "Red",
        config: "Config",
        cache: "MemoryCache",
        guild: discord.Guild,
        member: Union[discord.Member, UnavailableMember],
        data: dict,
        index: int,
    ):
        time = datetime.fromtimestamp(data["time"])
        duration = timedelta(seconds=data["duration"]) if data["duration"] else None
        roles = [guild.get_role(x) for x in data["roles"]]
        modlog_channel = guild.get_channel(data["modlog_message"]["channel_id"])
        if modlog_channel:
            modlog_message = modlog_channel.get_partial_message(
                data["modlog_message"]["message_id"]
            )
        else:
            modlog_message = None
        warn = cls(
            config,
            cache,
            guild=guild,
            member=member,
            author=UnavailableMember.get_member(bot, guild, data["author"]),
            level=data["level"],
            time=time,
            reason=data["reason"],
            duration=duration,
            roles=roles,
            modlog_message=modlog_message,
        )
        warn.index = index
        return warn

    async def save(self):
        async with self.data.custom("MODLOGS", self.guild.id, self.member.id).x() as warns:
            if self.index:
                warns[self.index] = self.to_dict()
            else:
                warns.append(self.to_dict())
                self.index = len(warns)

    async def _erase(self):
        if not self.index:
            return
        async with self.data.custom("MODLOGS", self.guild.id, self.member.id).x() as warns:
            del warns[self.index]

    # ----- various utils -----

    @staticmethod
    def _format_datetime(time: datetime):
        return time.strftime("%a %d %B %Y %H:%M:%S")

    @staticmethod
    def _format_timedelta(time: timedelta):
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

    async def _fetch_message(self) -> bool:
        if isinstance(self.modlog_message, discord.Message):
            return True
        try:
            self.modlog_message = await self.modlog_message.fetch()
        except discord.NotFound:
            log.warn(
                f"[Guild {self.guild.id}] Modlog message {self.modlog_message.id} "
                f"in channel {self.modlog_message.channel.id} not found."
            )
            return False
        except discord.Forbidden:
            log.warn(
                f"[Guild {self.guild.id}] No permissions "
                f"to fetch messages in channel {self.modlog_message.channel.id}."
            )
            return False
        except discord.HTTPException:
            log.error(
                f"[Guild {self.guild.id}] Failed to fetch modlog message. API exception raised.",
                exc_info=True,
            )
            return False
        else:
            return True

    async def format_reason(self, reason: str = None) -> str:
        """
        Reformat a reason with the substitutions set on the guild.

        Parameters
        ----------
        reason: str
            The string you want to reformat.

        Returns
        -------
        str
            The reformatted string
        """
        if not reason:
            return
        substitutions = await self.data.guild(self.guild).substitutions()
        for key, substitute in substitutions.items():
            reason = reason.replace(f"[{key}]", substitute)
        return reason

    async def get_embeds(self, message_sent: bool = True) -> Tuple[discord.Embed, discord.Embed]:
        """
        Return two embeds, one for the modlog and one for the member.

        .. warning:: Unlike for the warning, the arguments are not checked and won't raise errors
            if they are wrong. It is recommanded to call :func:`~warnsystem.api.API.warn` and let
            it generate the embeds instead.

        Parameters
        ----------
        message_sent: bool
            Set to :py:obj:`False` if the embed couldn't be sent to the warned user.

        Returns
        -------
        Tuple[discord.Embed, discord.Embed]
            A :py:class:`tuple` with the modlog embed at index 0, and the user embed at index 1.
        """
        action = {
            1: (_("warn"), _("warns")),
            2: (_("mute"), _("mutes")),
            3: (_("kick"), _("kicks")),
            4: (_("softban"), _("softbans")),
            5: (_("ban"), _("bans")),
        }.get(self.level, _("unknown"))
        mod_message = ""
        reason = self.reason
        if not reason:
            reason = _("No reason was provided.")
            mod_message = _("\nEdit this with `[p]warnings {id}`").format(id=self.member.id)
        logs = await self.data.custom("MODLOGS", self.guild.id, self.member.id).x()

        # prepare the status field
        total_warns = len(logs) + 1
        total_type_warns = (
            len([x for x in logs if x["level"] == self.level]) + 1
        )  # number of warns of the received type

        formatting_args = {
            "total": total_warns,
            "warnings": _("warnings") if total_warns > 1 else _("warning"),
            "total_type": total_type_warns,
            "action": action[1] if total_type_warns > 1 else action[0],
        }
        second_person_status = _("You now have {total} {warnings} ({total_type} {action})").format(
            **formatting_args
        )
        third_person_status = _(
            "The member now has {total} {warnings} ({total_type} {action})"
        ).format(**formatting_args)

        # we set any value that can be used multiple times
        invite = None
        log_description = await self.data.guild(self.guild).embed_description_modlog.get_raw(
            self.level
        )
        if "{invite}" in log_description:
            try:
                invite = await self.guild.create_invite(max_uses=1)
            except Exception:
                invite = _("*[couldn't create an invite]*")
        user_description = await self.data.guild(self.guild).embed_description_user.get_raw(
            self.level
        )
        if "{invite}" in user_description and not invite:
            try:
                invite = await self.guild.create_invite(max_uses=1)
            except Exception:
                invite = _("*[couldn't create an invite]*")
        duration = None
        if self.duration:
            duration = self._format_timedelta(self.duration)

        def format_description(text: str):
            try:
                return text.format(
                    invite=invite,
                    member=SafeMember(self.member),
                    mod=SafeMember(self.author),
                    duration=duration,
                    time=self.time,
                )
            except Exception:
                log.error(
                    f"[Guild {self.guild.id}] Failed to format description in embed", exc_info=True
                )
                return "Failed to format field."

        link = LINK_SEARCH.search(reason)

        # embed for the modlog
        log_embed = discord.Embed()
        log_embed.set_author(
            name=f"{self.member.name} | {self.member.id}", icon_url=self.member.avatar.url
        )
        log_embed.title = _("Level {level} warning ({action})").format(
            level=self.level, action=action[0]
        )
        log_embed.description = format_description(log_description)
        log_embed.add_field(name=_("Member"), value=self.member.mention, inline=True)
        log_embed.add_field(name=_("Moderator"), value=self.author.mention, inline=True)
        if self.duration:
            log_embed.add_field(name=_("Duration"), value=duration, inline=True)
        log_embed.add_field(name=_("Reason"), value=reason + mod_message, inline=False)
        log_embed.add_field(name=_("Status"), value=third_person_status, inline=False)
        log_embed.timestamp = self.time
        log_embed.set_thumbnail(
            url=await self.data.guild(self.guild).thumbnails.get_raw(self.level)
        )
        log_embed.colour = await self.data.guild(self.guild).colors.get_raw(self.level)
        log_embed.url = await self.data.guild(self.guild).url()
        log_embed.set_image(url=link.group() if link else "")
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
            user_embed.set_field_at(3 if self.duration else 2, name=_("Reason"), value=reason)
        user_embed.remove_field(
            4 if self.duration else 3
        )  # removes status field (gonna be added back)
        user_embed.remove_field(0)  # removes member field
        user_embed.add_field(name=_("Status"), value=second_person_status, inline=False)
        if not await self.data.guild(self.guild).show_mod():
            user_embed.remove_field(0)  # called twice, removing moderator field

        return (log_embed, user_embed)

    # ----- public interface for edition -----

    async def edit_reason(self, new_reason: str):
        """
        Edit the reason of a case.

        Parameters
        ----------
        new_reason: str
            The new reason to set.

        Raises
        ------
        ~warnsystem.errors.BadArgument
            The reason is above 1024 characters. Due to Discord embed rules, you have to make it
            shorter.
        """

        async def edit_message():
            if not await self._fetch_message():
                return
            try:
                embed: discord.Embed = self.modlog_message.embeds[0]
                embed.set_field_at(
                    len(embed.fields) - 2, name=_("Reason"), value=new_reason, inline=False
                )
            except IndexError:
                log.error(
                    f"[Guild {self.guild.id}] Failed to edit modlog message. Embed is malformed.",
                    exc_info=True,
                )
                return
            try:
                await self.modlog_message.edit(embed=embed)
            except discord.errors.HTTPException:
                log.error(
                    f"[Guild {self.guild.id}] Failed to edit modlog message. "
                    "Unknown error when attempting message edition.",
                    exc_info=True,
                )

        new_reason = await self.format_reason(new_reason)
        if len(new_reason) > 1024:
            raise BadArgument("The reason must not be above 1024 characters.")
        self.reason = new_reason
        try:
            await edit_message()
        except Exception:
            log.error(
                f"[Guild {self.guild.id}] Unhandled error when editing modlog message",
                exc_info=True,
            )
        await self.save()
        log.debug(
            f"[Guild {self.guild.id}] Edited case #{self.index} from member "
            f"{self.member} (ID: {self.member.id}). New reason: {new_reason}"
        )

    async def delete(self):
        """
        Delete this case.
        """

        async def delete_message():
            if not await self._fetch_message():
                return
            try:
                await self.modlog_message.delete()
            except discord.HTTPException:
                log.error(
                    f"[Guild {self.guild.id}] Failed to delete modlog message. "
                    "Unknown error when attempting message deletion.",
                    exc_info=True,
                )

        if self.level == 2:
            try:
                await self._unmute(_("Warning deleted."))
            except Exception:
                log.error(
                    f"[Guild {self.guild.id}] Failed to unmute member when deleting warn.",
                    exc_info=True,
                )
        try:
            await delete_message()
        except Exception:
            log.error(
                f"[Guild {self.guild.id}] Unhandled error when editing modlog message",
                exc_info=True,
            )
        await self._erase()
        log.debug(
            f"[Guild {self.guild.id}] Removed case #{self.index} from "
            f"member {self.member} (ID: {self.member.id})."
        )

    # ----- taking actions -----

    async def mute(self, reason: str = None):
        mute_role = self.guild.get_role(await self.cache.get_mute_role(self.guild))
        remove_roles = await self.data.guild(self.guild).remove_roles()
        if not mute_role:
            raise MissingMuteRole("You need to create the mute role before doing this.")
        if remove_roles:
            self.roles = self.member.roles.copy()
            self.roles.remove(self.guild.default_role)
            self.roles = [
                x
                for x in self.roles
                if x.position < self.guild.me.top_role.position and not x.managed
            ]
            try:
                await self.member.remove_roles(*self.roles, reason=reason)
            except discord.HTTPException:
                log.warn(
                    f"[Guild {self.guild.id}] Failed to remove roles from {self.member} "
                    f"(ID: {self.member.id}) while muting.",
                    exc_info=True,
                )
        await self.member.add_roles(mute_role, reason=reason)

    async def unmute(self, reason: str = None):
        """Unmute an user on the guild."""
        mute_role = self.guild.get_role(await self.cache.get_mute_role(self.guild))
        if not mute_role:
            raise MissingMuteRole(
                f"Lost the mute role on guild {self.guild.name} (ID: {self.guild.id}"
            )
        await self.member.remove_roles(mute_role, reason=reason)
        if self.roles:
            await self.member.add_roles(*self.roles, reason=reason)
