import discord
import logging
import time

from asyncio import TimeoutError as AsyncTimeoutError
from datetime import datetime
from pathlib import Path
from json import loads

from redbot.core import commands, checks
from redbot.core.i18n import Translator
from redbot.core.utils import predicates, menus
from redbot.core.utils.chat_formatting import pagify

from .abc import MixinMeta

log = logging.getLogger("red.laggron.warnsystem")
_ = Translator("WarnSystem", __file__)


class SettingsMixin(MixinMeta):
    """
    All commands for setting up the bot.

    Credit to https://github.com/Cog-Creators/Red-DiscordBot (mod cog) for all mixin stuff.
    """

    @commands.group()
    @checks.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def warnset(self, ctx: commands.Context):
        """
        Set all WarnSystem settings.

        For more informations about how to configure and use WarnSystem, read the wiki:\
        https://laggron.red/warnsystem.html
        """
        pass

    # commands are listed in the alphabetic order, like the help message
    @warnset.command(name="autoupdate")
    async def warnset_autoupdate(self, ctx: commands.Context, enable: bool = None):
        """
        Defines if the bot should update permissions of new channels for the mute role.

        If enabled, for each new text channel and category created, the Mute role will be\
        denied the permission to send messages and add reactions here.
        Keeping this disabled might cause issues with channels created after the WarnSystem setup\
        where muted members can talk.
        """
        guild = ctx.guild
        current = await self.data.guild(guild).update_mute()
        if enable is None:
            await ctx.send(
                _(
                    "The bot currently {update} new channels. If you want to change this, "
                    "type `[p]warnset autoupdate {opposite}`."
                ).format(
                    update=_("updates") if current else _("doesn't update"), opposite=not current
                )
            )
        elif enable:
            await self.data.guild(guild).update_mute.set(True)
            await ctx.send(
                _("Done. New created channels will be updated to keep the mute role working.")
            )
        else:
            await self.data.guild(guild).update_mute.set(False)
            await ctx.send(
                _(
                    "Done. New created channels won't be updated.\n**Make sure to update "
                    "manually new channels to keep the mute role working as intended.**"
                )
            )

    @warnset.command("bandays")
    async def warnset_bandays(self, ctx: commands.Context, ban_type: str, days: int):
        """
        Set the number of messages to delete when a member is banned.

        You can set a value for a softban or a ban.
        When invoking the command, you must specify `ban` or `softban` as the first\
        argument to specify which type of ban you want to edit, then a number between\
        1 and 7, for the number of days of messages to delete.
        These values will be always used for level 4/5 warnings.

        __Examples__

        - `[p]warnset bandays softban 2`
          The number of days of messages to delete will be set to 2 for softbans.

        - `[p]warnset bandays ban 7`
          The number of days of messages to delete will be set to 7 for bans.

        - `[p]warnset bandays ban 0`
          The bans will not delete any messages.
        """
        guild = ctx.guild
        if all([ban_type != x for x in ["softban", "ban"]]):
            await ctx.send(
                _(
                    "The first argument must be `ban` or `softban`.\n"
                    "Type `{prefix}help warnset bandays` for more details."
                )
            )
            return
        if not 0 <= days <= 7:
            is_ban = _("You can set 0 to disable messages deletion.") if ban_type == "ban" else ""
            await ctx.send(
                _(
                    "The number of days of messages to delete must be between "
                    "1 and 7, due to Discord restrictions.\n"
                )
                + is_ban
            )
            return
        if days == 0 and ban_type == "softban":
            await ctx.send(
                _(
                    "The goal of a softban is to delete the members' messages. Disabling "
                    "this would make the softban a simple kick. Enter a value between 1 and 7."
                )
            )
            return
        if ban_type == "softban":
            await self.data.guild(guild).bandays.softban.set(days)
        else:
            await self.data.guild(guild).bandays.ban.set(days)
        await ctx.send(_("The new value was successfully set!"))

    @warnset.command(name="channel")
    async def warnset_channel(
        self, ctx: commands.Context, channel: discord.TextChannel, level: int = None
    ):
        """
        Set the channel for the WarnSystem modlog.

        This will use the Red's modlog by default if it was set.

        All warnings will be logged here.
        I need the `Send Messages` and `Embed Links` permissions.

        If you want to set one channel for a specific level of warning, you can specify a\
        number after the channel
        """
        guild = ctx.guild
        if not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("I don't have the permission to send messages in that channel."))
        elif not channel.permissions_for(guild.me).embed_links:
            await ctx.send(_("I don't have the permissions to send embed links in that channel."))
        else:
            if not level:
                await self.data.guild(guild).channels.main.set(channel.id)
                await ctx.send(
                    _(
                        "Done. All events will be send to that channel by default.\n\nIf you want "
                        "to send a specific warning level in a different channel, you can use the "
                        "same command with the number after the channel.\nExample: "
                        "`{prefix}warnset channel #your-channel 3`"
                    ).format(prefix=ctx.prefix)
                )
            elif not 1 <= level <= 5:
                await ctx.send(
                    _(
                        "If you want to specify a level for the channel, provide a number between "
                        "1 and 5."
                    )
                )
            else:
                await self.data.guild(guild).channels.set_raw(level, value=channel.id)
                await ctx.send(
                    _(
                        "Done. All level {level} warnings events will be sent to that channel."
                    ).format(level=str(level))
                )

    @warnset.command("color")
    async def warnset_color(self, ctx: commands.Context, level: int, color: discord.Color):
        """
        Edit the color of the embed.

        This changes the color of the left bar if you don't like the default ones.

        You can provide an hexadecimal code like this: `#FFFFFF`
        You can also provide the color name, like `green` or `dark-blue`.
        """
        guild = ctx.guild
        if not 1 <= level <= 5:
            await ctx.send(_("You must provide a level between 1 and 5."))
            return
        await self.data.guild(guild).colors.set_raw(str(level), value=color.value)
        await ctx.send(
            _(
                "The new color for level {level} warnings has been succesfully set to {color}"
            ).format(level=level, color=color.value)
        )

    @warnset.command(name="convert")
    async def warnset_convert(self, ctx: commands.Context, *, path: Path):
        """
        Convert BetterMod V2 logs to V3.

        You need to point the path to your history file.
        Get your old Red V2 instance folder, go to `/data/bettermod/history/<server ID>.json` and\
        copy its path.
        You can get your server ID with the `[p]serverinfo` command.

        Example:
        `[p]warnset convert\
        /home/laggron/Desktop/Red-DiscordBot/data/bettermod/history/363008468602454017.json`
        """

        async def maybe_clear(message):
            try:
                await message.clear_reactions()
            except Exception:
                pass

        async def convert(data: dict) -> int:
            """
            Convert V2 logs to V3 format.
            """
            try:
                del data["version"]
            except KeyError:
                pass
            total_cases = 0
            for member, logs in data.items():
                cases = []
                for case in [y for x, y in logs.items() if x.startswith("case")]:
                    level = {"Simple": 1, "Kick": 3, "Softban": 4, "Ban": 5}.get(case["level"], 1)
                    timestamp = datetime.strptime(case["timestamp"], "%d %b %Y %H:%M").timestamp()
                    cases.append(
                        {
                            "level": level,
                            "author": "Unknown",
                            "reason": case["reason"],
                            "time": timestamp,
                            "duration": None,
                            "roles": [],
                        }
                    )
                    total_cases += 1
                async with self.data.custom("MODLOGS", guild.id, int(member)).x() as logs:
                    logs.extend(cases)
            return total_cases

        guild = ctx.guild
        react = guild.me.guild_permissions.add_reactions
        if not path.is_file():
            await ctx.send(_("That path doesn't exist."))
            return
        if not path.name.endswith(".json"):
            await ctx.send(_("That's not a valid file."))
            return
        if not path.name.startswith(str(guild.id)):
            yes_no = "(y/n)" if not react else ""
            message = await ctx.send(
                _(
                    "It looks like that file doesn't belong to the current server. Are you sure "
                    "you want to use this file?"
                )
                + yes_no
            )
            if react:
                menus.start_adding_reactions(
                    message, predicates.ReactionPredicate.YES_OR_NO_EMOJIS
                )
                pred = predicates.ReactionPredicate.yes_or_no(message, ctx.author)
                try:
                    await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
                except AsyncTimeoutError:
                    await ctx.send(_("Request timed out."))
                    await maybe_clear(message)
                    return
                await maybe_clear(message)
            else:
                pred = predicates.MessagePredicate.yes_or_no(ctx)
                try:
                    await self.bot.wait_for("message", check=pred, timeout=30)
                except AsyncTimeoutError:
                    await ctx.send(_("Request timed out."))
                    return
            if not pred.result:
                await ctx.send(_("Alrght, try again with the good file."))
                return
        content = path.open().read()
        try:
            content = loads(content)
        except Exception as e:
            log.warn(
                f"Couldn't decode JSON given by {ctx.author} (ID: {ctx.author.id}) at {str(path)}",
                exc_info=e,
            )
            await ctx.send(
                _(
                    "Couln't read the file because of an exception. "
                    "Check your console or logs for details."
                )
            )
            return
        await ctx.send(
            _(
                "Would you like to **append** the logs or **overwrite** them?\n\n"
                "**Append** will get the logs and add them to the current logs.\n"
                "**Overwrite** will erase the current logs and replace it with the given logs.\n\n"
                "*Type* `append` *or* `overwrite` *in the chat.*"
            )
        )
        pred = predicates.MessagePredicate.lower_contained_in(
            [_("append"), _("overwrite")], ctx=ctx
        )
        try:
            await self.bot.wait_for("message", check=pred, timeout=40)
        except AsyncTimeoutError:
            await ctx.send(_("Request timed out."))
            return
        t1 = time.time()
        if pred.result == 0:
            await ctx.send(_("Starting conversion... This might take a long time."))
            total = await convert(content)
        elif pred.result == 1:
            await ctx.send(_("Deleting server logs... Settings, such as channels, are kept."))
            await self.data.custom("MODLOGS").set({})
            await ctx.send(_("Starting conversion... This might take a long time."))
            total = await convert(content)
        t2 = time.time()
        await ctx.send(
            _(
                "Done! {number} cases were added to the WarnSystem V3 log.\n"
                "This took {time} seconds."
            ).format(number=total, time=round(t2 - t1, 2))
        )
        log.info(
            f"[Guild {guild.id}] {ctx.author.name} (ID: {ctx.author.id}) used the BetterMod data "
            f"converter and converted {total} cases, added with "
            f"the {'append' if pred.result == 0 else 'overwrite'} strategy.\n"
            f"The file used to convert is located at {path}"
        )

    @warnset.command(name="description")
    async def warnset_description(
        self, ctx: commands.Context, level: int, destination: str, *, description: str
    ):
        """
        Set a custom description for the modlog embeds.

        You can set the description for each type of warning, one for the user in DM\
        and the other for the server modlog.

        __Keys:__

        You can include these keys in your message:

        - `{invite}`: Generate an invite for the server
        - `{member}`: The warned member (tip: you can use `{member.id}` for the member's ID or\
        `{member.mention}` for a mention)
        - `{mod}`: The moderator that warned the member (you can also use keys like\
        `{moderator.id}`)
        - `{duration}`: The duration of a timed mute/ban if it exists
        - `{time}`: The current date and time.

        __Examples:__

        - `[p]warnset description 1 user You were warned by a moderator for your behaviour,\
        please read the rules.`
          This set the description for the first warning for the warned member.

        - `[p]warnset description 3 modlog A member was kicked from the server.`
          This set the description for the 3rd warning (kick) for the modlog.

        - `[p]warnset description 4 user You were banned and unbanned to clear your messages\
        from the server. You can join the server back with this link: {invite}`
          This set the description for the 4th warning (softban) for the user, while generating\
          an invite which will be replace `{invite}`
        """
        guild = ctx.guild
        if not any([destination == x for x in ["modlog", "user"]]):
            await ctx.send(
                _(
                    "You need to specify `modlog` or `user`. Read the help of "
                    "the command for more details."
                )
            )
            return
        if not 1 <= level <= 5:
            await ctx.send(_("You must provide a level between 1 and 5."))
            return
        if len(description) > 800:
            await ctx.send("Your text is too long!")
            return
        await self.data.guild(guild).set_raw(
            "embed_description_" + destination, str(level), value=description
        )
        await ctx.send(
            _("The new description for {destination} (warn {level}) was successfully set!").format(
                destination=_("modlog") if destination == "modlog" else _("user"), level=level
            )
        )

    @warnset.command(name="detectmanual")
    async def warnset_detectmanual(self, ctx: commands.Context, enable: bool = None):
        """
        Defines if the bot should log manual kicks/bans with WarnSystem.

        If enabled, manually banning a member will make the bot log the action in the modlog and\
save it, as if it was performed with WarnSystem. **However, the member will not receive a DM**.
        This also works with kicks, but not timeouts *yet*.

        Invoke the command without arguments to get the current status.
        """
        guild = ctx.guild
        current = await self.data.guild(guild).log_manual()
        if enable is None:
            await ctx.send(
                _(
                    "The bot currently {detect} manual actions. If you want to change this, "
                    "type `{prefix}warnset detectmanual {opposite}`."
                ).format(
                    detect=_("detects") if current else _("doesn't detect"),
                    opposite=not current,
                    prefix=ctx.clean_prefix,
                )
            )
        elif enable:
            await self.data.guild(guild).log_manual.set(True)
            await ctx.send(_("Done. The bot will now listen for manual actions and log them."))
        else:
            await self.data.guild(guild).log_manual.set(False)
            await ctx.send(_("Done. The bot won't listen for manual actions anymore."))

    @warnset.command(name="hierarchy")
    async def warnset_hierarchy(self, ctx: commands.Context, enable: bool = None):
        """
        Set if the bot should respect roles hierarchy.

        If enabled, a member cannot ban another member above them in the roles hierarchy, like\
        with manual bans.
        If disabled, mods can ban everyone the bot can.

        Invoke the command without arguments to get the current status.
        """
        guild = ctx.guild
        current = await self.data.guild(guild).respect_hierarchy()
        if enable is None:
            await ctx.send(
                _(
                    "The bot currently {respect} role hierarchy. If you want to change this, "
                    "type `[p]warnset hierarchy {opposite}`."
                ).format(
                    respect=_("respects") if current else _("doesn't respect"),
                    opposite=not current,
                )
            )
        elif enable:
            await self.data.guild(guild).respect_hierarchy.set(True)
            await ctx.send(
                _(
                    "Done. Moderators will not be able to take actions on the members higher "
                    "than themselves in the role hierarchy of the server."
                )
            )
        else:
            await self.data.guild(guild).respect_hierarchy.set(False)
            await ctx.send(
                _(
                    "Done. Moderators will be able to take actions on anyone on the server, as "
                    "long as the bot is able to do so."
                )
            )

    @warnset.command(name="mute")
    async def warnset_mute(self, ctx: commands.Context, *, role: discord.Role = None):
        """
        Create the role used for muting members.

        You can specify a role when invoking the command to specify which role should be used.
        If you don't specify a role, one will be created for you.
        """
        guild = ctx.guild
        my_position = guild.me.top_role.position
        if not role:
            if not guild.me.guild_permissions.manage_roles:
                await ctx.send(
                    _("I can't manage roles, please give me this permission to continue.")
                )
                return
            async with ctx.typing():
                fails = await self.api.maybe_create_mute_role(guild)
                my_position = guild.me.top_role.position
                if fails is False:
                    await ctx.send(
                        _(
                            "A mute role was already created! You can change it by specifying "
                            "a role when typing the command.\n`[p]warnset mute <role name>`"
                        )
                    )
                    return
                else:
                    if fails:
                        errors = _(
                            "\n\nSome errors occured when editing the channel permissions:\n"
                        ) + "\n".join(fails)
                    else:
                        errors = ""
                    text = (
                        _(
                            "The role `Muted` was successfully created at position {pos}. Feel "
                            "free to drag it in the hierarchy and edit its permissions, as long "
                            "as my top role is above and the members to mute are below."
                        ).format(pos=my_position - 1)
                        + errors
                    )
                    for page in pagify(text):
                        await ctx.send(page)
        elif role.position >= my_position:
            await ctx.send(
                _(
                    "That role is higher than my top role in the hierarchy. "
                    'Please move it below "{bot_role}".'
                ).format(bot_role=guild.me.top_role.name)
            )
        else:
            await self.cache.update_mute_role(guild, role)
            await ctx.send(_("The new mute role was successfully set!"))

    @warnset.command(name="refreshmuterole")
    @commands.cooldown(1, 120, commands.BucketType.guild)
    async def warnset_refreshmuterole(self, ctx: commands.Context):
        """
        Refresh the mute role's permissions in the server.

        This will iterate all of your channels and make sure all permissions are correctly\
configured for the mute role.

        The muted role will be prevented from sending messages and adding reactions in all text\
channels, and prevented from talking in all voice channels.
        """
        guild = ctx.guild
        mute_role = await self.cache.get_mute_role(guild)
        if mute_role is None:
            await ctx.send(
                _(
                    "No mute role configured on this server. "
                    "Create one with `{prefix}warnset mute`."
                ).format(prefix=ctx.clean_prefix)
            )
            return
        mute_role = guild.get_role(mute_role)
        if not mute_role:
            await ctx.send(
                _(
                    "It looks like the configured mute role was deleted. "
                    "Create a new one with `{prefix}warnset mute`."
                ).format(prefix=ctx.clean_prefix)
            )
            return
        if not guild.me.guild_permissions.manage_channels:
            await ctx.send(_("I need the `Manage channels` permission to continue."))
            return
        await ctx.send(
            _("Now checking {len} channels, please wait...").format(len=len(guild.channels))
        )
        perms = discord.PermissionOverwrite(send_messages=False, add_reactions=False, speak=False)
        reason = _("WarnSystem mute role permissions refresh")
        perms_failed = []  # if it failed because of Forbidden, add to this list
        other_failed = []  # if it failed because of HTTPException, add to this one
        count = 0
        category: discord.CategoryChannel
        async with ctx.typing():
            for channel in guild.channels:  # include categories, text and voice channels
                # we check if the perms are correct, to prevent useless API calls
                overwrites = channel.overwrites_for(mute_role)
                if (
                    isinstance(channel, discord.TextChannel)
                    and overwrites.send_messages is False
                    and overwrites.add_reactions is False
                ):
                    continue
                elif isinstance(channel, discord.VoiceChannel) and overwrites.speak is False:
                    continue
                elif overwrites == perms:
                    continue
                count += 1
                try:
                    log.debug(
                        f"[Guild {guild.id}] Editing channel {channel.name} for "
                        "mute role permissions refresh."
                    )
                    await channel.set_permissions(target=mute_role, overwrite=perms, reason=reason)
                except discord.errors.Forbidden:
                    perms_failed.append(channel)
                except discord.errors.HTTPException as e:
                    log.error(
                        f"[Guild {guild.id}] Failed to edit channel {channel.name} "
                        f"({channel.id}) while refreshing the mute role's permissions.",
                        exc_info=e,
                    )
                    other_failed.append(channel)
        if not perms_failed and not other_failed:
            await ctx.send(
                _("Successfully checked all channels, {len} were edited.").format(len=count)
            )
            return

        def format_channels(channels: list):
            text = ""
            for channel in sorted(channels, key=lambda x: x.position):
                if isinstance(channel, discord.TextChannel):
                    text += f"- Text channel: {channel.mention}"
                elif isinstance(channel, discord.VoiceChannel):
                    text += f"- Voice channel: {channel.name}"
                else:
                    text += f"- Category: {channel.name}"
            return text

        text = _("Successfully checked all channels, {len}/{total} were edited.\n\n").format(
            len=count - len(perms_failed) - len(other_failed), total=count
        )
        if perms_failed:
            text += _(
                "The following channels were not updated due to a permission failure, "
                "probably enforced `Manage channels` permission:\n{channels}\n"
            ).format(channels=format_channels(perms_failed))
        if other_failed:
            text += _(
                "The following channels were not updated due to an unknown error "
                "(check your logs or ask the bot administrator):\n{channels}\n"
            ).format(channels=format_channels(other_failed))
        text += _("You can fix these issues and run the command once again.")
        for page in pagify(text):
            await ctx.send(page)

    @warnset.command(name="reinvite")
    async def warnset_reinvite(self, ctx: commands.Context, enable: bool = None):
        """
        Set if the bot should send an invite after a temporary ban.

        If enabled, any unbanned member will receive a DM with an invite to join back to the server.
        The bot needs to share a server with the member to send a DM.

        Invoke the command without arguments to get the current status.
        """
        guild = ctx.guild
        current = await self.data.guild(guild).reinvite()
        if enable is None:
            await ctx.send(
                _(
                    "The bot {respect} reinvite unbanned members. If you want to "
                    "change this, type `[p]warnset reinvite {opposite}`."
                ).format(respect=_("does") if current else _("doesn't"), opposite=not current)
            )
        elif enable:
            await self.data.guild(guild).reinvite.set(True)
            await ctx.send(
                _(
                    "Done. The bot will try to send an invite to unbanned members. Please note "
                    "that the bot needs to share one server in common with the member to receive "
                    "the message."
                )
            )
        else:
            await self.data.guild(guild).reinvite.set(False)
            await ctx.send(_("Done. The bot will no longer reinvite unbanned members."))

    @warnset.command("removeroles")
    async def warnset_removeroles(self, ctx: commands.Context, enable: bool = None):
        """
        Defines if the bot should remove all roles on mute

        If enabled, when you set a level 2 warning on a member, they will be assigned the mute role\
        as usual, but all of their other roles will also be removed.
        Once the mute ends, the member will get their roles back.
        This can be useful for role permissions issues.
        """
        guild = ctx.guild
        current = await self.data.guild(guild).remove_roles()
        if enable is None:
            await ctx.send(
                _(
                    "The bot currently {remove} all roles on mute. If you want to change this, "
                    "type `[p]warnset removeroles {opposite}`."
                ).format(
                    remove=_("removes") if current else _("doesn't remove"), opposite=not current
                )
            )
        elif enable:
            await self.data.guild(guild).remove_roles.set(True)
            await ctx.send(
                _(
                    "Done. All roles will be removed from muted members. They will get their "
                    "roles back once the mute ends or when someone removes the warning using the "
                    "`{prefix}warnings` command."
                ).format(prefix=ctx.prefix)
            )
        else:
            await self.data.guild(guild).remove_roles.set(False)
            await ctx.send(_("Done. Muted members will keep their roles on mute."))

    @warnset.command(name="settings")
    async def warnset_settings(self, ctx: commands.Context):
        """
        Show the current settings.
        """
        guild = ctx.guild
        if not ctx.channel.permissions_for(guild.me).embed_links:
            await ctx.send(_("I can't send embed links here!"))
            return
        async with ctx.typing():

            # collect data and make strings
            all_data = await self.data.guild(guild).all()
            modlog_channels = await self.api.get_modlog_channel(guild, "all")
            channels = ""
            for key, channel in dict(modlog_channels).items():
                if not channel:
                    if key != "main":
                        continue
                    channel = _("Not set. Use `{prefix}warnset channel`").format(prefix=ctx.prefix)
                else:
                    channel = guild.get_channel(channel)
                    channel = channel.mention if channel else _("Not found")
                if key == "main":
                    channels += _("Default channel: {channel}\n").format(channel=channel)
                else:
                    channels += _("Level {level} warnings channel: {channel}\n").format(
                        channel=channel, level=key
                    )
            mute_role = guild.get_role(all_data["mute_role"])
            mute_role = _("No mute role set.") if not mute_role else mute_role.name
            hierarchy = _("Enabled") if all_data["respect_hierarchy"] else _("Disabled")
            reinvite = _("Enabled") if all_data["reinvite"] else _("Disabled")
            show_mod = _("Enabled") if all_data["show_mod"] else _("Disabled")
            update_mute = _("Enabled") if all_data["update_mute"] else _("Disabled")
            remove_roles = _("Enabled") if all_data["remove_roles"] else _("Disabled")
            manual_bans = _("Enabled") if all_data["log_manual"] else _("Disabled")
            bandays = _("Softban: {softban}\nBan: {ban}").format(
                softban=all_data["bandays"]["softban"], ban=all_data["bandays"]["ban"]
            )
            len_substitutions = len(all_data["substitutions"])
            substitutions = (
                _(
                    "No substitution set.\nType `{prefix}help warnset "
                    "substitutions` to get started."
                ).format(prefix=ctx.prefix)
                if len_substitutions < 1
                else _(
                    "{number} subsitution{plural} set.\n"
                    "Type `{prefix}warnset substitutions list` to list them."
                ).format(
                    number=len_substitutions,
                    plural=_("s") if len_substitutions > 1 else "",
                    prefix=ctx.prefix,
                )
            )
            modlog_dict = all_data["embed_description_modlog"]
            modlog_descriptions = ""
            for key, description in modlog_dict.items():
                if key == "main":
                    key == "Default"
                modlog_descriptions += f"{key}: {description}\n"
            if len(modlog_descriptions) > 1024:
                modlog_descriptions = _("Too long to be shown...")
            user_dict = all_data["embed_description_user"]
            user_descriptions = ""
            for key, description in user_dict.items():
                if key == "main":
                    key == "Default"
                user_descriptions += f"{key}: {description}\n"
            if len(user_descriptions) > 1024:
                user_descriptions = _("Too long to be shown...")
            embed_thumbnails = "\n".join(
                [f"{level}: {value}" for level, value in all_data["thumbnails"].items()]
            )
            embed_colors = "\n".join(
                [
                    f"{level}: {hex(value).replace('0x', '#')}"
                    for level, value in all_data["colors"].items()
                ]
            )

            # make embed
            embeds = [discord.Embed() for x in range(2)]
            embeds[0].title = _("WarnSystem settings. Page 1/2")
            embeds[1].title = _("WarnSystem settings. Page 2/2")
            try:
                color = await self.bot.get_embed_color(ctx)
            except AttributeError:
                color = self.bot.color
            for embed in embeds:
                embed.url = "https://laggron.red/warnsystem.html"
                embed.description = _(
                    "You can change all of these values with {prefix}warnset"
                ).format(prefix=ctx.clean_prefix)
                embed.set_footer(text=_("Cog made with ❤️ by Laggron"))
                embed.colour = color
            embeds[0].add_field(name=_("Log channels"), value=channels)
            embeds[0].add_field(name=_("Mute role"), value=mute_role)
            embeds[0].add_field(name=_("Respect hierarchy"), value=hierarchy)
            embeds[0].add_field(name=_("Reinvite unbanned members"), value=reinvite)
            embeds[0].add_field(name=_("Show responsible moderator"), value=show_mod)
            embeds[0].add_field(name=_("Detect manual actions"), value=manual_bans)
            embeds[0].add_field(name=_("Update new channels for mute role"), value=update_mute)
            embeds[0].add_field(name=_("Remove roles on mute"), value=remove_roles)
            embeds[0].add_field(name=_("Days of messages to delete"), value=bandays)
            embeds[0].add_field(name=_("Substitutions"), value=substitutions)
            embeds[1].add_field(name=_("Embed thumbnails"), value=embed_thumbnails)
            embeds[1].add_field(name=_("Embed colors"), value=embed_colors)
            embeds[1].add_field(
                name=_("Modlog embed descriptions"), value=modlog_descriptions, inline=False
            )
            embeds[1].add_field(
                name=_("User embed descriptions"), value=user_descriptions, inline=False
            )
            embeds[1].add_field(
                name="\u200b",
                value=_(
                    "To see informations about the cog (version, documentation, "
                    "support server, Patreon), type `{prefix}warnsysteminfo`."
                ).format(prefix=ctx.clean_prefix),
                inline=False,
            )
        try:
            await menus.menu(ctx=ctx, pages=embeds, controls=menus.DEFAULT_CONTROLS, timeout=90)
        except discord.errors.HTTPException as e:
            log.error("Couldn't make embed for displaying settings.", exc_info=e)
            await ctx.send(
                _(
                    "Error when sending the message. Check the warnsystem "
                    "logs for more informations."
                )
            )

    @warnset.command(name="showmod")
    async def warnset_showmod(self, ctx, enable: bool = None):
        """
        Defines if the responsible moderator should be revealed to the warned member in DM.

        If enabled, any warned member will be able to see who warned them, else they won't know.

        Invoke the command without arguments to get the current status.
        """
        guild = ctx.guild
        current = await self.data.guild(guild).show_mod()
        if enable is None:
            await ctx.send(
                _(
                    "The bot {respect} show the responsible moderator to the warned member in DM. "
                    "If you want to change this, type `[p]warnset showmod {opposite}`."
                ).format(respect=_("does") if current else _("doesn't"), opposite=not current)
            )
        elif enable:
            await self.data.guild(guild).show_mod.set(True)
            await ctx.send(
                _(
                    "Done. The moderator responsible of a warn will now be shown to the warned "
                    "member in direct messages."
                )
            )
        else:
            await self.data.guild(guild).show_mod.set(False)
            await ctx.send(_("Done. The bot will no longer show the responsible moderator."))

    @warnset.group(name="substitutions")
    async def warnset_substitutions(self, ctx: commands.Context):
        """
        Manage the reasons' substitutions

        A substitution is text replaced by a key you place in your warn reason.

        For example, if you set a substitution with the keyword `last warn` associated with the\
        text `This is your last warning!`, this is what will happen with your next warnings:

        `[p]warn 4 @annoying_member Stop spamming. [last warn]`
        Reason = Stop spamming. This is your last warning!
        """
        pass

    @warnset_substitutions.command(name="add")
    async def warnset_substitutions_add(self, ctx: commands.Context, name: str, *, text: str):
        """
        Create a new subsitution.

        `name` should be something short, it will be the keyword that will be replaced by your text
        `text` is what will be replaced by `[name]`

        Example:
        - `[p]warnset substitutions add ad Advertising for a Discord server`
        - `[p]warn 1 @noob [ad] + doesn't respect warnings`
        The reason will be "Advertising for a Discord server + doesn't respect warnings".
        """
        async with self.data.guild(ctx.guild).substitutions() as substitutions:
            if name in substitutions:
                await ctx.send(
                    _(
                        "The name you're using is already used by another substitution!\n"
                        "Delete or edit it with `[p]warnset substitutions delete`"
                    )
                )
                return
            if len(text) > 600:
                await ctx.send(_("That substitution is too long! Maximum is 600 characters!"))
                return
            substitutions[name] = text
        await ctx.send(
            _(
                "Your new subsitutions with the keyword `{keyword}` was successfully "
                "created! Type `[{substitution}]` in your warning reason to use the text you "
                "just set.\nManage your substitutions with the `{prefix}warnset "
                "substitutions` subcommands."
            ).format(keyword=name, substitution=name, prefix=ctx.prefix)
        )

    @warnset_substitutions.command(name="delete", aliases=["del"])
    async def warnset_substitutions_delete(self, ctx: commands.Context, name: str):
        """
        Delete a previously set substitution.

        The substitution must exist, see existing substitutions with the `[p]warnset substitutions\
        list` command.
        """
        async with self.data.guild(ctx.guild).substitutions() as substitutions:
            if name not in substitutions:
                await ctx.send(
                    _(
                        "That substitution doesn't exist!\nSee existing substitutions with the "
                        "`{prefix}warnset substitutions list` command."
                    ).format(prefix=ctx.prefix)
                )
                return
            del substitutions[name]
        await ctx.send(_("The substitutions was successfully deleted."))

    @warnset_substitutions.command(name="list")
    async def warnset_substitutions_list(self, ctx: commands.Context):
        """
        List all existing substitutions on your server
        """
        guild = ctx.guild
        substitutions = await self.data.guild(guild).substitutions()
        if len(substitutions) < 1:
            await ctx.send(
                _(
                    "You don't have any existing substitution on this server!\n"
                    "Create one with `{prefix}warnset substitutions add`"
                ).format(prefix=ctx.prefix)
            )
            return
        text = ""
        for substitution, content in substitutions.items():
            text += f"+ {substitution}\n{content}\n\n"
        messages = [x for x in pagify(text, page_length=1800)]
        total_pages = len(messages)
        for i, page in enumerate(messages):
            await ctx.send(
                _("Substitutions for {server}:").format(server=guild.name)
                + f"\n```diff\n{page}\n```"
                + _("Page {page}/{max}").format(page=i + 1, max=total_pages)
            )

    @warnset.command(name="thumbnail")
    async def warnset_thumbnail(self, ctx: commands.Context, level: int, url: str = None):
        """
        Edit the image displayed on the embeds.

        This is common to the modlog embeds and the embeds sent to the members.
        The URL must be the direct link to the image.
        You can omit the URL if you want to remove any image on the embed.
        """
        guild = ctx.guild
        if not 1 <= level <= 5:
            await ctx.send(_("You must provide a level between 1 and 5."))
            return
        await self.data.guild(guild).thumbnails.set_raw(str(level), value=url)
        await ctx.send(
            _("The new image for level {level} warnings has been set to {image}.").format(
                level=level, image=url
            )
        )
