import discord
import asyncio

from redbot.core import commands
from redbot.core import checks
from redbot.core.i18n import Translator
from redbot.core.utils import menus
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate
from redbot.core.utils.chat_formatting import pagify, box
from redbot.core.commands.converter import TimedeltaConverter

from typing import Optional
from datetime import timedelta

from .abc import MixinMeta
from .converters import ValidRegex

_ = Translator("WarnSystem", __file__)


class AutomodMixin(MixinMeta):
    """
    Automod configuration.
    """

    async def _ask_for_value(
        self,
        ctx: commands.Context,
        bot_msg: discord.Message,
        embed: discord.Embed,
        description: str,
        need: str = "same_context",
        optional: bool = False,
    ):
        embed.description = description
        if optional:
            embed.set_footer(text=_('\n\nType "skip" to omit this parameter.'))
        await bot_msg.edit(content="", embed=embed)
        pred = getattr(MessagePredicate, need, MessagePredicate.same_context)(ctx)
        user_msg = await self.bot.wait_for("message", check=pred, timeout=30)
        if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            await user_msg.delete()
        if optional and user_msg.content == "skip":
            return None
        if need == "time":
            try:
                time = await TimedeltaConverter().convert(ctx, user_msg.content)
            except commands.BadArgument:
                await ctx.send(_("Invalid time format."))
                return await self._ask_for_value(ctx, bot_msg, embed, description, need, optional)
            else:
                return time
        if need == "same_context":
            return user_msg.content
        return pred.result

    def _format_embed_for_autowarn(
        self,
        embed: discord.Embed,
        number_of_warns: int,
        warn_level: int,
        warn_reason: str,
        lock_level: int,
        only_automod: bool,
        time: timedelta,
        duration: timedelta,
    ) -> discord.Embed:
        time_str = _("Not set.") if not time else self.api._format_timedelta(time)
        duration_str = _("Not set.") if not duration else self.api._format_timedelta(duration)
        embed.description = _("Number of warnings until action: {num}\n").format(
            num=number_of_warns
        )
        embed.description += _("Warning level: {level}\n").format(level=warn_level)
        embed.description += _("Warning reason: {reason}\n").format(reason=warn_reason)
        embed.description += _("Time interval: {time}\n").format(time=time_str)
        if warn_level == 2 or warn_level == 5:
            embed.description += _("Duration: {time}\n").format(time=duration_str)
        embed.description += _("Lock to level: {level}\n").format(
            level=_("disabled") if lock_level == 0 else lock_level
        )
        embed.description += _("Only count automod: {enabled}\n\n").format(
            enabled=_("yes") if only_automod else _("no")
        )
        embed.add_field(
            name=_("What will happen:"),
            value=_(
                "If a member receives {number}{level_lock} warnings{from_bot}{within_time}, the "
                "bot will set a level {level} warning on him{duration} for the reason: {reason}"
            ).format(
                number=number_of_warns,
                level_lock=_(" level {level}").format(level=lock_level) if lock_level else "",
                from_bot=_(" from the automod") if only_automod else "",
                within_time=_(" within {time}").format(time=time_str) if time else "",
                level=warn_level,
                duration=_(" during {time}").format(time=duration_str) if duration else "",
                reason=warn_reason,
            ),
            inline=False,
        )
        return embed

    @commands.group()
    @checks.admin()
    async def automod(self, ctx: commands.Context):
        """
        WarnSystem automod configuration.
        """
        pass

    @automod.command(name="enable")
    async def automod_enable(self, ctx: commands.Context, confirm: bool = None):
        """
        Enable or disable WarnSystem's automod.
        """
        guild = ctx.guild
        if confirm is not None:
            if confirm:
                if not self.cache.automod_enabled:
                    self.api.enable_automod()
                await self.cache.add_automod_enabled(guild)
                await ctx.send(_("Automod is now enabled."))
            else:
                await self.cache.remove_automod_enabled(guild)
                if not self.cache.automod_enabled:
                    self.api.disable_automod()
                await ctx.send(_("Automod is now disabled."))
        else:
            current = await self.data.guild(guild).automod.enabled()
            await ctx.send(
                _(
                    "Automod is currently {state}.\n"
                    "Type `{prefix}automod enable {arg}` to {action} it."
                ).format(
                    state=_("enabled") if current else _("disabled"),
                    prefix=ctx.clean_prefix,
                    arg=not current,
                    action=_("enable") if not current else _("disable"),
                )
            )

    @automod.group(name="regex")
    async def automod_regex(self, ctx: commands.Context):
        """
        Trigger warnings when a regular expression matches a message like ReTrigger.
        """
        pass

    @automod_regex.command(name="add")
    async def automod_regex_add(
        self,
        ctx: commands.Context,
        name: str,
        regex: ValidRegex,
        level: int,
        time: Optional[TimedeltaConverter],
        *,
        reason: str,
    ):
        """
        Create a new Regex trigger for a warning.

        Use https://regex101.com/ to test your expression.

        Possible keywords:
        - `{member}`
        - `{channel}`
        - `{guild}`

        Example: `[p]automod regex add discord_invite \
"(?i)(discord\\.gg|discordapp\\.com\\/invite|discord\\.me)\\/(\\S+)" \
1 Discord invite sent in {channel.mention}.`
        """
        guild = ctx.guild
        automod_regex = await self.cache.get_automod_regex(guild)
        if name in automod_regex:
            await ctx.send(_("That name is already used."))
            return
        if time:
            if level == 2 or level == 5:
                time = self.api._format_timedelta(time)
            else:
                time = None
        await self.cache.add_automod_regex(guild, name, regex, level, time, reason)
        await ctx.send(_("Regex trigger added!"))

    @automod_regex.command(name="delete", aliases=["del", "remove"])
    async def automod_regex_delete(self, ctx: commands.Context, name: str):
        """
        Delete a Regex trigger.
        """
        guild = ctx.guild
        if name not in await self.cache.get_automod_regex(guild):
            await ctx.send(_("That Regex trigger doesn't exist."))
            return
        await self.cache.remove_automod_regex(guild, name)
        await ctx.send(_("Regex trigger removed."))

    @automod_regex.command(name="list")
    async def automod_regex_list(self, ctx: commands.Context):
        """
        Lists all Regex triggers.
        """
        guild = ctx.guild
        automod_regex = await self.cache.get_automod_regex(guild)
        text = ""
        if not automod_regex:
            await ctx.send(_("Nothing registered."))
            return
        for name, value in automod_regex.items():
            text += (
                f"+ {name}\nLevel {value['level']} warning. Reason: {value['reason'][:40]}...\n\n"
            )
        messages = []
        pages = list(pagify(text, delims=["\n\n", "\n"], priority=True, page_length=1900))
        for i, page in enumerate(pages):
            messages.append(
                _("Page {i}/{total}").format(i=i + 1, total=len(pages)) + box(page, "diff")
            )
        await menus.menu(ctx, pages=messages, controls=menus.DEFAULT_CONTROLS)

    @automod_regex.command(name="show")
    async def automod_regex_show(self, ctx: commands.Context, name: str):
        """
        Show details of a Regex trigger.
        """
        guild = ctx.guild
        try:
            automod_regex = (await self.cache.get_automod_regex(guild))[name]
        except KeyError:
            await ctx.send(_("That Regex trigger doesn't exist."))
            return
        embed = discord.Embed(title=_("Regex trigger: {name}").format(name=name))
        embed.description = _("Regex trigger details.")
        embed.add_field(
            name=_("Regular expression"), value=box(automod_regex["regex"].pattern), inline=False
        )
        embed.add_field(
            name=_("Warning"),
            value=_("**Level:** {level}\n**Reason:** {reason}\n**Duration:** {time}").format(
                level=automod_regex["level"],
                reason=automod_regex["reason"],
                time=self.api._format_timedelta(automod_regex["time"])
                if automod_regex["time"]
                else _("Not set."),
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @automod.group(name="warn")
    async def automod_warn(self, ctx: commands.Context):
        """
        Trigger actions when a member get x warnings within the specified time.

        For example, if a member gets 3 warnings within a day, you can make the bot automatically
set him a level 3 warning with the given reason.
        It is also possible to only include warnings given by the bot when counting.
        """
        pass

    @automod_warn.command(name="add")
    async def automod_warn_add(self, ctx: commands.Context):
        """
        Create a new automated warn based on member's modlog.

        Multiple parameters are needed, you will open an interactive menu.
        """
        guild = ctx.guild
        msg = await ctx.send(_("Loading configuration menu..."))
        await asyncio.sleep(1)
        embed = discord.Embed(title=_("Automatic warn setup"))
        embed.colour = await self.bot.get_embed_colour(ctx)
        try:
            while True:
                number_of_warns = await self._ask_for_value(
                    ctx,
                    msg,
                    embed,
                    _("How many warnings should trigger the automod?"),
                    need="valid_int",
                )
                if number_of_warns > 1:
                    break
                else:
                    await ctx.send(_("This must be higher than 1."))
            while True:
                warn_level = await self._ask_for_value(
                    ctx,
                    msg,
                    embed,
                    _("What's the level of the automod's warning?"),
                    need="valid_int",
                )
                if 1 <= warn_level <= 5:
                    break
                else:
                    await ctx.send(_("Level must be between 1 and 5."))
            warn_reason = await self._ask_for_value(
                ctx, msg, embed, _("What's the reason of the automod's warning?"), optional=True,
            )
            time: timedelta = await self._ask_for_value(
                ctx,
                msg,
                embed,
                _(
                    "For how long should this automod be active?\n\n"
                    "For example, you can make it trigger if a member got 3 warnings"
                    " __within a day__\nOmitting this value will make the automod look across the "
                    "entire member's modlog without time limit.\n\n"
                    "Format is the same as temp mutes/bans: `30m` = 30 minutes, `2h` = 2 hours, "
                    "`4d` = 4 days..."
                ),
                need="time",
                optional=True,
            )
            duration = None
            if warn_level == 2 or warn_level == 5:
                duration: timedelta = await self._ask_for_value(
                    ctx,
                    msg,
                    embed,
                    _(
                        "Level 2 and 5 warnings can be temporary (unmute or unban "
                        "after some time). For how long should the the member stay punished?\n"
                        "Skip this value to make the mute/ban unlimited.\n"
                        "Time format is the same as the previous question."
                    ),
                    need="time",
                    optional=True,
                )
            while True:
                lock_level = await self._ask_for_value(
                    ctx,
                    msg,
                    embed,
                    _(
                        "Should the automod be triggered only by specific level? "
                        "(e.g. only 3 level 1 warnings should trigger)\n"
                        "Send the level or `0` to disable."
                    ),
                    need="valid_int",
                )
                if 0 <= lock_level <= 5:
                    break
                else:
                    await ctx.send(_("Level must be between 0 and 5."))
                    await asyncio.sleep(1)
            only_automod = await self._ask_for_value(
                ctx,
                msg,
                embed,
                _(
                    "Should the automod be triggered only by other automod warnings?\n"
                    "If enabled, warnings issued by a normal moderator "
                    "will not be added to the count.\n\n"
                    "Type `yes` or `no`."
                ),
                need="yes_or_no",
                optional=False,
            )
        except asyncio.TimeoutError:
            await ctx.send(_("Timed out."))
            return
        await msg.delete()
        embed = discord.Embed(title=_("Summary of auto warn"))
        embed = self._format_embed_for_autowarn(
            embed,
            number_of_warns,
            warn_level,
            warn_reason,
            lock_level,
            only_automod,
            time,
            duration,
        )
        embed.add_field(name="\u200B", value=_("Is this correct?"), inline=False)
        message = await ctx.send(embed=embed)
        pred = ReactionPredicate.yes_or_no(message, ctx.author)
        menus.start_adding_reactions(message, ReactionPredicate.YES_OR_NO_EMOJIS)
        try:
            await self.bot.wait_for("reaction_add", check=pred, timeout=30)
        except asyncio.TimeoutError:
            await ctx.send(_("Timed out."))
            return
        if not pred.result:
            await ctx.send(_("Please restart the process over."))
            return
        async with self.data.guild(guild).automod.warnings() as warnings:
            warnings.append(
                {
                    "number": number_of_warns,
                    "time": time.total_seconds() if time else None,
                    "level": lock_level,
                    "automod_only": only_automod,
                    "warn": {
                        "level": warn_level,
                        "reason": warn_reason,
                        "duration": duration.total_seconds() if duration else None,
                    },
                }
            )
        await ctx.send(_("The new automatic warn was successfully saved!"))

    @automod_warn.command(name="delete", aliases=["del", "remove"])
    async def automod_warn_delete(self, ctx: commands.Context, index: int):
        """
        Delete an automated warning.

        You can find the index with the `[p]automod warn list` command.
        """
        guild = ctx.guild
        if index < 0:
            await ctx.send(_("Invalid index, must be positive."))
            return
        async with await self.data.guild(guild).automod.warnings() as warnings:
            try:
                autowarn = warnings[index]
            except IndexError:
                await ctx.send(_("There isn't such automated warn."))
                return
            embed = discord.Embed(title=_("Deletion of the following auto warn:"))
            duration = autowarn["warn"]["duration"]
            embed = self._format_embed_for_autowarn(
                embed,
                autowarn["number"],
                autowarn["warn"]["level"],
                autowarn["warn"]["reason"],
                autowarn["level"],
                autowarn["automod_only"],
                timedelta(seconds=autowarn["time"]),
                timedelta(seconds=duration) if duration else None,
            )
            embed.set_footer(text=_("Confirm with the reactions below."))
            msg = await ctx.send(embed=embed)
            menus.start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(msg, ctx.author)
            try:
                await self.bot.wait_for("reaction_add", check=pred, timeout=30)
            except asyncio.TimeoutError:
                await ctx.send(_("Timed out."))
                return
            if not pred.result:
                await ctx.send(_("The auto warn wasn't deleted."))
                return
            warnings.pop(index)
        await ctx.send(_("Automated warning successfully deleted."))

    @automod_warn.command(name="list")
    async def automod_warn_list(self, ctx: commands.Context):
        """
        Lists automated warnings on this server.
        """
        guild = ctx.guild
        autowarns = await self.data.guild(guild).automod.warnings()
        if not autowarns:
            await ctx.send(_("No automatic warn registered."))
            return
        text = ""
        for index, data in enumerate(autowarns):
            text += _("{index}. level {level} warn (need {number} warns to trigger)\n").format(
                index=index, level=data["warn"]["level"], number=data["number"],
            )
        text = list(pagify(text, page_length=1900))
        pages = []
        for i, page in enumerate(text):
            pages.append(
                _("Page {i}/{total}\n\n").format(i=i + 1, total=len(text))
                + page
                + _("\n*Type `{prefix}automod warn show` to view details.*").format(
                    prefix=ctx.clean_prefix
                )
            )
        await menus.menu(ctx, pages=pages, controls=menus.DEFAULT_CONTROLS)

    @automod_warn.command(name="show")
    async def automod_warn_show(self, ctx: commands.Context, index: int):
        """
        Shows the contents of an automatic warn.

        Index is shown by the `[p]automod warn list` command.
        """
        guild = ctx.guild
        if index < 0:
            await ctx.send(_("Invalid index, must be positive."))
            return
        async with self.data.guild(guild).automod.warnings() as warnings:
            try:
                autowarn = warnings[index]
            except IndexError:
                await ctx.send(_("There isn't such automated warn."))
                return
        embed = discord.Embed(title=_("Settings of auto warn {index}").format(index=index))
        duration = autowarn["warn"]["duration"]
        embed = self._format_embed_for_autowarn(
            embed,
            autowarn["number"],
            autowarn["warn"]["level"],
            autowarn["warn"]["reason"],
            autowarn["level"],
            autowarn["automod_only"],
            timedelta(seconds=autowarn["time"]),
            timedelta(seconds=duration) if duration else None,
        )
        await ctx.send(embed=embed)
