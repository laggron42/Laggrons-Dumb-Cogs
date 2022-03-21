from __future__ import annotations

import discord
import re

from typing import TYPE_CHECKING, Union

from redbot.core.commands import BadArgument, MemberConverter
from redbot.core.i18n import Translator

if TYPE_CHECKING:
    from redbot.core.bot import Red
    from redbot.core import commands

_ = Translator("WarnSystem", __file__)
id_pattern = re.compile(r"([0-9]{15,21})$")


class SafeMember:
    def __init__(self, member: discord.Member) -> None:
        self.name = str(member.name)
        self.display_name = str(member.display_name)
        self.nick = str(member.nick)
        self.id = str(member.id)
        self.mention = str(member.mention)
        self.discriminator = str(member.discriminator)
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
    colour = discord.Embed.Empty


class FakeAsset:
    url = ""


class UnavailableMember(discord.abc.User, discord.abc.Messageable):
    """
    A class that reproduces the behaviour of a discord.Member instance, except
    the member is not in the guild. This is used to prevent calling bot.fetch_info
    which has a very high cooldown.
    """

    def __init__(self, bot: "Red", state, user_id: int):
        self.bot = bot
        self._state = state
        self.id = user_id
        self.top_role = FakeRole()
        self.avatar = FakeAsset()

    @staticmethod
    def _check_id(member_id):
        if not id_pattern.match(member_id):
            raise ValueError(f"You provided an invalid ID: {member_id}")
        return int(member_id)

    @classmethod
    async def convert(cls, ctx: "commands.Context", text: str):
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

    @classmethod
    def get_member(
        cls, bot: "Red", guild: discord.Guild, user_id: int
    ) -> Union[discord.Member, UnavailableMember]:
        if member := guild.get_member(user_id):
            return member
        return cls(bot, guild._state, user_id)

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
