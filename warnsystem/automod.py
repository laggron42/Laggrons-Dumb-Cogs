import discord

from redbot.core import commands
from redbot.core import checks
from redbot.core.i18n import Translator
from redbot.core.utils import menus
from redbot.core.utils.chat_formatting import pagify, box
from redbot.core.commands.converter import TimedeltaConverter

from typing import Optional

from .abc import MixinMeta
from .converters import ValidRegex

_ = Translator("WarnSystem", __file__)


class AutomodMixin(MixinMeta):
    """
    Automod configuration.
    """

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
                await self.cache.add_automod_enabled(guild)
                await ctx.send(_("Automod is now enabled."))
            else:
                await self.cache.remove_automod_enabled(guild)
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
"(?i)(discord\.gg|discordapp\.com\/invite|discord\.me)\/(\S+)" \
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
        for name, value in automod_regex:
            text += f"+ {name}\n{value}\n\n"
        messages = []
        pages = list(pagify(text, delims=["\n\n", "\n"], priority=True, page_length=1900))
        for i, page in enumerate(pages):
            messages += _("Page {i}/{total}").format(i=i + 1, total=len(pages)) + box(page, "md")
        await menus.menu(ctx, pages=messages, controls=menus.DEFAULT_CONTROLS)
