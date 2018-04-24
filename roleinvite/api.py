import discord
from redbot.core import Config
from .errors import Errors

class API:
    """Interact with roleinvite using these functions.
    Get the full doc on the wiki (https://github.com/retke/Laggrons-Dumb-Cogs/wiki)
    or by reading the docstrings"""

    def __init__(self, bot, config):
        self.bot = bot
        self.data = config

    async def add_invite(self, guild: discord.Guild, invite: discord.Invite, roles: list):
        """
        This is a coroutine.
        Add an invite link to the autorole system.
        
        Parameters:
        
        `guild(discord.Guild)`   : The guild to get the invites from.
        `invite(discord.Invite)` : The invite to extend. Get it using `guild.invites()`.
        `roles(list)`            : A list of roles ID to add to the roles list.

        Raises:

        `CannotGetInvites`  : The bot doesn't have the permission to get the guild's invites
        `EmptyRolesList`    : The list of roles given is empty
        `WrongInviteObject` : Cannot get the number of uses (due to the use of Client.get_invite())
        `InviteNotFound`    : The invite given doesn't exist in the guild.
        """

        invites = await self.data.guild(guild).invites()
        try:
            guild_invite = await guild.invites()
        except discord.errors.Forbidden:
            raise Errors.CannotGetInvites("The Manage server permission is needed for this function")

        if roles == []:
            raise Errors.EmptyRolesList("No roles to add to the invite")
        if invite.uses is None:
            raise Errors.WrongInviteObject("That invite cannot get its count. "
                                "Get the object using guild.invites, not bot.get_invite().")
        if invite not in guild_invite:
            raise Errors.InviteNotFound("The invite given doesn't exist in that guild")
        

        if invite.url not in invites:
            invites[invite.url] = {
                "roles" : [],
                "uses"  : 0
            }
        invites[invite.url]['roles'].extend(roles)
        invites[invite.url]['uses'] = invite.uses

        await self.data.guild(guild).invites.set(invites)


    async def remove_invite(self, guild: discord.Guild, invite: str, roles: list = []):
        """
        Remove a list of roles from the invite links.
        
        Parameters:
        
        `guild(discord.Guild)`   : The guild to get the invites from.
        `invite(discord.Invite)` : The invite to remove roles from.
        `roles(list)`            : A list of roles ID to remove from the roles list. If it's empty, it will remove the invite from the autorole system.
        
        Raises:

        `KeyError` : The invite given doesn't exist.
        """

        invites = await self.data.guild(guild).invites()
        
        if invite not in invites:
            raise KeyError("That invite was never added.")
        
        if roles == []:
            # all roles will be removed
            del invites[invite]
        else:
            invites[invite]['roles'] = [x for x in invites[invite]['roles'] if x not in roles]
        await self.data.guild(guild).invites.set(invites)

    
    async def get_invites(self, guild):
        """
        Return a list of the invites linked to the autorole system of the guild.
        
        Parameters:

        `guild(discord.Guild)` : The guild to get the invites from.
        
        Returns:
        
        A `dict` of invites linked to any role on the guild.
        Body:
        ```Json
        {
            "https://discord.gg/abc" : {
                "roles" : [
                    012345678987654321
                ],
                "uses" : 42
            }
        }
        ```
        """

        return await self.data.guild(guild).invites()