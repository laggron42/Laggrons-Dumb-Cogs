# RoleInvite by retke, aka El Laggron
import asyncio
import logging
import discord

from typing import TYPE_CHECKING

from redbot.core import commands
from redbot.core import Config
from redbot.core import checks
from redbot.core.i18n import cog_i18n, Translator
from redbot.core.utils.predicates import MessagePredicate
from redbot.core.utils.chat_formatting import pagify

# creating this before importing other modules allows to import the translator
_ = Translator("WarnSystem", __file__)

from .api import API
from . import errors

if TYPE_CHECKING:
    from .loggers import Log

log = None
BaseCog = getattr(commands, "Cog", object)


@cog_i18n(_)
class RoleInvite(BaseCog):
    """
    Server autorole following the invite the user used to join the server

    Report a bug or ask a question: https://discord.gg/AVzjfpR
    Full documentation and FAQ: https://laggrons-dumb-cogs.readthedocs.io/roleinvite.html
    """

    def_guild = {"invites": {}, "enabled": False}

    def __init__(self, bot):
        self.bot = bot

        self.data = Config.get_conf(self, 260)
        self.data.register_guild(**self.def_guild)

        self.api = API(bot, self.data)
        self.errors = errors
        self.sentry = None
        self.translator = _

        bot.loop.create_task(self.api.update_invites())

    __author__ = "retke (El Laggron)"
    __version__ = "2.0.0"
    __info__ = {
        "bot_version": "3.0.0b14",
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

    def _set_log(self, sentry: "Log"):
        self.sentry = sentry
        global log
        log = logging.getLogger("laggron.warnsystem")
        # this is called now so the logger is already initialized

    async def _check(self, ctx: commands.Context):
        """
        Wait for user confirm.
        """
        pred = MessagePredicate.yes_or_no(ctx)
        try:
            await self.bot.wait_for("message", check=pred)
        except asyncio.TimeoutError:
            await ctx.send(_("Request timed out."))
            return False
        return pred.result

    @commands.group()
    @checks.admin()
    async def inviteset(self, ctx):
        """
        Roleinvite cog management

        For a clear explaination of how the cog works, read the documentation.
        https://laggrons-dumb-cogs.readthedocs.io/
        """
        pass

    @inviteset.command()
    async def add(self, ctx, invite: str, *, role: discord.Role):
        """
        Link a role to an invite for the autorole system.

        Example: `[p]inviteset add https://discord.gg/laggron Member`
        If this message still shows after using the command, you probably gave a wrong role name.
        If you want to link roles to the main autorole system (user joined with an unknown invite),\
        give `main` instead of a discord invite.
        If you want to link roles to the default autorole system (roles given regardless of the\
        invite used), give `default` instead of a discord invite.
        """

        async def roles_iteration(invite: str):
            if invite in bot_invites:
                # means that the invite is already registered, we will append the role
                # to the existing list
                current_roles = []

                for x in bot_invites[invite]["roles"]:
                    # iterating current roles so they can be showed to the user
                    bot_role = discord.utils.get(ctx.guild.roles, id=x)
                    if bot_role is None:
                        # the role doesn't exist anymore
                        bot_invites[invite]["roles"].remove(x)
                    elif x == role.id:
                        # the role that needs to be added is already linked
                        await ctx.send(_("That role is already linked to the invite."))
                        return False
                    else:
                        current_roles.append(bot_role.name)

                await self.data.guild(ctx.guild).invites.set(bot_invites)

                if not current_roles:
                    return True  # all roles deleted

                await ctx.send(
                    _(
                        "**Warning**: This invite is already registered and currently linked to "
                        "the role(s) `{}`.\nIf you continue, this invite will give all roles "
                        "given to the new member. \nIf you want to edit it, first delete the link "
                        "using `{}inviteset remove`.\n\nDo you want to link this invite to {} "
                        "roles? (yes/no)"
                    ).format("`, `".join(current_roles), ctx.prefix, len(current_roles) + 1)
                )

                if not await self._check(ctx):  # the user answered no
                    return False
            return True

        # permission checks
        if role.position >= ctx.guild.me.top_role.position:
            await ctx.send(_("That role is higher than mine. I can't add it to new users."))
            return
        if not ctx.guild.me.guild_permissions.manage_guild:
            await ctx.send(_("I need the `Manage server` permission!"))
            return
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send(_("I need the `Manage roles` permission!"))
            return

        guild_invites = await ctx.guild.invites()
        try:
            invite = await commands.InviteConverter.convert(self, ctx, invite)
        except (commands.BadArgument, IndexError):
            if not any(invite == x for x in ["main", "default"]):
                await ctx.send(_("That invite cannot be found"))
                return
        else:  # not the default autorole, checks if the invite is valid
            if invite.channel.guild != ctx.guild:
                await ctx.send(_("That invite doesn't belong to this server!"))
                return
            if not guild_invites:
                await ctx.send(_("There are no invites generated on this server."))
                return

        bot_invites = await self.data.guild(ctx.guild).invites()
        if invite == "main":
            if not await roles_iteration(invite):
                return
            await self.api.add_invite(ctx.guild, "main", [role.id])
            await ctx.send(
                _(
                    "The role `{}` is now linked to the main autorole system. "
                    "(new members will get it if they join with an invite not registered)"
                ).format(role.name)
            )
            return
        elif invite == "default":
            if not await roles_iteration(invite):
                return
            await self.api.add_invite(ctx.guild, "default", [role.id])
            await ctx.send(
                _(
                    "The role `{}` is now linked to the default autorole system. "
                    "(new members will always get this role, whatever invite he used.)"
                ).format(role.name)
            )
            return
        # invite is not "main" or "default", we try to find the invite
        for guild_invite in guild_invites:
            if invite.url == guild_invite.url:
                if not await roles_iteration(invite.url):
                    return
                await self.api.add_invite(ctx.guild, invite.url, [role.id])
                await ctx.send(
                    _("The role `{}` is now linked to the invite `{}`").format(
                        role.name, self.api.escape_invite_links(invite.url)
                    )
                )
                return
        # not "main", "default" or an invite for the guild
        await ctx.send(_("That invite cannot be found"))

    @inviteset.command()
    async def remove(self, ctx, invite: str, *, role: discord.Role = None):
        """
        Remove a link in this server

        Specify a `role` to only remove one role from the invite link list.
        Don't specify anything if you want to remove the invite itself.
        If you want to edit the main/default autorole system's roles, give \
        `main`/`default` instead of a discord invite.
        """
        invites = await self.data.guild(ctx.guild).invites()
        invites = {x.split("/")[-1]: y for x, y in invites.items()}  # removes https://discord.gg/
        invite = invite.split("/")[-1]  # also removes https://discord.gg
        bot_invite = invites.get(invite)
        if not bot_invite:
            await ctx.send(_("That invite cannot be found"))
            return

        if not role or len(bot_invite["roles"]) <= 1:
            # user will remove the invite from the autorole system
            roles = [discord.utils.get(ctx.guild.roles, id=x) for x in bot_invite["roles"]]
            roles = [x for x in roles if x]  # removes deleted roles
            if not roles:  # no more roles after cleaning
                await self.api.remove_invite(ctx.guild, f"http://discord.gg/{invite}")
                await ctx.send(_("That invite lost all of its linked roles and was deleted."))
                return

            if invite == "main":
                message = _("You're about to remove all roles linked to the main autorole.\n")
            elif invite == "default":
                message = _("You're about to remove all roles linked to the default autorole.\n")
            else:
                message = _("You're about to remove all roles linked to this invite.\n")

            message += _("List of roles:\n{}\nProceed? (yes/no)\n\n").format(
                "```Diff\n+ " + "\n+ ".join([x.name for x in roles]) + "\n```"
            )

            if len(bot_invite["roles"]) > 1:
                message += _(
                    "Remember that you can remove a single role from this list by typing "
                    "`{}inviteset remove {} [role name]`"
                ).format(ctx.prefix, invite)

            await ctx.send(message)
            if not await self._check(ctx):  # the user answered no
                await ctx.send(_("Alright, invite is kept."))
                return

            await self.api.remove_invite(ctx.guild, invite=f"http://discord.gg/{invite}")
            await ctx.send(
                _("The invite `{}` has been removed from the list.").format(
                    self.api.escape_invite_links(f"http://discord.gg/{invite}")
                )
            )

        else:
            # user will remove only one role from the invite link
            if invite == "main":
                message = _("main autorole.")
            elif invite == "default":
                message = _("default autorole.")
            else:
                message = _("invite `{}`.").format(self.api.escape_invite_links(invite))
            await ctx.send(
                _("You're about to unlink the `{}` role from the {}\nProceed? (yes/no)").format(
                    role.name, message
                )
            )

            if not await self._check(ctx):  # the user answered no
                await ctx.send(_("Alright, role is kept."))
                return

            await self.api.remove_invite(ctx.guild, invite, [role.id])
            await ctx.send(
                _("The role `{}` is now unlinked from the {}").format(role.name, message)
            )

    @inviteset.command()
    async def list(self, ctx):
        """
        List all links on this server
        """
        invites = await self.data.guild(ctx.guild).invites()
        text = ""
        to_delete = []
        if not ctx.me.guild_permissions.embed_links:
            await ctx.send("I need the `Embed links` permission.")
            return

        for i, invite in invites.items():
            if all(i != x for x in ["default", "main"]):
                try:
                    await self.bot.get_invite(i)
                except discord.errors.NotFound:
                    to_delete.append(i)  # if the invite got deleted
                    continue
            roles = []
            for role in invites[i]["roles"]:
                role = discord.utils.get(ctx.guild.roles, id=role)
                if role:
                    roles.append(role)
            if not roles:
                to_delete.append(i)  # no more roles
                continue
            roles_names = "\n+ ".join([x.name for x in roles])

            if i == "default":
                text += f"{_('Roles linked to the default autorole')}:\n+ {roles_names}\n\n"
            elif i == "main":
                text += f"{_('Roles linked to the main autorole')}:\n+ {roles_names}\n\n"
            else:
                i = self.api.escape_invite_links(i)
                text += f"{_('Roles linked to')} {i}:\n+ {roles_names}\n\n"

        for deletion in to_delete:
            del invites[deletion]
        if to_delete:
            await self.data.guild(ctx.guild).invites.set(invites)
        if not text:
            await ctx.send(
                _(
                    "There is nothing set on RoleInvite. "
                    "Type `{}help inviteset` for more informations."
                ).format(ctx.prefix)
            )
            return
        if not await self.data.guild(ctx.guild).enabled():
            text += _(
                "**Info:** RoleInvite is currently disabled and won't give roles on member "
                "join.\nType `{}inviteset enable` to enable it."
            ).format(ctx.prefix)

        text = (
            _("List of invites linked to an autorole on this server:") + f"\n```Diff\n{text}\n```"
        )
        for page in pagify(text, delims=("\n\n", "\n"), priority=True, escape_mass_mentions=True):
            # ^ get pages and tries to separate them between paragraphs
            await ctx.send(page)

    @inviteset.command()
    async def enable(self, ctx):
        """
        Enable or disabe the autorole system.

        If it was disabled within your action, that means that the bot somehow lost the\
        `Manage roles` or the `Manage server` permission.
        """

        if not ctx.me.guild_permissions.manage_roles:
            await ctx.send(_("I need the `Manage roles` permission."))
            return
        if not ctx.me.guild_permissions.manage_guild:
            await ctx.send(_("I need the `Manage server` permission."))
            return
        current = not await self.data.guild(ctx.guild).enabled()
        await self.data.guild(ctx.guild).enabled.set(current)

        if current:
            await ctx.send(
                _(
                    "The autorole system is now enabled on this server.\n"
                    "Type `{0.prefix}inviteset list` to see what's the current role list.\n"
                    "If the bot lose the `Manage roles` or the `Manage server` permissions "
                ).format(ctx)
            )

    @commands.command(hidden=True)
    @checks.is_owner()
    async def roleinviteinfo(self, ctx, sentry: str = None):
        """
        Get informations about the cog.

        Type `sentry` after your command to modify its status.
        """

        current_status = await self.data.enable_sentry()
        status = lambda x: (_("enable"), _("enabled")) if x else (_("disable"), _("disabled"))
        if sentry is not None and "sentry" in sentry:
            await ctx.send(
                _(
                    "You're about to {} error logging. Are you sure you want to do this? Type "
                    "`yes` to confirm."
                ).format(status(not current_status)[0])
            )
            predicate = MessagePredicate.yes_or_no(ctx)
            try:
                await self.bot.wait_for("message", timeout=60, check=predicate)
            except asyncio.TimeoutError:
                await ctx.send(_("Request timed out."))
            else:
                if predicate.result:
                    await self.data.enable_sentry.set(not current_status)
                    if not current_status:
                        # now enabled
                        self.sentry.enable()
                        await ctx.send(
                            _(
                                "Upcoming errors will be reported automatically for a faster fix. "
                                "Thank you for helping me with the development process!"
                            )
                        )
                    else:
                        # disabled
                        self.sentry.disable()
                        await ctx.send(_("Error logging has been disabled."))
                    log.info(
                        f"Sentry error reporting was {status(not current_status)[1]} "
                        "on this instance."
                    )
                else:
                    await ctx.send(
                        _("Okay, error logging will stay {}.").format(status(current_status)[1])
                    )
                return

        message = _(
            "Laggron's Dumb Cogs V3 - roleinvite\n\n"
            "Version: {0.__version__}\n"
            "Author: {0.__author__}\n"
            "Sentry error reporting: {1} (type `{2}roleinviteinfo sentry` to change this)\n\n"
            "Github repository: https://github.com/retke/Laggrons-Dumb-Cogs/tree/v3\n"
            "Discord server: https://discord.gg/AVzjfpR\n"
            "Documentation: http://laggrons-dumb-cogs.readthedocs.io/\n\n"
            "Support my work on Patreon: https://www.patreon.com/retke"
        ).format(self, status(current_status)[1], ctx.prefix)
        await ctx.send(message)

    @commands.command()
    async def error(self, ctx):
        raise KeyError("Hello it's RoleInvite")

    async def on_member_join(self, member):
        async def add_roles(invite):
            invites_data = bot_invites[invite]
            if invite == "main":
                reason = _("Joined with an unknown invite, main roles given.")
            elif invite == "default":
                reason = _("Default roles given.")
            else:
                reason = _("Joined with {}").format(invite)

            roles_data = invites_data["roles"]
            roles = []  # roles object to add to the member
            to_remove = []  # lost roles
            for role_id in roles_data:
                role = discord.utils.get(guild.roles, id=role_id)
                if role is None:
                    to_remove.append(role_id)
                else:
                    roles.append(role)
            if to_remove:
                roles_id_str = ", ".join([str(x) for x in to_remove])
                log.warning(
                    "Removing the following roles because they were not found on the server.\n"
                    f"Roles ID: {roles_id_str}\n"
                    f"Guild: {guild.name} (ID: {guild.id})"
                )
                await self.data.guild(guild).invites.set_raw(
                    invite, "roles", value=[x for x in roles_data if x not in to_remove]
                )

            # let's check if the request can be done before calling the API
            if not member.guild.me.guild_permissions.manage_roles:
                # manage_roles permission was removed
                # we disable the autorole to prevent more errors
                await self.data.guild(guild).enabled.set(False)
                log.warning(
                    'The "Manage roles" permission was lost. '
                    "RoleInvite is now disabled on this guild.\n"
                    f"Guild: {guild.name} (ID: {guild.id})"
                )
                return False
            to_remove = []
            for role in roles:
                if role.position >= guild.me.top_role.position:
                    # The role is above or equal to the bot's highest role in the hierarchy
                    # we're removing this role from the list to prevent more errors
                    to_remove.append(role)
            if to_remove != []:
                roles = [x for x in invites_data["roles"] if x not in [x.id for x in to_remove]]
                await self.data.guild(guild).invites.set_raw(invite, "roles", value=roles)
                roles_str = "; ".join([f"{x.name} (ID: {x.id})" for x in to_remove])
                log.warning(
                    f"Some roles linked to {invite} were removed because the role "
                    "hierarchy has changed and the roles are upper than mine.\n"
                    "To fix this, set my role above those and add them back.\n"
                    f"Roles removed: {roles_str}\n"
                    f"Guild: {guild.name} (ID: {guild.id})"
                )
            if invites_data["roles"] == []:
                # all roles were removed due to the checks
                del bot_invites[invite]
                await self.data.guild(guild).invites.set(bot_invites)
                log.warning(
                    f"Invite {invite} was removed due to missing roles.\n"
                    f"Guild: {guild.name} (ID: {guild.id})"
                )
                return False

            await member.add_roles(*roles, reason=_("Roleinvite autorole. ") + reason)
            return True

        guild = member.guild
        if not await self.data.guild(guild).enabled():
            return  # autorole disabled
        bot_invites = await self.data.guild(guild).invites()

        try:
            guild_invites = await guild.invites()
        except discord.errors.Forbidden:
            # manage guild permission removed
            # we disable the autorole to prevent more errors
            await self.data.guild(guild).enabled.set(False)
            log.warning(
                'The "Manage server" permission was lost. '
                "RoleInvite is now disabled on this guild.\n"
                f"Guild: {guild.name} (ID: {guild.id})"
            )
            return

        if "default" in bot_invites:
            if not await add_roles("default"):
                return

        for invite in bot_invites:

            if any(invite == x for x in ["default", "main"]):
                continue

            invite = discord.utils.get(guild_invites, url=invite)
            if not invite:
                del bot_invites[invite.url]
                await self.data.guild(guild).invites.set(bot_invites)
                log.warning(
                    f"Invite {invite} is expired and was removed.\n"
                    f"Guild: {guild.name} (ID: {guild.id})"
                )
            else:
                if invite.uses > bot_invites[invite.url]["uses"]:
                    # the invite has more uses than what we registered before
                    # this is the one used by the member

                    if not await add_roles(invite.url):
                        return

                    await self.data.guild(guild).invites.set_raw(
                        invite.url, "uses", value=invite.uses
                    )
                    return  # so it won't add "main" roles

        if "main" in bot_invites:
            if not await add_roles("main"):
                return

    # error handling
    def _set_context(self, data):
        self.sentry.client.extra_context(data)

    async def on_command_error(self, ctx, error):
        if not isinstance(error, commands.CommandInvokeError):
            return
        if not ctx.command.cog_name == self.__class__.__name__:
            # That error doesn't belong to the cog
            return
        context = {
            "command": {
                "invoked": f"{ctx.author} (ID: {ctx.author.id})",
                "command": f"{ctx.command.name} (cog: {ctx.cog})",
                "arguments": ctx.kwargs,
            }
        }
        if ctx.guild:
            context["guild"] = f"{ctx.guild.name} (ID: {ctx.guild.id})"
        self._set_context(context)
        self.sentry.disable_stdout()  # remove console output since Red already handle this
        log.error(
            f"Exception in command '{ctx.command.qualified_name}'.\n\n", exc_info=error.original
        )
        self.sentry.enable_stdout()  # re-enable console output for warnings
        self._set_context({})  # remove context for future logs

    def __unload(self):
        self.sentry.disable()
        log.handlers = []
