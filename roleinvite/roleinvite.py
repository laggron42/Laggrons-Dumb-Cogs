# RoleInvite by retke, aka El Laggron

import asyncio
import discord

from redbot.core import commands
from discord.utils import get
from redbot.core import Config
from redbot.core import checks
from redbot.core.utils.chat_formatting import pagify

from .api import API
from .errors import Errors

BaseCog = getattr(commands, "Cog", object)


class RoleInvite(BaseCog):
    """
    Server autorole following the invite the user used to join the server

    Report a bug or ask a question: https://discord.gg/AVzjfpR
    Full documentation and FAQ: https://laggrons-dumb-cogs.readthedocs.io/roleinvite.html
    """

    def __init__(self, bot):

        self.bot = bot
        self.data = Config.get_conf(self, 260)

        def_guild = {"invites": {}, "enabled": False}
        self.data.register_guild(**def_guild)
        self.api = API(self.bot, self.data)  # loading the API

    __author__ = "retke (El Laggron)"
    __version__ = "Laggrons-Dumb-Cogs/roleinvite beta 2c"
    __info__ = {
        "bot_version": "3.0.0b9",
        "description": (
            "Autorole based on the invite the user used.\n"
            "If the user joined using invite x, he will get "
            "a list of roles linked to invite x."
        ),
        "hidden": False,
        "install_msg": (
            "Thanks for installing roleinvite. Please check the wiki "
            "for all informations about the cog.\n"
            "https://laggrons-dumb-cogs.readthedocs.io/roleinvite.html\n"
            "Everything you need to know about setting up the cog is here.\n"
            "For a quick guide, type `[p]help RoleInvite`, just keep in mind "
            "that the bot needs the `Manage server` and the `Add roles` permissions."
        ),
        "required_cogs": [],
        "requirements": [],
        "short": "Autorole based on server's invites",
        "tags": ["autorole", "role", "join", "invite"],
    }

    async def check(self, ctx):
        # Used for author confirmation

        def confirm(message):
            return (
                message.author == ctx.author
                and message.channel == ctx.channel
                and message.content in ["yes", "no"]
            )

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

    async def invite_not_found(self, ctx):
        # used if the invite gave isn't found
        await ctx.send("That invite cannot be found")

    async def update_invites(self):
        # this will update every invites uses count
        # since it could have been modified while the bot was offline
        # executed on cog load

        bot_invites = await self.data.all_guilds()

        for guild_id in bot_invites:

            guild = self.bot.get_guild(guild_id)

            if guild is None:
                # bot has left the guild
                await self.data.guild(guild_id).clear()
                continue

            if await self.api.has_invites(guild):
                # we need to request guild invites, which requires manage server perm
                # if there's only the default autorole, no need to fetch that

                try:
                    invites = await guild.invites()
                except discord.errors.Forbidden:
                    # manage_roles permission was removed
                    # we disable the autorole to prevent more errors
                    await self.data.guild(guild).enabled.set(False)
                    raise Errors.CannotAddRole(
                        "The manage_roles permission was lost. "
                        "RoleInvite is now disabled on this guild."
                    )
            else:
                invites = None

            for invite in guild:
                try:
                    invite = self.bot.get_invite(invite)
                except discord.ext.commands.errors.CommandInvokeError:
                    del invites[invite.url]
                    continue

                if invites:
                    invite = get(guild.invites, code=invite.code)

                if not invite:
                    del invites[invite.url]
                else:
                    invites[invite.url]["uses"] = invite.uses
        await self.data.guild(guild)

    @commands.group()
    @checks.admin()
    async def roleset(self, ctx):
        """Roleinvite cog management"""

        if not ctx.invoked_subcommand:
            await ctx.send_help()

    @roleset.command()
    async def add(self, ctx, invite: str, *, role: discord.Role):
        """
        Link a role to an invite for the autorole system.

        Example: `[p]roleset add https://discord.gg/laggron Member`
        If this message still shows after using the command, you probably gave a wrong role name.
        If you want to link roles to the main autorole system (user joined with an unknown invite), give `main` instead of a discord invite.
        If you want to link roles to the default autorole system (roles given regardless of the invite used), give `default` instead of a discord invite.
        """

        async def roles_iteration(invite: str):
            if invite in bot_invites:
                # that means that the invite is already registered, and another role is going to be added
                current_roles = []

                for x in bot_invites[invite]["roles"]:
                    # iterating current roles so they can be showed to the user

                    bot_role = get(ctx.guild.roles, id=x)
                    if bot_role is None:
                        # the role doesn't exist anymore
                        bot_invites[invite]["roles"].remove(x)

                    elif x == role.id:
                        # the role that needs to be added is already linked
                        await ctx.send("That role is already linked to the invite.")
                        return False

                    else:
                        current_roles.append(bot_role.name)

                if current_roles == []:
                    return True

                await ctx.send(
                    "**WARNING**: This invite is already registered and currently linked to the role(s) `{}`.\n"
                    "If you continue, this invite will give all roles given to the new member. \n"
                    "If you want to edit it, first delete the link using `{}roleset remove`.\n\n"
                    "Do you want to link this invite to {} roles? (yes/no)".format(
                        "`, `".join(current_roles), ctx.prefix, len(current_roles) + 1
                    )
                )

                await self.data.guild(ctx.guild).invites.set(bot_invites)
                if not await self.check(ctx):  # the user answered no
                    return False
            return True

        if role.position >= ctx.guild.me.top_role.position:
            await ctx.send("That role is higher than mine. I can't add it to new users.")
            return

        if await commands.InviteConverter.convert(self, ctx, invite):
            # not the default autorole
            try:
                guild_invites = await ctx.guild.invites()
            except discord.errors.Forbidden:
                await ctx.send("I lack the `Manage server` permission.")
                return

            # splitting the string so https://discord.gg/abc becomes abc
            invite = invite.split("/")
            invite = invite[len(invite) - 1]

            invite = get(guild_invites, code=invite)
            if not invite:
                await self.invite_not_found(ctx)
                return

            if guild_invites == []:
                await ctx.send("There are no invites generated on this server.")
                return

        elif invite == "main":
            # not needed atm, but it will be, so we check for the permission
            try:
                guild_invites = await ctx.guild.invites()
            except discord.errors.Forbidden:
                await ctx.send("I lack the `Manage server` permission.")
            return

        elif invite != "default":
            # invite is not a discord.Invite nor it is main/default (default autorole)
            await self.invite_not_found(ctx)
            return

        bot_invites = await self.data.guild(ctx.guild).invites()

        if invite == "main":
            if not await roles_iteration(invite):
                return
            await self.api.add_invite(ctx.guild, "main", [role.id])
            await ctx.send(
                "The role `{}` is now linked to the main autorole system. "
                "(new members will get it if they join with an invite not registered)".format(
                    role.name
                )
            )
            return

        elif invite == "default":
            if not await roles_iteration(invite):
                return
            await self.api.add_invite(ctx.guild, "default", [role.id])
            await ctx.send(
                "The role `{}` is now linked to the default autorole system. "
                "(new members will always get this role, whatever invite he used.)".format(
                    role.name
                )
            )
            return

        for guild_invite in guild_invites:
            if invite.url == guild_invite.url:

                if not await roles_iteration(invite.url):
                    return
                await self.api.add_invite(ctx.guild, invite.url, [role.id])
                await ctx.send(
                    "The role `{}` is now linked to the invite {}".format(role.name, invite.url)
                )
                return

        await self.invite_not_found(ctx)

    @roleset.command()
    async def remove(self, ctx, invite: str, *, role: discord.Role = None):
        """
        Remove a link in this server
        
        Specify a `role` to only remove one role from the invite link list.
        Don't specify anything if you want to remove the invite itself.
        If you want to edit the main/default autorole system's roles, give `main`/`default` instead of a discord invite.
        """

        bot_invites = await self.data.guild(ctx.guild).invites()

        if invite not in bot_invites:
            await ctx.send("That invite cannot be found")
            return

        for bot_invite_str, bot_invite in bot_invites.items():
            if bot_invite_str == invite:

                if role is None or len(bot_invite["roles"]) <= 1:
                    # user will unlink the invite from the autorole system

                    roles = [get(ctx.guild.roles, id=x) for x in bot_invite["roles"]]

                    if invite == "main":
                        message = "You're about to remove all roles linked to the main autorole.\n"
                    elif invite == "default":
                        message = (
                            "You're about to remove all roles linked to the default autorole.\n"
                        )
                    else:
                        message = "You're about to remove all roles linked to this invite.\n"

                    message += (
                        "```Diff\n"
                        "List of roles:\n\n"
                        "+ {}\n"
                        "```\n\n"
                        "Proceed? (yes/no)\n\n".format("\n+ ".join([x.name for x in roles]))
                    )

                    if len(bot_invite["roles"]) > 1:
                        message += (
                            "Remember that you can remove a single role from this list by typing "
                            "`{}roleset remove {} [role name]`".format(ctx.prefix, invite)
                        )

                    await ctx.send(message)

                    if not await self.check(ctx):  # the user answered no
                        return

                    await self.api.remove_invite(ctx.guild, invite=invite)
                    await ctx.send("The invite {} has been removed from the list.".format(invite))
                    return  # prevents a RuntimeError because of dict changes

                else:
                    # user will remove only one role from the invite link

                    if invite == "main":
                        message = "You're about to unlink the `{}` role from the main autorole.".format(
                            role.name
                        )
                    elif invite == "default":
                        message = "You're about to unlink the `{}` role from the default autorole.".format(
                            role.name
                        )
                    else:
                        message = "You're about to unlink the `{}` role from the invite {}.".format(
                            role.name, invite
                        )
                    await ctx.send(message + "\nProceed? (yes/no)")

                    if not await self.check(ctx):  # the user answered no
                        return

                    await self.api.remove_invite(ctx.guild, invite, [role.id])
                    await ctx.send(
                        "The role `{}` is unlinked from the invite {}".format(
                            role.name, bot_invite_str
                        )
                    )

        await self.invite_not_found(ctx)

    @roleset.command()
    async def list(self, ctx):
        """
        List all links on this server
        """

        invites = await self.data.guild(ctx.guild).invites()
        embeds = []
        to_delete = []

        for i, invite in invites.items():

            if all(i != x for x in ["default", "main"]):
                try:
                    invite = await self.bot.get_invite(i)
                except discord.errors.NotFound:
                    to_delete.append(i)  # if the invite got deleted

            roles = []
            for role in invites[i]["roles"]:
                roles.append(get(ctx.guild.roles, id=role))

            embed = discord.Embed()
            embed.color = ctx.guild.me.color
            if i == "main":
                embed.add_field(
                    name="Roles linked to the main autorole",
                    value="\n".join([x.name for x in roles]),
                )
                embed.set_footer(
                    text="These roles are given if the member joined with an other invite than those linked"
                )
            elif i == "default":
                embed.add_field(
                    name="Roles linked to the default autorole",
                    value="\n".join([x.name for x in roles]),
                )
                embed.set_footer(
                    text="These roles are always given to the new members, regardless of the invite used."
                )
            else:
                embed.add_field(
                    name="Roles linked to " + str(i), value="\n".join([x.name for x in roles])
                )
            embed.set_footer(text="These roles are given if the user joined using " + i)

            embeds.append(embed)

        for deletion in to_delete:
            del invites[deletion]
        await self.data.guild(ctx.guild).invites.set(invites)

        if embeds == []:
            await ctx.send(
                "There is nothing set on RoleInvite. Type `{}roleset` for more informations.".format(
                    ctx.prefix
                )
            )
            return

        await ctx.send("List of invites linked to an autorole on this server:")
        for embed in embeds:
            try:
                await ctx.send(embed=embed)
            except discord.errors.Forbidden:
                await ctx.send("I lack the `Embed links` permission.")
                return

        if not await self.data.guild(ctx.guild).enabled():
            await ctx.send(
                "**Info:** RoleInvite is currently disabled and won't give roles on member join.\n"
                "Type `{}roleset enable` to enable it.".format(ctx.prefix)
            )

    @roleset.command()
    async def enable(self, ctx):
        """
        Enable or disabe the autorole system.

        If it was disabled within your action, that means that the bot somehow lost the `manage_roles` permission.
        """

        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("I lack the `Manage roles` permission.")
            return

        if not await self.data.guild(ctx.guild).enabled():
            await self.data.guild(ctx.guild).enabled.set(True)
            await ctx.send(
                "The autorole system is now enabled on this server.\n"
                "Type `{0.prefix}roleset list` to see what's the current role list.\n"
                "If the bot lose the `Manage roles` permission, the autorole will be disabled.".format(
                    ctx
                )
            )

        else:
            await self.data.guild(ctx.guild).enabled.set(False)
            await ctx.send(
                "The autorole system is now disabled on this server.\n"
                "Type `{0.prefix}roleset enable` to enable it back.\n\n"
                "The settings are still saved, and you can also edit them. New members will just be ignored.".format(
                    ctx
                )
            )

    async def on_member_join(self, member):
        async def add_roles(invite):
            roles = []
            for role in invites[invite]["roles"]:
                role = get(guild.roles, id=role)
                roles.append(role)

            # iterating all roles linked to the autorole
            for role in roles:

                if invite == "main":
                    reason = "Joined with an unknown invite, main roles given."
                elif invite == "default":
                    reason = "Default roles given."
                else:
                    reason = "Joined with " + invite

                try:
                    await member.add_roles(role, reason="Roleinvite autorole. " + reason)

                except discord.errors.Forbidden:

                    if role.position >= guild.me.top_role.position:
                        # The role is above or equal to the bot's highest role in the hierarchy
                        # we're removing this role from the list to prevent more errors
                        invites[invite.url]["roles"].remove(role.id)
                        raise Errors.CannotAddRole(
                            "Role {} is too high in the role hierarchy. "
                            "Now removed from the list."
                        )

                    if not member.guild.me.guild_permissions.manage_roles:
                        # manage_roles permission was removed
                        # we disable the autorole to prevent more errors
                        await self.data.guild(guild).enabled.set(False)
                        raise Errors.CannotAddRole(
                            "The manage_roles permission was lost. "
                            "RoleInvite is now disabled on this guild."
                        )
            return True

        guild = member.guild
        invites = await self.data.guild(guild).invites()

        if not await self.data.guild(guild).enabled():
            return  # autorole disabled

        if not await add_roles("default"):
            return

        if await self.api.has_invites(guild):
            try:
                guild_invites = await guild.invites()
            except discord.errors.Forbidden:
                # manage guild permission removed
                # we disable the autorole to prevent more errors
                await self.data.guild(guild).enabled.set(False)
                raise Errors.CannotGetInvites(
                    "The manage_server permission was lost. "
                    "RoleInvite is now disabled on this guild."
                )
        else:
            return

        for invite in invites:

            if any(invite == x for x in ["default", "main"]):
                continue

            invite = get(guild_invites, url=invite)
            if not invite:
                del invites[invite.url]
            else:
                if invite.uses > invites[invite.url]["uses"]:
                    # the invite has more uses than what we registered before
                    # this is the one used by the member

                    if not await add_roles(invite.url):
                        return

                    invites[invite.url]["uses"] = invite.uses  # updating uses count
                    await self.data.guild(guild).invites.set(invites)
                    return  # so it won't iterate other invites registered

        if not await add_roles("main"):
            return
