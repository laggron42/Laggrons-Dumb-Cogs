import discord

from datetime import timedelta
from typing import TYPE_CHECKING, Optional, cast
from discord.interactions import Interaction
from discord.ui import View, Modal, TextInput, button

from redbot.core import app_commands
from redbot.core.i18n import Translator
from redbot.core.commands import BadArgument, Context
from redbot.core.commands.converter import parse_timedelta

if TYPE_CHECKING:
    from redbot.core.bot import Red
    from .warnsystem import WarnSystem

_ = Translator("WarnSystem", __file__)


class ReasonEntry(Modal, title="Member warn"):
    reason = TextInput(
        label="Reason",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=False,
        placeholder="Optional, substitutions work",
    )
    duration = TextInput(
        label="Duration",
        style=discord.TextStyle.short,
        max_length=100,
        required=False,
        placeholder="Example: 2d12h30m = 2 days, 12 hours, 30 minutes",
    )
    ban_days = TextInput(
        label="Number of days of messages to delete",
        style=discord.TextStyle.short,
        max_length=1,
        required=False,
        placeholder="Max of 7 days",
    )

    def __init__(
        self, og_interaction: discord.Interaction["Red"], level: int, member: discord.Member
    ):
        super().__init__()
        self.og_interaction = og_interaction
        self.level = level
        self.member = member

    async def on_submit(self, interaction: Interaction["Red"]) -> None:
        cog = cast("WarnSystem", interaction.client.get_cog("WarnSystem"))

        duration: Optional[timedelta] = None
        ban_days: Optional[int] = None
        if self.duration.value:
            try:
                duration = parse_timedelta(self.duration.value)
            except BadArgument:
                await interaction.response.send_message(_("Invalid duration"), ephemeral=True)
                return
            if not duration:
                await interaction.response.send_message(_("Invalid duration"), ephemeral=True)
                return
        if self.ban_days.value:
            try:
                ban_days = int(self.ban_days.value)
            except ValueError:
                await interaction.response.send_message(
                    _("You must input a number, not {}").format(self.ban_days.value),
                    ephemeral=True,
                )
                return
            if ban_days > 7 or ban_days < 1:
                await interaction.response.send_message(
                    _("The number of days must be between 1 and 7."), ephemeral=True
                )
                return

        await cog.call_warn(
            ctx=await Context.from_interaction(self.og_interaction),
            level=self.level,
            member=self.member,
            reason=self.reason.value,
            time=duration,
            ban_days=ban_days,
        )
        await interaction.response.edit_message(content=_("Done."))


class WarnView(View):
    def __init__(self, og_interaction: discord.Interaction["Red"], member: discord.Member):
        self.og_interaction = og_interaction
        self.member = member
        super().__init__(timeout=30)

    async def on_timeout(self):
        self.stop()
        for item in self.children:
            item.disabled = True
        await self.og_interaction.followup.edit_message("@original", view=self)

    async def warn(self, interaction: discord.Interaction["Red"], level: int):
        await self.on_timeout()
        modal = ReasonEntry(self.og_interaction, level=level, member=self.member)
        if level != 2 and level != 5:
            modal.remove_item(modal.duration)
        if level != 4 and level != 5:
            modal.remove_item(modal.ban_days)
        await interaction.response.send_modal(modal)

    @button(label="Warn", style=discord.ButtonStyle.secondary, emoji="\N{WARNING SIGN}")
    async def warn_1(self, interaction: discord.Interaction["Red"], button: discord.ui.Button):
        await self.warn(interaction, 1)

    @button(
        label="Mute",
        style=discord.ButtonStyle.secondary,
        emoji="\N{SPEAKER WITH CANCELLATION STROKE}",
    )
    async def warn_2(self, interaction: discord.Interaction["Red"], button: discord.ui.Button):
        await self.warn(interaction, 2)

    @button(label="Kick", style=discord.ButtonStyle.primary, emoji="\N{WOMANS BOOTS}")
    async def warn_3(self, interaction: discord.Interaction["Red"], button: discord.ui.Button):
        await self.warn(interaction, 3)

    @button(label="Softban", style=discord.ButtonStyle.primary, emoji="\N{WOMANS BOOTS}")
    async def warn_4(self, interaction: discord.Interaction["Red"], button: discord.ui.Button):
        await self.warn(interaction, 4)

    @button(label="Ban", style=discord.ButtonStyle.danger, emoji="\N{HAMMER}")
    async def warn_5(self, interaction: discord.Interaction["Red"], button: discord.ui.Button):
        await self.warn(interaction, 5)


@app_commands.context_menu(name="Warn")
async def context_warn(interaction: discord.Interaction["Red"], member: discord.Member):
    cog = cast("WarnSystem", interaction.client.get_cog("WarnSystem"))
    if not cog:
        await interaction.response.send_message(
            _("The WarnSystem cog is not loaded"), ephemeral=True
        )
        return
    if (
        not interaction.user.guild_permissions.administrator
        and not await interaction.client.is_mod(interaction.user)
    ):
        await interaction.response.send_message(
            _("You are not allowed to do this"), ephemeral=True
        )
        return
    await interaction.response.send_message(
        _("Please choose an action to perform."),
        view=WarnView(interaction, member),
        ephemeral=True,
    )
