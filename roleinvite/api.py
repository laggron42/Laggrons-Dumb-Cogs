import discord
import logging

from .roleinvite import _  # translator
from . import errors

log = logging.getLogger("laggron.warnsystem")
if logging.getLogger("red").isEnabledFor(logging.DEBUG):
    # debug mode enabled
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.WARNING)


class API:
    """
    Interact with RoleInvite from your cog.

    To import the cog and use the functions, type this in your code:

    .. code-block:: python

        roleinvite = bot.get_cog('RoleInvite').api

    .. warning:: If ``roleinvite`` is :py:obj:`None`, the cog is
      not loaded/installed. You won't be able to interact with
      the API at this point.

    .. tip:: You can get the cog version by doing this

        .. code-block:: python

            version = bot.get_cog('RoleInvite').__version__
    """

    def __init__(self, bot, config):
        self.bot = bot
        self.data = config

    def escape_invite_links(self, text: str) -> str:
        """
        Return a Discord invite link that won't show an embed

        Parameters
        ----------
        text: str
            The text which needs to have invite links previews removes

        Returns
        -------
        text: str
            The cleared text
        """
        return text.replace("://discord.gg/", "://discord.\u200Bgg/")

    async def update_invites(self) -> dict:
        """
        Update all invites registered to keep their uses count good.

        This is usually called on cog load since these values
        could have been modified while the bot or the cog was offline.

        Returns
        -------
        dict
            The updated dictionnary.

            .. note::

                The value ``enabled`` may have been switched to :py:obj:`False`
                if the :attr:`~discord.Permissions.manage_guild` permission was
                lost on the guild.
        """
        all_bot_invites = await self.data.all_guilds()
        for guild_id in all_bot_invites:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            bot_invites = all_bot_invites[guild.id]["invites"]

            try:
                invites = await guild.invites()
            except discord.errors.Forbidden:
                # manage_roles permission was removed
                # we disable the autorole to prevent more errors
                await self.data.guild(guild).enabled.set(False)
                self.log.warning(
                    "The manage_server permission was lost. "
                    "RoleInvite is now disabled on this guild.\n"
                    f"Guild: {guild.name} (ID: {guild.id})"
                )
                continue

            to_remove = []
            for invite in bot_invites:
                if all(invite != x for x in ["main", "default"]):
                    invite_object = discord.utils.get(invites, url=invite)
                    if not invite_object:
                        to_remove.append(invite)
                    else:
                        await self.data.guild(guild).invites.set_raw(
                            invite_object.url, "uses", value=invite_object.uses
                        )
            # removing invites to delete
            bot_invites = {x: y for x, y in bot_invites.items() if x not in to_remove}
            if to_remove:
                log.debug(
                    f"Removing expired invites from guild {guild.name} (ID: {guild.id}):\n"
                    + ", ".join(to_remove)
                )
                await self.data.guild(guild).invites.set(bot_invites)
        return await self.data.all_guilds()

    async def add_invite(self, guild: discord.Guild, invite: str, roles: list) -> bool:
        """
        Add an invite link to the autorole system.

        Parameters
        ----------
        guild: :class:`discord.Guild`
            The guild to get the invites from.
        invite: :py:class:`str`
            The invite link to create/extend. Give ``main`` or ``default`` if
            you want to edit the main/default autorole system.
        roles: :py:class:`list`
            A list of roles ID to add to the roles list.

        Returns
        -------
        bool
            :py:obj:`True` if successful

        Raises
        ------
        :class:`~errors.NotInvite`
            The invite given is not a discord invite, not is is main/default.
        :class:`~errors.CannotGetInvites`
            The bot doesn't have the permission to get the guild's invites
        :class:`~errors.EmptyRolesList`
            The list of roles given is empty
        :class:`~errors.InviteNotFound`
            The invite given doesn't exist in the guild.
        """
        invites = await self.data.guild(guild).invites()
        if roles == []:
            raise errors.EmptyRolesList("No roles to add to the invite")

        try:
            guild_invite = await guild.invites()
        except discord.errors.Forbidden:
            raise errors.CannotGetInvites(
                'The "Manage server" permission is needed for this function'
            )

        if all(invite != x for x in ["default", "main"]):  # the invite given is a true invite
            try:
                invite_object = await self.bot.get_invite(invite)
            except discord.errors.NotFound:
                raise errors.NotInvite(f"Cannot get discord.Invite object from {invite}")

            invite_object = discord.utils.get(guild_invite, code=invite_object.code)
            if not invite_object:
                raise errors.InviteNotFound("The invite given doesn't exist in that guild")

        if invite not in invites:
            await self.data.guild(guild).invites.set_raw(invite, value={"roles": [], "uses": None})

        new_roles = await self.data.guild(guild).invites.get_raw(invite, "roles")
        new_roles.extend(roles)
        await self.data.guild(guild).invites.set_raw(invite, "roles", value=new_roles)
        if all(invite != x for x in ["default", "main"]):
            await self.data.guild(guild).invites.set_raw(invite, "uses", value=invite_object.uses)
        return True

    async def remove_invite(self, guild: discord.Guild, invite: str, roles: list = []) -> bool:
        """
        Remove a :py:class:`list` of roles from the invite links.

        Parameters
        ----------
        guild: :class:`discord.Guild`
            The guild to get the invites from.
        roles: :py:class:`list`
            A : py:class:`list` of roles ID to remove from the roles list. If it's empty, it will
            remove the invite from the autorole system.
        invite: :py:class`str`
            The invite to remove roles from. Give `main` or `default` to edit the main/default
            autorole system.

        Returns
        -------
        bool
            :py:obj:`True` if successful.
        Raises
        ------
        :py:class:`KeyError`
            The invite given doesn't exist.
        """

        invites = await self.data.guild(guild).invites()

        if invite not in invites:
            raise KeyError("That invite was never added.")

        if roles == []:
            # all roles will be removed
            del invites[invite]
            await self.data.guild(guild).invites.set(invites)
            return
        else:
            await self.data.guild(guild).invites.set_raw(
                invite,
                "roles",
                value=[
                    x
                    for x in await self.data.guild(guild).invites.get_raw(invite, "roles")
                    if x not in roles
                ],
            )
        if await self.data.guild(guild).invites.get_raw(invite, "roles") == []:
            del invites[invite]
            await self.data.guild(guild).invites.set(invites)
        return True

    async def get_invites(self, guild) -> dict:
        """
        Return a :py:class:`list` of the invites linked to the autorole system of the guild.

        Parameters
        ----------
        guild: :class:`discord.Guild`
            The guild to get the invites from.

        Returns
        -------
        dict
            A :py:class:`dict` of invites linked to any role on the guild.

            Example

            .. code-block:: json

                {
                    "main" : {
                        "roles" : [
                            987654321234567890
                        ]
                    },
                    "https://discord.gg/example" : {
                        "roles" : [
                            012345678987654321,
                            987654321234567890
                        ],
                        "uses" : 42
                    }
                }
        """

        return await self.data.guild(guild).invites()
