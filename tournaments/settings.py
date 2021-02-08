import discord
import logging
import re
import asyncio
import achallonge
import inspect

from datetime import datetime, timedelta
from typing import Optional

from redbot.core import commands
from redbot.core import checks
from redbot.core.i18n import Translator
from redbot.core.utils import menus
from redbot.core.utils.predicates import MessagePredicate
from redbot.core.utils.chat_formatting import humanize_timedelta, pagify
from redbot.core.commands.converter import TimedeltaConverter
from discord.ext.commands.view import StringView

from .abc import MixinMeta
from .objects import ChallongeTournament
from .utils import credentials_check, async_http_retry, mod_or_to, prompt_yes_or_no

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)

CHALLONGE_URL_RE = re.compile(r"(?:https?://challonge\.com/)(\S{1,2}/)?(?P<id>\S[^/]+)(/.*)?")


class ChallongeURLConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        result = CHALLONGE_URL_RE.match(argument)
        if result is None:
            raise commands.BadArgument(_("Invalid Challonge URL."))
        link_id = result.group("id")
        if not link_id:
            raise commands.BadArgument(_("Invalid Challonge URL."))
        return link_id


class ConfigSelector(commands.Converter):
    """
    Attempts to parse a config parameter inside the last argument, then return a cleaned string
    to another given converter. We're looking for a -c/--config flag.

    Basically we use discord.py's logic for parsing quoted strings, get what we're looking for,
    if it exists, then make a new string cleaned from this argument and pass this to the proper
    converter.

    Ex: "--config Thing Some other stuff" -> "Some other stuff" config=Thing
    "Here's more -c 'Another config' stuff !" -> "Here's more stuff !" config='Another config'
    """

    def __init__(self, converter=str):
        self.converter = converter
        self.config: str = None
        self.arg = None

    async def config_exists(self, ctx: commands.Context, name):
        data = ctx.bot.get_cog("Tournaments").data
        configs = await data.settings(ctx.guild.id).all()
        if name not in configs:
            raise commands.BadArgument(_("That config doesn't exist."))

    async def convert(self, ctx: commands.Context, argument: str):
        # we use dpy's tools for parsing quoted strings
        view = StringView(argument)
        config = None
        start, stop = 0, view.end
        while view.eof is False and config is None:
            view.skip_ws()
            next_word = view.get_word()
            if next_word == "-c" or next_word == "--config":
                start = view.previous
                view.skip_ws()
                config = view.get_quoted_word()
                await self.config_exists(ctx, config)
                self.config = config
                view.skip_ws()
                stop = view.index
                break
        if self.config is not None:
            argument = (argument[:start] + argument[stop:]).strip()
        param: inspect.Parameter = list(ctx.command.params.values())[-1]
        if not argument:
            if param.default is param.empty:
                raise commands.MissingRequiredArgument(param)
            else:
                self.arg = None if param.default.__class__ == self.__class__ else param.default
        else:
            self.arg = await ctx.command.do_conversion(ctx, self.converter, argument, param)
        return self


class Settings(MixinMeta):
    async def _verify_settings(self, ctx: commands.Context) -> str:
        """
        Check if all settings are correctly filled and the roles/channels still exist.
        """
        guild = ctx.guild
        not_set = {"channels": [], "roles": []}
        lost = {"channels": [], "roles": []}
        required_channels = ["to"]
        required_roles = ["participant"]
        data = await self.data.guild(guild).all()
        for name, channel_id in data["channels"].items():
            if name not in required_channels:
                continue
            if channel_id is None:
                not_set["channels"].append(name)
                continue
            channel = guild.get_channel(channel_id)
            if channel is None:
                lost["channels"].append(name)
        for name, role_id in data["roles"].items():
            if name not in required_roles:
                continue
            if role_id is None:
                not_set["roles"].append(name)
                continue
            role = guild.get_role(role_id)
            if role is None:
                lost["roles"].append(name)
        if all([not x for x in not_set.values()]) and all([not x for x in lost.values()]):
            return
        text = ""
        if not_set["channels"]:
            text += (
                _("The following channels are not configured:\n")
                + "".join([f"- {x}\n" for x in not_set["channels"]])
                + "\n"
            )
        if not_set["roles"]:
            text += (
                _("The following roles are not configured:\n")
                + "".join([f"- {x}\n" for x in not_set["roles"]])
                + "\n"
            )
        if lost["channels"]:
            text += (
                _("The following channels were lost:\n")
                + "".join([f"- {x}\n" for x in not_set["channels"]])
                + "\n"
            )
        if lost["roles"]:
            text += (
                _("The following roles were lost:\n")
                + "".join([f"- {x}\n" for x in not_set["roles"]])
                + "\n"
            )
        text += _(
            "Please configure the missing settings with the "
            "`{prefix}tset channels` and `{prefix}tset roles` commands."
        ).format(prefix=ctx.clean_prefix)
        return text

    @commands.group()
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def challongeset(self, ctx: commands.Context):
        """
        Configure the Challonge credentials for this server.

        You will have to use the same Challonge account as the one creating the tournaments.

        You need a username and an API key, obtainable in the user settings (Developer API).
        https://challonge.com/settings/developer

        Use `[p]challongeset username` and `[p]challongeset api`.

        :warning: **Careful, your API key is private ! Be sure to do not send this key to \
anyone**. The command `[p]challongeset api` will ask for your key in DM, no need to provide \
it directly.
        """
        pass

    @challongeset.command(name="api")
    async def challongeset_api(self, ctx: commands.Context, api_key: Optional[str]):
        """
        Set the Challonge API Key

        You can obtain this in your Challonge user settings, "Developer API" category.
        **https://challonge.com/settings/developer**

        :warning: **Careful, this key is secret !**
        """
        guild = ctx.guild
        if api_key is not None:
            if ctx.channel.permissions_for(guild.me).manage_messages:
                try:
                    await ctx.message.delete()
                except Exception:
                    pass
            await self.data.guild(guild).credentials.api.set(api_key)
            await ctx.send(_("The API key was successfully set."))
            return
        try:
            await ctx.author.send(
                _(
                    "Please send the Challonge API key here.\n"
                    'Go to this website, or go in your Challonge user settings, "Developer API" '
                    "category, to obtain your key.\n"
                    "**https://challonge.com/settings/developer**"
                )
            )
        except discord.HTTPException:
            await ctx.send(
                _(
                    "I can't send you a DM. Activate the DMs on this server, or use the command "
                    "like this: `{prefix}challongeset api <api key>`.\n"
                    "Pay attention to where you type this command, your key must stay private!"
                ).format(prefix=ctx.clean_prefix)
            )
            return
        pred = MessagePredicate.same_context(user=ctx.author)
        try:
            message = await self.bot.wait_for("message", check=pred, timeout=300)
        except asyncio.TimeoutError:
            await ctx.author.send(_("Request timed out."))
            return
        await self.data.guild(guild).credentials.api.set(message.content)
        await ctx.author.send(_("The API key was successfully set."))

    @challongeset.command(name="username")
    async def challongeset_username(self, ctx: commands.Context, username: str):
        """
        Set the Challonge username

        Example: `[p]challongeset username laggron42`
        """
        guild = ctx.guild
        await self.data.guild(guild).credentials.username.set(username)
        await ctx.send(_("The username was successfully set."))

    @commands.group(name="tset", aliases=["tournamentset"])
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def tournamentset(self, ctx: commands.Context):
        """
        Tournament settings on this server.

        Only administrators have access to those commands, not the T.O.
        """
        pass

    @tournamentset.group(name="config")
    async def tournamentset_config(self, ctx: commands.Context):
        """
        Manage multiple configurations for tournaments.
        """
        pass

    @tournamentset_config.command(name="add")
    async def tournamentset_config_add(self, ctx: commands.Context, name: str):
        """
        Add a new configuration to your settings.

        You will be able to set independent settings for this configuration.
        If there are spaces in the name, wrap it in quotes.

        If you use the name of a game, the bot will automatically switch to that config \
        for related tournaments.
        """
        all_configs = await self.data.settings(ctx.guild.id).all()
        if name in all_configs:
            await ctx.send(_("That name is already used."))
            return
        # we set something useless so it registers the new entry
        await self.data.settings(ctx.guild.id, name).delay.set(None)
        await ctx.send(
            _(
                "New configuration {name} added.\n"
                "If you want to define settings for that config, "
                "add `--config {name}` at the end of your command.\n\n"
                "Example: `{prefix}tset channels ruleset #my-channel --config {name}`"
            )
        )

    @tournamentset_config.command(name="remove")
    async def tournamentset_config_remove(self, ctx: commands.Context, name: str):
        """
        Remove a configuration.

        If there are spaces in the name, wrap it in quotes.
        """
        async with self.data.settings(ctx.guild.id).all() as configs:
            if name not in configs:
                await ctx.send(_("That name doesn't exist."))
                return
            del configs[name]
        await ctx.send(_("The config was successfully deleted."))

    @tournamentset_config.command(name="list")
    async def tournamentset_config_list(self, ctx: commands.Context):
        """
        List all existing configs.
        """
        all_configs = await self.data.settings(ctx.guild.id).all()
        if all_configs is None:
            await ctx.send(_("Nothing setup yet!"))
            return
        text = _("__List of configs:__\n\n")
        for config in all_configs:
            text += f"- {config}\n"
        for page in pagify(text):
            await ctx.send(page)

    @tournamentset.group(name="channels")
    async def tournamentset_channels(self, ctx: commands.Context):
        """
        Channels settings.
        """
        pass

    @tournamentset_channels.command(name="announcements")
    async def tournamentset_channels_announcements(
        self,
        ctx: commands.Context,
        *,
        channel: ConfigSelector(discord.TextChannel) = ConfigSelector(),
    ):
        """
        Set the announcements channel.

        The following announcements will be sent there :
        - Start of registration
        - Tournament launch
        - Tournament end
        """
        config = channel.config
        channel = channel.arg
        guild = ctx.guild
        if channel is None:
            await self.data.settings(guild.id, config).channels.announcements.set(None)
            await ctx.send(_("The channel was successfully removed."))
            return
        if not channel.permissions_for(guild.me).read_messages:
            await ctx.send(_("I don't have the permission to read messages in this channel."))
        elif not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("I don't have the permission to send messages in this channel."))
        else:
            await self.data.settings(guild.id, config).channels.announcements.set(channel.id)
            await ctx.send(_("The channel was successfully set."))

    @tournamentset_channels.command(name="checkin")
    async def tournamentset_channels_checkin(
        self,
        ctx: commands.Context,
        *,
        channel: ConfigSelector(discord.TextChannel) = ConfigSelector(),
    ):
        """
        Set the check-in channel.

        The start of the check-in will be announced there, and participants will have to enter a \
command to confirm their registration.

        Don't set this to keep the command channel unrestricted (can be typed anywhere).
        """
        guild = ctx.guild
        config = channel.config
        channel = channel.arg
        if channel is None:
            await self.data.settings(guild.id, config).channels.checkin.set(None)
            await ctx.send(
                _(
                    "The check-in will now be available in any channel. Careful, "
                    "Red's permissions system still applies."
                )
            )
            return
        if not channel.permissions_for(guild.me).read_messages:
            await ctx.send(_("I don't have the permission to read messages in this channel."))
        elif not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("I don't have the permission to send messages in this channel."))
        else:
            await self.data.settings(guild.id, config).channels.checkin.set(channel.id)
            await ctx.send(_("The channel was successfully set."))

    @tournamentset_channels.command(name="register")
    async def tournamentset_channels_register(
        self,
        ctx: commands.Context,
        *,
        channel: ConfigSelector(discord.TextChannel) = ConfigSelector(),
    ):
        """
        Set the registration channel.

        The start of the registration will be announced there, and participants will have to \
enter a command to register or unregister.

        Don't set this to keep the command channel unrestricted (can be typed anywhere).
        """
        guild = ctx.guild
        config = channel.config
        channel = channel.arg
        if channel is None:
            await self.data.settings(guild.id, config).channels.register.set(None)
            await ctx.send(
                _(
                    "The registration will now be available in any channel. Careful, "
                    "Red's permissions system still applies."
                )
            )
            return
        if not channel.permissions_for(guild.me).read_messages:
            await ctx.send(_("I don't have the permission to read messages in this channel."))
        elif not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("I don't have the permission to send messages in this channel."))
        else:
            await self.data.settings(guild.id, config).channels.register.set(channel.id)
            await ctx.send(_("The channel was successfully set."))

    @tournamentset_channels.command(name="scores")
    async def tournamentset_channels_scores(
        self,
        ctx: commands.Context,
        *,
        channel: ConfigSelector(discord.TextChannel) = ConfigSelector(),
    ):
        """
        Set the score entry channel.

        Members will have to enter a command there to register their score.

        Don't set this to keep the command channel unrestricted (can be typed anywhere).
        """
        guild = ctx.guild
        config = channel.config
        channel = channel.arg
        if channel is None:
            await self.data.settings(guild.id, config).channels.scores.set(None)
            await ctx.send(
                _(
                    "The score entry will now be available in any channel. Careful, "
                    "Red's permissions system still applies."
                )
            )
            return
        if not channel.permissions_for(guild.me).read_messages:
            await ctx.send(_("I don't have the permission to read messages in this channel."))
        elif not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("I don't have the permission to send messages in this channel."))
        else:
            await self.data.settings(guild.id, config).channels.scores.set(channel.id)
            await ctx.send(_("The channel was successfully set."))

    @tournamentset_channels.command(name="queue")
    async def tournamentset_channels_queue(
        self,
        ctx: commands.Context,
        *,
        channel: ConfigSelector(discord.TextChannel) = ConfigSelector(),
    ):
        """
        Define the channel for announcing new sets.
        """
        guild = ctx.guild
        config = channel.config
        channel = channel.arg
        if channel is None:
            await self.data.settings(guild.id, config).channels.queue.set(None)
            await ctx.send(_("The channel was successfully removed."))
            return
        if not channel.permissions_for(guild.me).read_messages:
            await ctx.send(_("I don't have the permission to read messages in this channel."))
        elif not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("I don't have the permission to send messages in this channel."))
        else:
            await self.data.settings(guild.id, config).channels.queue.set(channel.id)
            await ctx.send(_("The channel was successfully set."))

    @tournamentset_channels.command(name="ruleset")
    async def tournamentset_channels_ruleset(
        self,
        ctx: commands.Context,
        *,
        channel: ConfigSelector(discord.TextChannel) = ConfigSelector(),
    ):
        """
        Set the channel of the rules for your tournament.

        Example: `[p]tset ruleset #tournament-rules`
        """
        guild = ctx.guild
        config = channel.config
        channel = channel.arg
        if channel is None:
            await self.data.settings(guild.id, config).channels.ruleset.set(None)
            await ctx.send(_("The channel was successfully removed."))
        else:
            await self.data.settings(guild.id, config).channels.ruleset.set(channel.arg.id)
            await ctx.send(_("The channel was successfully set."))

    @tournamentset_channels.command(name="stream")
    async def tournamentset_channels_stream(
        self,
        ctx: commands.Context,
        *,
        channel: ConfigSelector(discord.TextChannel) = ConfigSelector(),
    ):
        """
        Set the stream announcement channel.
        """
        guild = ctx.guild
        config = channel.config
        channel = channel.arg
        if channel is None:
            await self.data.settings(guild.id, config).channels.stream.set(None)
            await ctx.send(_("The channel was successfully removed."))
        elif not channel.permissions_for(guild.me).read_messages:
            await ctx.send(_("I don't have the permission to read messages in this channel."))
        elif not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("I don't have the permission to send messages in this channel."))
        else:
            await self.data.settings(guild.id, config).channels.stream.set(channel.id)
            await ctx.send(_("The channel was successfully set."))

    @tournamentset_channels.command(name="to")
    async def tournamentset_channels_to(
        self, ctx: commands.Context, *, channel: ConfigSelector(discord.TextChannel)
    ):
        """
        Set the T.O. channel.

        It is recommanded to keep this channel closed to T.O.s only.
        The following announcements will be sent there:
        - Lag tests requested with the `[p]lag` command
        - Sets slowing down the bracket
        - Automatic DQs because of inactivity

        Careful, this channel does not grant additional permissions to people with write access.
        The Red permissions system will define if someone has access to the commands.
        """
        guild = ctx.guild
        config = channel.config
        channel = channel.arg
        if not channel.permissions_for(guild.me).read_messages:
            await ctx.send(_("I don't have the permission to read messages in this channel."))
        elif not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("I don't have the permission to send messages in this channel."))
        else:
            await self.data.settings(guild.id, config).channels.to.set(channel.id)
            await ctx.send(_("The channel was successfully set."))

    @tournamentset_channels.command(name="vipregister", hidden=True)
    async def tournamentset_channels_vipregister(
        self,
        ctx: commands.Context,
        *,
        channel: ConfigSelector(discord.TextChannel) = ConfigSelector(),
    ):
        """
        Set the VIP registration channel.

        This is a hidden setting that defines a channel where anyone able to send messages \
there is able to use `[p]in` as soon as the tournament is setup, regardless of the current state \
of the other registrations channel.
        """
        guild = ctx.guild
        config = channel.config
        channel = channel.arg
        if channel is None:
            await self.data.settings(guild.id, config).channels.vipregister.set(None)
            await ctx.send(_("VIP registration channel removed."))
            return
        if not channel.permissions_for(guild.me).read_messages:
            await ctx.send(_("I don't have the permission to read messages in this channel."))
        elif not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("I don't have the permission to send messages in this channel."))
        else:
            await self.data.settings(guild.id, config).channels.vipregister.set(channel.id)
            await ctx.send(_("The channel was successfully set."))

    @tournamentset_channels.command(name="category")
    async def tournamentset_channels_category(
        self,
        ctx: commands.Context,
        *,
        category: ConfigSelector(discord.CategoryChannel) = ConfigSelector(),
    ):
        """
        Set the category of your tournaments channels.

        This category will be used for the position of the categories containing the sets channel.
        One or more categories will be created below the category defined with this command.

        You can either give the complete name of the category, or its ID.
        """
        guild = ctx.guild
        config = category.config
        category = category.arg
        if category is None:
            await self.data.settings(guild.id, config).channels.category.set(None)
            await ctx.send(_("The category was successfully removed."))
        else:
            await self.data.settings(guild.id, config).channels.category.set(category.id)
            await ctx.send(_("The category was successfully set."))

    @tournamentset.group(name="roles")
    async def tournamentset_roles(self, ctx: commands.Context):
        """
        Roles settings.

        Give the complete name of the role, or its ID.

        The T.O. role is optional if your T.O. are also moderators of this server, configured \
with the `[p]set addadminrole` and `[p]set addmodrole` commands.
        """
        pass

    @tournamentset_roles.command(name="participant")
    async def tournamentset_roles_participant(
        self, ctx: commands.Context, *, role: ConfigSelector(discord.Role)
    ):
        """
        Set the participant role in the tournament.

        This role will be assigned to members as soon as they register, and removed once the \
tournament ends.
        """
        guild = ctx.guild
        if role.arg.position >= guild.me.top_role.position:
            await ctx.send(_("This role is too high. Place it below my main role."))
            return
        await self.data.settings(guild.id, role.config).roles.participant.set(role.id)
        await ctx.send(_("The role was successfully set."))

    @tournamentset_roles.command(name="player")
    async def tournamentset_roles_player(
        self, ctx: commands.Context, *, role: ConfigSelector(discord.Role) = ConfigSelector()
    ):
        """
        Define the role for players that could register to tournaments.

        This role will be used for:
        - Setting the permissions of the registration channel when they are opened
        - Mention players when opening the registration

        Give the entire name of the role or its ID.

        If this role isn't set, the @everyone role is used by default (without pinging).
        Use this command without role to reset it to its initial state.
        """
        guild = ctx.guild
        if role.arg is None:
            await self.data.settings(guild.id, role.config).role.set(None)
            await ctx.send(_("The role was reset to its initial state."))
        else:
            await self.data.settings(guild.id, role.config).role.set(role.arg.id)
            await ctx.send(_("The role was successfully set."))

    @tournamentset_roles.command(name="streamer")
    async def tournamentset_roles_streamer(
        self, ctx: commands.Context, *, role: ConfigSelector(discord.Role) = ConfigSelector()
    ):
        """
        Set the streamer role.

        This role will give access to the sets channels, and the streamer commands.
        """
        guild = ctx.guild
        if role.arg is None:
            await self.data.settings(guild.id, role.config).roles.streamer.set(None)
            await ctx.send(_("The role was reset to its initial state."))
        else:
            await self.data.settings(guild.id, role.config).roles.streamer.set(role.arg.id)
            await ctx.send(_("The role was successfully set."))

    @tournamentset_roles.command(name="tester")
    async def tournamentset_roles_tester(self, ctx: commands.Context, *, role: discord.Role):
        """
        Set the tester role.
        """
        guild = ctx.guild
        if role.position >= guild.me.top_role.position:
            await ctx.send(_("This role is too high. Place it below my main role."))
            return
        await self.data.guild(guild).roles.tester.set(role.id)
        await ctx.send(_("The role was successfully set."))

    @tournamentset_roles.command(name="to")
    async def tournamentset_roles_to(
        self, ctx: commands.Context, *, role: ConfigSelector(discord.Role)
    ):
        """
        Set the T.O. role (Tournament Organizer).

        This role gives access to the tournament commands (except `[p]challongeset` and \
`[p]tset`).

        :warning: **Use this setting only if you need to separate moderators from T.O.**
        Otherwise, it is strongly recommanded to use the Red commands: `[p]set addadminrole` and \
`[p]set addmodrole`. This will adapt the permissions of all commands from this bot to your \
moderators and admins.
        """
        guild = ctx.guild
        config = role.config
        role = role.arg
        if role.permissions.kick_members or role.permissions.manage_roles:
            # we consider this role is a mod role
            result = await prompt_yes_or_no(
                ctx,
                _(
                    ":warning: This role seems to have moderator or administrator permissions.\n\n"
                    "It is strongly recommanded to use the Red permissions system with `{prefix}"
                    "set addadminrole` and `{prefix}set addmodrole` to configure your moderator "
                    "and administrator roles, adapting the permissions of all commands of this "
                    "bot to your staff.\n"
                    "This setting is recommanded for T.O.s that aren't moderators.\n"
                    "Do you want to continue?"
                ).format(prefix=ctx.clean_prefix),
                timeout=60,
                delete_after=False,
            )
            if result is False:
                return
        if role.position >= guild.me.top_role.position:
            await ctx.send(_("This role is too high. Place it below my main role."))
            return
        await self.data.settings(guild.id, config).roles.to.set(role.id)
        await ctx.send(_("The role was successfully set."))

    @tournamentset.command(name="baninfo")
    async def tournamentset_baninfo(
        self, ctx: commands.Context, *, text: ConfigSelector = ConfigSelector()
    ):
        """
        Define infos on the bans (ex: 2-3-1)

        Those informations will be given when opening a set, and do not require a specific format.
        Use this command without parameter to reset it to its initial state.

        Example : If the value is set to "2-3-1", here is what will be shown:
        ":game_die: **[player 1]** was picked to begin the bans *(2-3-1)*"
        """
        guild = ctx.guild
        config = text.config
        text = text.arg
        if text is not None and len(text) > 256:
            await ctx.send(
                _(
                    "This text is too long (>256 characters). "
                    "Type `{prefix}help tset games baninfo` for details."
                ).format(prefix=ctx.clean_prefix)
            )
            return
        await self.data.settings(guild.id, config).baninfo.set(text)
        if text is not None:
            await ctx.send(_("The text was successfully set."))
        else:
            await ctx.send(_("The text was successfully deleted."))

    @tournamentset.command(name="stages")
    async def tournamentset_stages(
        self, ctx: commands.Context, *, stages: ConfigSelector = ConfigSelector()
    ):
        """
        Define the list of authorized stages.

        Give the stages one after another, separated by a comma.

        Example : `[p]tset stages Battlefield, Final Destination, Pokémon Stadium 2`
        """
        guild = ctx.guild
        if stages.arg is None:
            await self.data.settings(guild.id, stages.config).stages.set(None)
            await ctx.send(_("The stage list was deleted."))
            return
        selection = [x.strip() for x in stages.arg.split(",")]
        await self.data.settings(guild.id, stages.config).stages.set(selection)
        await ctx.send(_("The stages were successfully set."))

    @tournamentset.command(name="counters")
    async def tournamentset_counters(
        self, ctx: commands.Context, *, counters: ConfigSelector = ConfigSelector()
    ):
        """
        Define the list of authorized counter stages.

        Give the stages one after another, separated by a comma.

        Example : `[p]tset counters Battlefield, Final Destination, Pokémon Stadium 2`
        """
        guild = ctx.guild
        if counters.arg is None:
            await self.data.settings(guild.id, counters.config).stages.set(None)
            await ctx.send(_("The stage list was deleted."))
            return
        selection = [x.strip() for x in counters.arg.split(",")]
        await self.data.settings(guild.id, counters.config).counterpicks.set(selection)
        await ctx.send(_("The stages were successfully set."))

    @tournamentset.command(name="ranking")
    async def tournamentset_ranking(
        self,
        ctx: commands.Context,
        league_name: Optional[str],
        league_id: Optional[str],
        *,
        config: ConfigSelector = ConfigSelector(),
    ):
        """
        Define Braacket ranking informations for a game.

        This will be used for seeding.
        You need to give the league's name, followed by its ID.

        Omit both values to reset those informations.
        """
        guild = ctx.guild
        if league_name is None and league_id is None:
            await self.data.settings(guild.id, config.config).ranking.set(
                {"league_name": None, "league_id": None}
            )
            await ctx.send(_("Ranking informations deleted."))
        elif league_name is None or league_id is None:
            # only one value provided
            await ctx.send_help()
        else:
            await self.data.settings(guild.id, config.config).ranking.set(
                {"league_name": league_name, "league_id": league_id}
            )
            await ctx.send(_("The ranking informations were successfully set."))

    @tournamentset.command(name="delay")
    async def tournamentset_delay(
        self,
        ctx: commands.Context,
        *,
        delay: ConfigSelector(TimedeltaConverter),
    ):
        """
        Set the delay before automatically DQing an inactive player.

        Example formats: `30s`, `5m`, `1h`, `10m30s`...
        Set a time of `0s` to disable
        """
        guild = ctx.guild
        config = delay.config
        delay: timedelta = config.arg
        if delay.total_seconds() < 0:
            await ctx.send(_("This can't be negative!"))
            return
        await self.data.settings(guild.id, config).delay.set(delay.total_seconds())
        if delay.total_seconds() == 0:
            await ctx.send(_("Automatic DQ is now disabled."))
        else:
            await ctx.send(
                _(
                    "Done. If a player doesn't respond in his channel {delay} "
                    "after its creation, he will automatically be disqualified."
                ).format(delay=humanize_timedelta(delay))
            )

    @tournamentset.command(name="warntime")
    async def tournamentset_warntime(
        self,
        ctx: commands.Context,
        time_until_warn_in_channel: TimedeltaConverter,
        time_until_to_warn: TimedeltaConverter,
        mode: ConfigSelector = ConfigSelector(),
    ):
        """
        Set the time until warning for too long matches.

        You set two delays: the delay until warning the players about the length of their match, \
then the delay until warning the T.O.s about this match.
        The second delay is in addition to the first one.
        You also have to set the mode, either "bo3" or "bo5". Defaults to "bo3" if not set.
        Put `0s` to one of the values (or both) to disable that warn.

        Examples:
        `[p]tset warntime 30m 10m`: will warn the players 30 minutes after the start of their \
match, then warn the T.O.s 10 minutes after the first warn (so 40 minutes in total).
        `[p]tset warntime 1h 10m bo5`: same as above but for bo5 matches instead, and with a one \
hour limit instead of 30 minutes.
        """
        guild = ctx.guild
        config = mode.config
        mode = mode.arg or "bo3"
        if mode not in ("bo3", "bo5"):
            await ctx.send(_('The mode must either be "bo3" or "bo5".'))
            return
        await self.data.settings(guild.id, config).time_until_warn.set_raw(
            mode,
            value=(time_until_warn_in_channel.total_seconds(), time_until_to_warn.total_seconds()),
        )
        await ctx.send(_("New values have been set."))

    @tournamentset.command(name="register")
    async def tournamentset_register(
        self,
        ctx: commands.Context,
        opening: TimedeltaConverter,
        *,
        closing: ConfigSelector(TimedeltaConverter),
    ):
        """
        Set the opening and closing time of the registration.

        You need to give the delay before the start of the tournament for each value.
        First the opening hour, then the closing hour.

        Date and time of the tournament's start is the one defined on Challonge.

        To disable the automatic opening/closing of the registration, give 0s for its \
corresponding value.

        Example: `[p]tset register 2d 10m` = Opening of the registration 2 days \
before the opening of the tournament, then closing 10 minutes before.
        """
        guild = ctx.guild
        config = closing.config
        closing: timedelta = closing.arg
        if (
            closing.total_seconds() != 0
            and opening.total_seconds() != 0
            and closing.total_seconds() >= opening.total_seconds()
        ):
            await ctx.send(_("Opening must occur before closing time."))
            return
        async with self.data.settings(guild.id, config).register() as register:
            if (
                opening.total_seconds() != 0
                and register["second_opening"] >= opening.total_seconds()
            ):
                await ctx.send(
                    _("Opening must occur before second attempt (two-stage registrations).")
                )
                return
            register["opening"] = opening.total_seconds()
            register["closing"] = closing.total_seconds()
        if opening.total_seconds() == 0 and closing.total_seconds() == 0:
            await ctx.send(_("Automatic registration is now disabled."))
        else:
            await ctx.send(
                _(
                    "Registration will now open {opening} before the start and close "
                    "{closing} before the start of the tournament."
                ).format(opening=humanize_timedelta(opening), closing=humanize_timedelta(closing))
            )

    @tournamentset.command(name="autostopregister")
    async def tournamentset_autostopregister(
        self, ctx: commands.Context, enable: ConfigSelector(bool) = ConfigSelector()
    ):
        """
        End registration when the limit is reached.

        If this is enabled, registrations will be closed as soon as the tournament is completed.
        This is useful with two-stage registrations (see `[p]help tset twostageregister`).
        """
        guild = ctx.guild
        current = await self.data.settings(guild.id, enable.config).autostop_register()
        if enable.arg is None:
            await ctx.send(
                _("The bot currently ends registrations automatically. ")
                if current
                else _("The bot currently doesn't end registrations automatically. ")
                + _(
                    "If you want to change this, type `{prefix}tset autostopregister {opposite}`."
                ).format(prefix=ctx.clean_prefix, opposite=not current)
            )
        elif enable.arg is True:
            await self.data.settings(guild.id, enable.config).autostop_register.set(True)
            await ctx.send(
                _("Done. Registrations will now end as soon as your participants cap is reached.")
            )
        else:
            await self.data.settings(guild.id, enable.config).autostop_register.set(False)
            await ctx.send(
                _(
                    "Done. Registrations will continue regardless of the limit (someone still "
                    "can't register above the limit, but the channel and commands remains open)."
                )
            )

    @tournamentset.command(name="twostageregister")
    async def tournamentset_twostageregister(
        self, ctx: commands.Context, second_opening: ConfigSelector(TimedeltaConverter)
    ):
        """
        Give a second opening attempt hour for registrations.

        This must be inferior to the base opening hour you have set.
        Basically, the bot will attempt opening registrations a second time. If they're already \
opened and ongoing, nothing happens.

        Combine this with the autostop setting (see `[p]help tfix autostopregister`), and you can \
have registrations that can look like this:
        - Registrations opened until the cap is reached, then closed
        - Check-in is done, unchecked participants are removed
        - **Set up last minute registrations** where members don't have to check and fill your \
bracket.

        Provide the duration before tournament start for this second opening (ex: "1h", "15m").
        Set 0s to disable.
        """
        guild = ctx.guild
        config = second_opening.config
        second_opening = second_opening.arg.total_seconds()
        async with self.data.settings(guild.id, config) as register:
            if second_opening != 0 and second_opening >= register["opening"]:
                await ctx.send(_("Second opening must occur after first opening."))
                return
            if second_opening != 0 and second_opening <= register["closing"]:
                await ctx.send(_("Second opening must before closing."))
                return
            register["second_opening"] = second_opening
        if second_opening == 0:
            await ctx.send(_("Two stage registration is now disabled."))
        else:
            await ctx.send(_("Two stage registration is now enabled with your second opening."))

    @tournamentset.command(name="checkin")
    async def tournamentset_checkin(
        self,
        ctx: commands.Context,
        opening: TimedeltaConverter,
        *,
        closing: ConfigSelector(TimedeltaConverter),
    ):
        """
        Set the opening and closing time of the check-in.

        You need to give the delay before the start of the tournament for each value.
        First the opening hour, then the closing hour.

        Date and time of the tournament's start is the one defined on Challonge.

        To disable the check-in, give 0s for both values.

        Example: `[p]tset checkin 1h 15m` = Opening of the check-in one hour before \
the start of the tournament, then closing 15 minutes before.
        """
        guild = ctx.guild
        config = closing.config
        closing = closing.arg
        await self.data.settings(guild.id, config).checkin.set(
            {"opening": opening.total_seconds(), "closing": closing.total_seconds()}
        )
        if opening.total_seconds() == 0 and closing.total_seconds() == 0:
            await ctx.send(_("The check-in is now disabled."))
        else:
            await ctx.send(
                _(
                    "Check-in will now open {opening} before the start and close "
                    "{closing} before the start of the tournament."
                ).format(opening=humanize_timedelta(opening), closing=humanize_timedelta(closing))
            )

    @tournamentset.command(name="startbo5")
    async def tournamentset_startbo5(self, ctx: commands.Context, level: ConfigSelector(int)):
        """
        Define when the sets switch to Best of 5 format (BO5)

        You need to enter a number to define the level:
        0 = top 7
        1 = top 5
        2 = top 3 (winner + loser final)
        -1 = top 12...
        """
        guild = ctx.guild
        await self.data.settings(guild.id, level.config).start_bo5.set(level.arg)
        await ctx.send(_("The level was successfully set."))

    @tournamentset.command(name="settings")
    async def tournamentset_settings(
        self, ctx: commands.Context, *, config: ConfigSelector = ConfigSelector()
    ):
        """
        Show all settings for this server.

        If you want to display the settings for a specific configuration, use `[p]tset settings \
--config "Your config name"`
        """
        guild = ctx.guild
        if not ctx.channel.permissions_for(guild.me).embed_links:
            await ctx.send(_("I need the `Embed links` permission in this channel."))
            return
        data = await self._get_settings(ctx.guild.id, config.config)
        if config.config is not None:
            config = _('Displaying configuration "{name}".').format(name=config.config)
        else:
            config = _("Displaying the default configuration.")

        def get_warn_time(mode):
            _data = data["time_until_warn"][mode]
            text = "__{mode}__\n".format(mode=mode.upper())
            if not _data[0]:
                return text + _("Disabled")
            text += _("First warn: after {} minutes\n").format(_data[0])
            if _data[1]:
                text += _("T.O. warn: {} minutes after first warn").format(_data[1])
            else:
                text += _("T.O. warn: disabled")
            return text

        no_configs = len(await self.data.settings(guild.id).all()) - 1
        credentials = await self.data.guild(guild).credentials.all()
        if credentials["api"] and credentials["username"]:
            challonge = _(
                "Configured account: [{user}](https://challonge.com/users/{user})"
            ).format(user=credentials["username"])
        else:
            challonge = _("Not configured. Use `{prefix}challongeset`").format(
                prefix=ctx.clean_prefix
            )
        delay = data["delay"]
        start_bo5 = data["start_bo5"]
        if data["register"]["opening"] != 0:
            register_start = _("{time} minutes before the start of the tournament.").format(
                time=data["register"]["opening"]
            )
        else:
            register_start = _("manual.")
        if data["register"]["second_opening"] != 0:
            register_secondstart = _("{time} minutes before the start of the tournament.").format(
                time=data["register"]["second_opening"]
            )
        else:
            register_secondstart = _("disabled.")
        if data["register"]["closing"] != 0:
            register_end = _("{time} minutes before the start of the tournament.").format(
                time=data["register"]["closing"]
            )
        else:
            register_end = _("manual.")
        if data["checkin"]["opening"] != 0:
            checkin_start = _("{time} minutes before the start of the tournament.").format(
                time=data["checkin"]["opening"]
            )
        else:
            checkin_start = _("manual.")
        if data["checkin"]["closing"] != 0:
            checkin_end = _("{time} minutes before the start of the tournament.").format(
                time=data["checkin"]["closing"]
            )
        else:
            checkin_end = _("Manual.")
        autostop = _("enabled") if data["autostop_register"] else _("disabled")
        channels = {}
        for k, v in data["channels"].items():
            if not v:
                channels[k] = _("Not set")
                continue
            channel = guild.get_channel(v)
            if not channel:
                channels[k] = _("Lost")
            else:
                if isinstance(channel, discord.TextChannel):
                    channels[k] = channel.mention
                else:
                    # category
                    channels[k] = channel.name
        channels = _(
            "Category : {category}\n\n"
            "Announcements : {announcements}\n"
            "Ruleset : {ruleset}\n"
            "Registration : {register}\n"
            "Check-in : {checkin}\n"
            "Queue : {queue}\n"
            "Scores : {scores}\n"
            "Stream : {stream}\n"
            "T.O. : {to}\n"
            "VIP Registration : {vipregister}"
        ).format(**channels)
        roles = {}
        for k, v in data["roles"].items():
            if not v:
                roles[k] = _("Not set")
                continue
            role = guild.get_role(v)
            if not role:
                roles[k] = _("Lost")
            else:
                roles[k] = role.name
        roles = _(
            "Participant : {participant}\n"
            "Player : {player}\n"
            "Streamer : {streamer}\n"
            "T.O. : {to}\n"
            "Tester : {tester}\n"
        ).format(**roles)
        baninfo = data["baninfo"] if data["baninfo"] else _("Not set.")
        stages = "\n".join([f"- {x}" for x in data["stages"]])
        counterpicks = "\n".join([f"- {x}" for x in data["counterpicks"]])
        if data["ranking"]["league_name"] and data["ranking"]["league_id"]:
            ranking = _("Name: {name}\nID: {id}").format(
                name=data["ranking"]["league_name"], id=data["ranking"]["league_id"]
            )
        else:
            ranking = _("Not set.")
        embeds = []
        embed = discord.Embed(title=_("Settings • Page 1/3"))
        embed.set_footer(text=config)
        embed.description = _(
            "Challonge credentials : {challonge}\n"
            "Number of configs : {configs}\n"
            "Delay before DQ : {delay} minutes\n"
            "Begin of BO5 : {bo5} *(see `{prefix}help tset startbo5`)*"
        ).format(
            challonge=challonge,
            configs=no_configs,
            delay=delay,
            bo5=start_bo5,
            prefix=ctx.clean_prefix,
        )
        embed.add_field(
            name=_("Registration"),
            value=_(
                "Opening : {opening}\n"
                "Second opening : {secondopening}\n"
                "Closing : {closing}\n"
                "Auto-stop : {stop}"
            ).format(
                opening=register_start,
                secondopening=register_secondstart,
                closing=register_end,
                stop=autostop,
            ),
        )
        embed.add_field(
            name=_("Check-in"),
            value=_("Opening : {opening}\nClosing : {closing}").format(
                opening=checkin_start, closing=checkin_end
            ),
        )
        if any(x[0] for x in data["time_until_warn"].values()):
            warn_time = get_warn_time("bo3") + "\n\n" + get_warn_time("bo5")
        else:
            warn_time = _("Fully disabled.")
        embed.add_field(
            name=_("Warn long matches"),
            value=warn_time,
            inline=False,
        )
        embeds.append(embed)
        embed = discord.Embed(title=_("Settings • Page 2/3"))
        embed.set_footer(text=config)
        embed.add_field(name=_("Channels"), value=channels)
        embed.add_field(name=_("Roles"), value=roles)
        embeds.append(embed)
        embed = discord.Embed(title=_("Settings • Page 3/3"))
        embed.set_footer(text=config)
        embed.description = _("Ban info: {baninfo}").format(baninfo=baninfo)
        if stages:
            embed.add_field(name=_("Stages"), value=stages)
        if counterpicks:
            embed.add_field(name=_("Counterpicks"), value=counterpicks)
        embed.add_field(name=_("Ranking league"), value=ranking)
        embeds.append(embed)
        await menus.menu(ctx, embeds, controls=menus.DEFAULT_CONTROLS)

    @credentials_check
    @mod_or_to()
    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 30, commands.BucketType.guild)
    async def setup(self, ctx: commands.Context, *, url: ConfigSelector(ChallongeURLConverter)):
        """
        Setup the next tournament for this server.

        You must give a valid Challonge URL.
        """
        guild = ctx.guild
        message = await self._verify_settings(ctx)
        if message:
            await ctx.send(message)
            return
        del message
        tournament = self.tournaments.get(guild.id)
        if tournament is not None:
            await ctx.send(
                _(
                    "A tournament seems to be already configured. If this tournament is done, "
                    "use `{prefix}end` to correctly end the tournament. Else, use `{prefix}reset` "
                    "to clear the tournament from the bot."
                ).format(prefix=ctx.clean_prefix)
            )
            return
        credentials = await self.data.guild(guild).credentials.all()
        credentials["login"] = credentials.pop("username")
        credentials["password"] = credentials.pop("api")
        error_mapping = {
            "401": _(
                ":information_source: A 401 error at this step means your Challonge username "
                "and/or API key are invalid. Please configure new ones with "
                "the `{prefix}challongeset` command while making sure everything is correct."
            ).format(prefix=ctx.clean_prefix),
            "404": _(
                ":information_source: A 404 error either means the link you've provided is "
                "invalid, or the tournament is hosted by a community instead of a user.\n"
                "For obscure reasons, the Challonge API does not support communitites, so if "
                "this is the case, move the tournament to a standalone user (Settings > Basic "
                "info > Host).\nYou will be able to move the tournament back "
                "to your community once it is ended."
            ),
        }
        config = url.config
        url = url.arg
        async with ctx.typing():
            try:
                data = await async_http_retry(
                    achallonge.tournaments.show(url, credentials=credentials)
                )
            except achallonge.ChallongeException as e:
                error = error_mapping.get(e.args[0].split()[0])
                if error:
                    await ctx.send(
                        _(
                            "__Error from Challonge: {error}__\n{error_msg}\n\n"
                            "If this problem persists, contact T.O.s or an admin of the bot."
                        ).format(error=e.args[0], error_msg=error, prefix=ctx.clean_prefix)
                    )
                    return
                raise
        if data is None:
            await ctx.send(_("Tournament not found. Check your URL."))
            return
        if data["start_at"] is None:
            await ctx.send(_("You need to define a start date and time on your tournament."))
            return
        if config is None:
            configs = await self.data.settings(guild.id).all()
            if data["game_name"] and data["game_name"].title() in configs:
                config = data["game_name"]
            del configs
        config_data = await self._get_settings(guild.id, config)
        tournament: ChallongeTournament = ChallongeTournament.build_from_api(
            bot=self.bot,
            guild=guild,
            config=self.data,
            prefix=ctx.clean_prefix,
            cog_version=self.__version__,
            data=data,
            config_data=config_data,
        )

        def format_datetime(datetime: Optional[datetime], name_to_check: Optional[str]):
            if name_to_check and name_to_check in tournament.ignored_events:
                return _("Skipped")
            elif datetime:
                return datetime.strftime("%a %d %b %H:%M")
            else:
                return _("Manual")

        now = datetime.now(tournament.tz)
        if now > tournament.tournament_start:
            await ctx.send(
                _("The tournament's date has already passed: ")
                + format_datetime(tournament.tournament_start)
            )
            return
        try:
            tournament._valid_dates()
        except RuntimeError as e:
            text = _("There are conflicts with dates!\n\n") + e.args[0] + "\n"
            for name, time, identifier in e.args[1]:
                text += f"{name}: {format_datetime(time)}\n"
                tournament.ignored_events.append(identifier)
            text += _("\nWould you like to continue and skip these events?")
            if not await prompt_yes_or_no(ctx, text, delete_after=False):
                return
        embed = discord.Embed(title=f"{tournament.name} • *{tournament.game}*")
        embed.url = tournament.url
        if tournament.limit is not None:
            embed.description = _("Tournament of {limit} players.").format(limit=tournament.limit)
        else:
            embed.description = _("Tournament without player limit.")
        embed.description += _("\nTournament start: {date}").format(
            date=format_datetime(tournament.tournament_start)
        )
        embed.description += _("Time zone: {tz}").format(tz=tournament.tournament_start.tzname())
        embed.add_field(
            name=_("Registration"),
            value=_(
                "Opening: {opening}\n"
                "Second opening: {secondopening}\n"
                "Close when complete: {autostop}\n"
                "Closing : {closing}"
            ).format(
                opening=format_datetime(tournament.register_start, "register_start"),
                secondopening=format_datetime(
                    tournament.register_second_start, "register_second_start"
                )
                if tournament.register_second_start
                else _("Disabled"),
                autostop=_("Enabled") if tournament.autostop_register else _("Disabled"),
                closing=format_datetime(tournament.register_stop, "register_stop"),
            ),
        )
        embed.add_field(
            name=_("Check-in"),
            value=_("Opening: {opening}\nClosing : {closing}").format(
                opening=format_datetime(tournament.checkin_start, "checkin_start"),
                closing=format_datetime(tournament.checkin_stop, "checkin_stop"),
            ),
        )
        embed.set_footer(
            text=(
                _('Using config "{name}"').format(name=config)
                if config
                else _("Using default config.")
            )
        )
        result = await prompt_yes_or_no(
            ctx, _("Is this correct?"), embed=embed, timeout=60, delete_after=False
        )
        if result is False:
            return
        self.tournaments[guild.id] = tournament
        await self.data.guild(guild).tournament.set(tournament.to_dict())
        await ctx.send(_("The tournament is now set!"))

    @mod_or_to()
    @commands.command(name="tinfo", aliases=["tournamentinfo"])
    @commands.guild_only()
    async def tournamentinfo(self, ctx: commands.Context):
        """
        Shows infos about the current tournament.
        """
        try:
            t = self.tournaments[ctx.guild.id]
        except KeyError:
            await ctx.send(_("There's no tournament setup on this server."))
            return

        def get_time(d: datetime):
            if d:
                return d.strftime("%d/%m/%y %H:%M")
            else:
                return _("Manual")

        def get_channel(c: discord.TextChannel):
            if c:
                return c.mention
            else:
                return _("Not set.")

        embed = discord.Embed(title=f"{t.name} • *{t.game}*")
        embed.url = t.url
        embed.description = _("Current phase: {phase}").format(phase=t.phase)
        if t.phase == "ongoing":
            embed.add_field(
                name=_("Participants"),
                value=_("Total: {total}\nIn-game: {ingame}").format(
                    total=len(t.participants), ingame=len([x for x in t.participants if x.match])
                ),
                inline=False,
            )
            embed.add_field(
                name=_("Matchs"),
                value=_(
                    "Total: {total}\nOngoing: {ongoing}\n"
                    "Scheduled: {scheduled}\nEnded (awaiting deletion): {ended}"
                ).format(
                    total=len(t.matches),
                    ongoing=len([x for x in t.matches if x.status == "ongoing"]),
                    scheduled=len([x for x in t.matches if x.status == "pending"]),
                    ended=len([x for x in t.matches if x.status == "finished"]),
                ),
                inline=False,
            )
            if t.task is None or not t.loop_task.is_running():
                embed.add_field(
                    name="\u200B",
                    value=_(
                        ":warning: **The background task is not running.**\n"
                        "This is either a bug, or someone paused it manually. Resume it with "
                        "`{prefix}tfix resumetask`.\n"
                        "Type `{prefix}help tfix pausetask` for details about "
                        "the role of this background loop task."
                    ).format(prefix=ctx.clean_prefix),
                    inline=False,
                )
        else:
            limit = f"/{t.limit}" if t.limit else _(" *(no limit)*")
            checked = len([x for x in t.participants if x.checked_in])
            checkin = (
                _("\n{checked}/{total} checked").format(checked=checked, total=len(t.participants))
                if 0 < checked < len(t.participants)
                else ""
            )
            embed.add_field(name=_("Start time"), value=get_time(t.tournament_start), inline=True)
            embed.add_field(
                name=_("Participants registered"),
                value=f"{len(t.participants)}{limit}{checkin}",
                inline=True,
            )
            try:
                name, time = t.next_scheduled_event()
            except TypeError:
                embed.add_field(
                    name=_("Next scheduled event"),
                    value=_("None"),
                    inline=True,
                )
            else:
                name = {
                    "register_start": _("Registration start"),
                    "register_second_start": _("Second registration start"),
                    "register_stop": _("Registration ending"),
                    "checkin_start": _("Check-in start"),
                    "checkin_stop": _("Check-in stop"),
                }.get(name)
                embed.add_field(
                    name=_("Next scheduled event"),
                    value=f"{name}\n{str(time).split('.')[0]}",
                    inline=True,
                )
            status = {
                "manual": _("Manual"),
                "pending": _("Pending"),
                "ongoing": _("Ongoing"),
                "onhold": _("On hold (awaiting second opening)"),
                "done": _("Done"),
            }
            embed.add_field(
                name=_("Registration"),
                value=_(
                    "Current status: **{status}**\n\n"
                    "Opening : {opening}\n"
                    "Second opening : {secondopening}\n"
                    "Closing : {closing}\n"
                    "Auto-stop : {stop}"
                ).format(
                    status=status.get(t.register_phase),
                    opening=get_time(t.register_start),
                    secondopening=get_time(t.register_second_start)
                    if t.register_second_start
                    else _("Disabled"),
                    closing=get_time(t.register_stop),
                    stop=_("Enabled") if t.autostop_register else _("Disabled"),
                ),
                inline=True,
            )
            embed.add_field(
                name=_("Check-in"),
                value=_(
                    "Current status: **{status}**\n\n" "Opening: {start}\n" "Closing: {stop}"
                ).format(
                    status=status.get(t.checkin_phase),
                    start=get_time(t.checkin_start),
                    stop=get_time(t.checkin_stop),
                ),
                inline=True,
            )
            embed.set_footer(text=_("Timezone: {tz}").format(tz=str(t.tz)))
        await ctx.send(embed=embed)
