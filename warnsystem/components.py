from __future__ import annotations

import discord

from discord.components import SelectOption
from discord.ui import Button, Select, Modal, TextInput, View
from datetime import datetime
from typing import List, Optional, Union, TYPE_CHECKING

from redbot.core.i18n import Translator
from redbot.core.utils import mod

from warnsystem.core.api import UnavailableMember
from warnsystem.core.warning import Warning

if TYPE_CHECKING:
    from redbot.core.bot import Red

_ = Translator("WarnSystem", __file__)


def pretty_date(time: datetime):
    """
    Get a datetime object and return a pretty string like 'an hour ago',
    'Yesterday', '3 months ago', 'just now', etc

    This is based on this answer, modified for i18n compatibility:
    https://stackoverflow.com/questions/1551382/user-friendly-time-format-in-python
    """

    def text(amount: float, unit: tuple):
        amount = round(amount)
        if amount > 1:
            unit = unit[1]
        else:
            unit = unit[0]
        return _("{amount} {unit} ago").format(amount=amount, unit=unit)

    units_name = {
        0: (_("year"), _("years")),
        1: (_("month"), _("months")),
        2: (_("week"), _("weeks")),
        3: (_("day"), _("days")),
        4: (_("hour"), _("hours")),
        5: (_("minute"), _("minutes")),
        6: (_("second"), _("seconds")),
    }
    now = datetime.now()
    diff = now - time
    second_diff = diff.seconds
    day_diff = diff.days
    if day_diff < 0:
        return ""
    if day_diff == 0:
        if second_diff < 10:
            return _("Just now")
        if second_diff < 60:
            return text(second_diff, units_name[6])
        if second_diff < 120:
            return _("A minute ago")
        if second_diff < 3600:
            return text(second_diff / 60, units_name[5])
        if second_diff < 7200:
            return _("An hour ago")
        if second_diff < 86400:
            return text(second_diff / 3600, units_name[4])
    if day_diff == 1:
        return _("Yesterday")
    if day_diff < 7:
        return text(day_diff, units_name[3])
    if day_diff < 31:
        return text(day_diff / 7, units_name[2])
    if day_diff < 365:
        return text(day_diff / 30, units_name[1])
    return text(day_diff / 365, units_name[0])


class EditReasonModal(Modal):
    reason = TextInput(
        label=_("New reason"),
        placeholder=_("Substitutions works here"),
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, select_menu: WarningsList, case: Warning):
        super().__init__(title=_("Edit warning reason"))
        self.select_menu = select_menu
        self.case = case

    async def on_submit(self, interaction: discord.Interaction):
        await self.case.edit_reason(self.reason.value)
        await interaction.response.edit_message(embed=await self.case.get_historical_embed())
        self.select_menu.refresh_options()
        await self.select_menu.message.edit(
            embed=self.select_menu.generate_embed(), view=self.select_menu.view
        )


class EditReasonButton(Button):
    def __init__(
        self,
        select_menu: WarningsList,
        case: Warning,
        disabled: bool = False,
        row: Optional[int] = None,
    ):
        self.select_menu = select_menu
        self.case = case
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=_("Edit reason"),
            disabled=disabled,
            emoji="✏",
            row=row or 0,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EditReasonModal(self.select_menu, self.case))


class DeleteWarnButton(Button):
    def __init__(
        self,
        select_menu: WarningsList,
        case: Warning,
        disabled: bool = False,
        row: Optional[int] = None,
    ):
        self.select_menu = select_menu
        self.case = case
        super().__init__(
            style=discord.ButtonStyle.danger,
            label=_("Delete case"),
            disabled=disabled,
            emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
            row=row or 0,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.case.delete()

        # update the internal values
        del self.select_menu.cases[self.case.index]
        try:
            for case in self.select_menu.cases[self.case.index :]:
                case.index += 1
        except KeyError:
            pass  # reached end of list

        await interaction.response.edit_message(
            content=_("The warning was deleted."), embed=None, view=None
        )
        self.select_menu.refresh_options()
        await self.select_menu.message.edit(
            embed=self.select_menu.generate_embed(), view=self.select_menu.view
        )


class WarningsList(Select):
    def __init__(
        self,
        bot: "Red",
        member: Union[UnavailableMember, discord.Member],
        cases: List[Warning],
        *,
        row: Optional[int] = None,
    ):
        self.bot = bot
        self.member = member
        self.cases = cases
        super().__init__(
            placeholder=_("Click to view the list of warnings."),
            min_values=1,
            max_values=1,
            options=self.generate_cases(),
            row=row,
        )

        # the initial message sent by the command, with the options attached
        self.message: Optional[discord.Message] = None

        # when selectiong an option, a view is created with a new message
        # to prevent stacking, always cancel the previous view before creating a new one
        self.launched_view: Optional[View] = None

    def _get_label(self, level: int):
        if level == 1:
            return (_("Warning"), "⚠")
        elif level == 2:
            return (_("Mute"), "🔇")
        elif level == 3:
            return (_("Kick"), "👢")
        elif level == 4:
            return (_("Softban"), "🧹")
        elif level == 5:
            return (_("Ban"), "🔨")

    def generate_cases(self) -> List[SelectOption]:
        options = []
        for i, case in enumerate(self.cases[:24]):
            name, emote = self._get_label(case.level)
            date = pretty_date(case.time)
            if case.reason and len(name) + len(case.reason) > 25:
                reason = case.reason[:47] + "..."
            else:
                reason = case.reason
            option = SelectOption(
                label=name + " • " + date,
                value=i,
                emoji=emote,
                description=reason,
            )
            options.append(option)
        return options

    def generate_embed(self) -> discord.Embed:
        count = {k: 0 for k in range(1, 6)}
        for warn in self.cases:
            count[warn.level] += 1
        msg = []
        for level, total in filter(lambda x: x[1], count.items()):
            msg.append(f"{Warning.get_label_from_level(level, plural=total > 1)}: {total}")
        warn_field = "\n".join(msg)

        avatar = self.member.guild_avatar or self.member.avatar or self.member.default_avatar
        embed = discord.Embed(description=_("User modlog summary."))
        embed.set_author(name=f"{self.member} | {self.member.id}", icon_url=avatar.url)
        embed.add_field(
            name=_("Total number of warnings: ") + str(len(self.cases)),
            value=warn_field,
            inline=False,
        )
        embed.colour = self.member.top_role.colour
        return embed

    def refresh_options(self):
        self.options = self.generate_cases()

    async def callback(self, interaction: discord.Interaction):
        i = int(interaction.data["values"][0])
        case = self.cases[i]
        is_mod = await mod.is_mod_or_superior(self.bot, interaction.user)
        if self.launched_view:
            self.launched_view.stop()
        self.launched_view = view = View()
        # TODO: permission check for interactions on this view
        view.add_item(EditReasonButton(self, case=case, disabled=not is_mod))
        view.add_item(DeleteWarnButton(self, case=case, disabled=not is_mod))
        await interaction.response.send_message(embed=await case.get_historical_embed(), view=view)
