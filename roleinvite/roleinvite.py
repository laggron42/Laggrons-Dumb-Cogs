import discord
import asyncio
import json

from discord.ext import commands
from discord.utils import get
from redbot.core import Config
from redbot.core import checks
from redbot.core.utils.chat_formatting import pagify

from .api import API

class RoleInvite:
    """Server autorole following the invite the user used to join the server

    Report a bug or ask a question: https://discord.gg/WsTGeQ"""

    def __init__(self, bot):
        self.bot = bot
        self.data = Config.get_conf(self, 260)

        def_guild = {'invites' : {}} # cauz config is glitchy atm
        self.data.register_guild(**def_guild)

        self.api = API(self.bot, self.data) # loading the API

    __author__ = "retke (El Laggron)"

    
    async def check(self, ctx):
        # Used for author confirmation

        def confirm(message):
            return message.author == ctx.author and message.channel == ctx.channel and message.content in ["yes", "no"]

        try:
            response = await self.bot.wait_for("message", timeout=120, check=confirm)
        except asyncio.TimeoutError:
            await ctx.send("Question timed out.")
            return False

        if response.content == "no":
            await ctx.send("Aborting...")
            return False
        else:
            return True
        

    @commands.group()
    @checks.admin()
    async def roleset(self, ctx):
        """Roleinvite cog management"""

        if not ctx.invoked_subcommand:
            await ctx.send_help()

    
    @roleset.command()
    async def add(self, ctx, invite: discord.Invite, *, role: discord.Role):
        """Link a role to an invite

        Example: `[p]roleset add https://discord.gg/laggron Member`
        If this message still shows after using the command, you probably gave a wrong role name / invite."""

        async def invite_not_found():
            await ctx.send("That invite cannot be found")
            return

        if role.position >= ctx.guild.me.top_role.position:
            await ctx.send("That role is higher than mine. I can't add it to new users.")
            return

        try:
            guild_invites = await ctx.guild.invites()
        except discord.errors.Forbidden:
            await ctx.send("I lack the `Manage server` permission.")
            return

        invite = get(guild_invites, code=invite.code)
        if not invite:
            await invite_not_found()
            return

        if guild_invites == []:
            await ctx.send("There are no invites on this server.")
            return
        
        bot_invites = await self.data.guild(ctx.guild).invites()
        for guild_invite in guild_invites: 
            if invite.url == guild_invite.url:
                if invite.url in bot_invites:

                    current_roles = []

                    for x in bot_invites[invite.url]['roles']:
                            
                        bot_role = get(ctx.guild.roles, id=x)
                        if bot_role is None:
                            bot_invites[invite.url]['roles'].remove(x)
                        elif x == role.id:
                            await ctx.send("That role is already linked to the invite.")
                            return
                        else:
                            current_roles.append(bot_role.name)

                    await ctx.send("**WARNING**: This invite is already registered and currently linked to the role(s) `{}`.\n"
                            "If you continue, this invite will give all roles given to the new member. \n"
                            "If you want to edit it, first delete the link using `{}roleset remove`.\n\n"
                            "Do you want to link this invite to {} roles? (yes/no)".format(
                                "`, `".join(current_roles), ctx.prefix, len(current_roles) + 1
                            ))

                    resp = await self.check(ctx)
                    if not resp: # the user answered no
                        return

                await self.api.add_invite(ctx.guild, invite, [role.id])
                await ctx.send("The role `{}` is now linked to the invite {}".format(role.name, invite.url))
                return

        await invite_not_found()


    @roleset.command()
    async def remove(self, ctx, invite: str, role: discord.Role=None):
        """Remove a link in this server
        
        Specify a `role` to only remove one role from the invite link list.
        Don't specify anything if you want to remove the invite itself."""

        bot_invites = await self.data.guild(ctx.guild).invites()

        if invite not in bot_invites:
            await ctx.send("That invite cannot be found")
            return

        for bot_invite_str, bot_invite in bot_invites.items():
            if bot_invite_str == invite:

                if role is None or len(bot_invite['roles']) <= 1:
                    roles = [get(ctx.guild.roles, id=x) for x in bot_invite['roles']]

                    await ctx.send("You're about to remove all roles linked to this invite.\n"
                                "```Diff\n"
                                "List of roles:\n\n"
                                "+ {}\n"
                                "```\n\n"
                                "Proceed? (yes/no)\n\n"
                                "Remember that you can remove a single role from this list by typing "
                                "`{}roleset remove {} [role name]`".format(
                                    "\n+ ".join([x.name for x in roles]), ctx.prefix, invite
                                ))
                    resp = await self.check(ctx)
                    if not resp: # the user answered no
                        return

                    await self.api.remove_invite(ctx.guild, invite)
                    await ctx.send("The invite {} has been removed from the list.".format(invite))
                    return # prevents a RuntimeError because of dict changes

                else:
                    await ctx.send("You're about to unlink the `{}` role from the invite {}.\n"
                                "Proceed? (yes/no)".format(role.name, invite))
                    resp = await self.check(ctx)
                    if not resp: # the user answered no
                        return

                    await self.api.remove_invite(ctx.guild, invite, [role.id])
                    await ctx.send("The role `{}` is unlinked from the invite {}".format(role.name, bot_invite_str))
    

    @roleset.command()
    async def list(self, ctx):
        """List all links on this server"""

        invites = await self.data.guild(ctx.guild).invites()
        embeds = []

        for i, invite in invites.items():

            try:
                invite = await self.bot.get_invite(i)
            except discord.errors.NotFound:
                del invites[i] # if the invite got deleted
            else:
                roles = []
                for role in invites[i]['roles']:
                    roles.append(get(ctx.guild.roles, id=role))
                
                embed = discord.Embed()
                embed.color = ctx.guild.me.color
                embed.add_field(name="Roles linked to " + str(i), value="\n".join([x.name for x in roles]))

                embeds.append(embed)
        
        if embeds == []:
            await ctx.send("There is no invite linked to an autorole on this server.")
            return

        await ctx.send("List of invites linked to an autorole on this server:")
        for embed in embeds:
            try:
                await ctx.send(embed=embed)
            except discord.errors.Forbidden:
                await ctx.send("I lack the `Embed links` permission.")
                return


    async def on_member_join(self, member):
        guild = member.guild
        invites = await self.data.guild(guild).invites()
        for invite in invites:
            try:
                guild_invites = await guild.invites()
            except discord.errors.Forbidden:
                return # manage guild permission removed
            
            invite = get(guild_invites, url=invite)
            if not invite:
                del invites[invite.url]
            else:
                if invite in guild_invites and invite.uses > invites[invite.url]['uses']:
                    roles_id = invites[invite.url]['roles']
                    roles = []
                    for role in roles_id:
                        role = get(guild.roles, id=role)
                        roles.append(role)

                    for role in roles:
                        await member.add_roles(role, reason="Roleinvite autorole. Joined with " + invite.url)

                    invites[invite.url]['uses'] = invite.uses
                    await self.data.guild(guild).invites.set(invites)
                    return