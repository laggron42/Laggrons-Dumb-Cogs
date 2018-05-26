import discord
from .errors import Errors


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

    async def has_invites(self, guild):
        """
        Return a bool telling if there are invites links in the autorole system, or main ones.
        This can tell if the :attr:`~discord.Permissions.manage_guild`
        permission is needed or not.

        Parameters
        ----------
        guild: :class:`discord.Guild`
            The guild to get the invites from.

        Returns
        -------
        bool
            :py:obj:`True` if there are invite links, else :py:obj:`False`.
        """

        invites = await self.data.guild(guild).invites()
        for invite in invites:
            if invite != "default":
                return True
        return False

    async def add_invite(self, guild: discord.Guild, invite: str, roles: list):
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
        :class:`~Errors.NotInvite`
            The invite given is not a discord invite, not is is main/default.
        :class:`~Errors.CannotGetInvites`
            The bot doesn't have the permission to get the guild's invites
        :class:`~Errors.EmptyRolesList`
            The list of roles given is empty
        :class:`~Errors.InviteNotFound`
            The invite given doesn't exist in the guild.
        """

        invites = await self.data.guild(guild).invites()

        if all(invite != x for x in ["default", "main"]):  # the invite given is not default

            try:
                invite_object = await self.bot.get_invite(invite)
            except discord.errors.NotFound:
                raise Errors.NotInvite("Cannot get discord.Invite object from " + invite)

            try:
                guild_invite = await guild.invites()
            except discord.errors.Forbidden:
                raise Errors.CannotGetInvites(
                    "The Manage server permission is needed for this function"
                )

            invite_object = discord.utils.get(guild_invite, code=invite_object.code)
            if not invite_object:
                raise Errors.InviteNotFound("The invite given doesn't exist in that guild")

        elif all(invite != x for x in ["default", "main"]):
            raise Errors.NotInvite("The invite sent isn't a discord.Invite, not it is main/default")

        if roles == []:
            raise Errors.EmptyRolesList("No roles to add to the invite")

        if invite not in invites:
            invites[invite] = {"roles": [], "uses": None}

        invites[invite]["roles"].extend(roles)
        if all(invite != x for x in ["default", "main"]):
            invites[invite]["uses"] = invite_object.uses

        await self.data.guild(guild).invites.set(invites)
        return True

    async def remove_invite(self, guild: discord.Guild, invite: str, roles: list = []):
        """
        Remove a :py:class:`list` of roles from the invite links.
        
        Parameters
        ----------
        guild: :class:`discord.Guild`
            The guild to get the invites from.
        roles: :py:class:list
            A : py:class:`list` of roles ID to remove from the roles list. If it's empty, it will remove the invite from the autorole system.
        invite: :py:class`str`
            The invite to remove roles from. Give `main` or `default` to edit the main/default autorole system.

        Returns
        -------
        bool
            :py:obj:`True` if successful
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
        else:
            invites[invite]["roles"] = [x for x in invites[invite]["roles"] if x not in roles]
        await self.data.guild(guild).invites.set(invites)
        return True

    async def get_invites(self, guild):
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
