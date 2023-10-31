from __future__ import annotations

import discord

from discord.components import SelectOption
from discord.interactions import Interaction
from discord.ui import Button, View, Modal, TextInput
from asyncio import TimeoutError as AsyncTimeoutError
from datetime import datetime, timezone
from typing import Optional, Union, List, Tuple, TYPE_CHECKING, cast

from redbot.core.i18n import Translator
from redbot.core.utils import mod
from redbot.core.commands import Context
from redbot.vendored.discord.ext import menus

from .api import UnavailableMember
from .paginator import Pages

if TYPE_CHECKING:
    from redbot.core.bot import Red
    from .api import API
    from .warnsystem import WarnSystem

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
    now = datetime.now(timezone.utc)
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


async def prompt_yes_or_no(
    bot: "Red",
    interaction: discord.Interaction,
    content: Optional[str] = None,
    *,
    embed: Optional[discord.Embed] = None,
    timeout: int = 30,
    clear_after: bool = True,
    negative_response: bool = True,
) -> bool:
    """
    Sends a message and waits for used confirmation, using buttons.

    Credit to TrustyJAID for the stuff with buttons. Source:
    https://github.com/TrustyJAID/Trusty-cogs/blob/f6ceb28ff592f664070a89282288452d615d7dc5/eventposter/eventposter.py#L750-L777

    Parameters
    ----------
    content: Union[str, discord.Embed]
        Either text or an embed to send.
    timeout: int
        Time before timeout. Defaults to 30 seconds.
    clear_after: bool
        Should the message have its buttons removed? Defaults to True. Set to false if you will
        edit later
    negative_response: bool
        If the bot should send "Cancelled." after a negative response. Defaults to True.

    Returns
    -------
    bool
        False if the user declined, if the request timed out, or if there are insufficient
        permissions, else True.
    """
    view = discord.ui.View()
    approve_button = discord.ui.Button(
        style=discord.ButtonStyle.green,
        emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}",
        custom_id=f"yes-{interaction.message.id}",
    )
    deny_button = discord.ui.Button(
        style=discord.ButtonStyle.red,
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
        custom_id=f"no-{interaction.message.id}",
    )
    view.add_item(approve_button)
    view.add_item(deny_button)
    await interaction.response.edit_message(content=content, embed=embed, view=view)

    def check_same_user(inter):
        return inter.user.id == interaction.user.id

    try:
        interaction = await bot.wait_for("interaction", check=check_same_user, timeout=timeout)
    except AsyncTimeoutError:
        await interaction.response.edit_message(content=_("Request timed out."))
        return False
    else:
        custom_id = interaction.data.get("custom_id")
        if custom_id == f"yes-{interaction.message.id}":
            return True
        if negative_response:
            await interaction.response.edit_message(content=_("Cancelled."), view=None, embed=None)
        return False
    finally:
        if clear_after:
            await interaction.response.edit_message(
                content=interaction.message.content, embed=embed, view=None
            )


class WarningEditionModal(Modal, title="Warning reason edition"):
    new_reason = TextInput(
        label=_("New reason"),
        placeholder=_("Enter the new reason here, substitutions work."),
        min_length=1,
        style=discord.TextStyle.long,
    )

    async def on_submit(self, interaction: Interaction) -> None:
        self.interaction = interaction


class WarningEditionView(View):
    def __init__(
        self,
        bot: "Red",
        list: WarningsSelector,
        *,
        user: Union[discord.Member, UnavailableMember],
        case: dict,
        case_index: int,
        disabled: bool = False,
    ):
        super().__init__()
        self.bot = bot
        self.list = list
        self.ws = cast("WarnSystem", bot.get_cog("WarnSystem"))
        self.api: "API" = self.ws.api
        self.user = user
        self.case = case
        self.case_index = case_index
        if disabled:
            self.edit_button.disabled = True
            self.delete_button.disabled = True

    @discord.ui.button(style=discord.ButtonStyle.secondary, label=_("Edit reason"), emoji="✏")
    async def edit_button(self, interaction: discord.Interaction, button: Button):
        modal = WarningEditionModal()
        await interaction.response.send_modal(modal)
        if await modal.wait():
            pass  # timed out
        interaction = modal.interaction
        embed = discord.Embed()
        new_reason = await self.api.format_reason(interaction.guild, modal.new_reason.value)
        embed.description = _("Case #{number} edition.").format(number=self.case_index + 1)
        embed.add_field(name=_("Old reason"), value=self.case["reason"], inline=False)
        embed.add_field(name=_("New reason"), value=new_reason, inline=False)
        embed.set_footer(text=_("Click on ✅ to confirm the changes."))
        response = await prompt_yes_or_no(self.bot, interaction, embed=embed, clear_after=False)
        if response is False:
            return
        await self.api.edit_case(interaction.guild, self.user, self.case_index + 1, new_reason)
        await interaction.followup.edit_message(
            "@original", content=_("The reason was successfully edited!\n"), embed=None, view=None
        )

    @discord.ui.button(
        style=discord.ButtonStyle.danger,
        label=_("Delete case"),
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
    )
    async def delete_button(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        embed = discord.Embed()
        can_unmute = False
        add_roles = False
        if self.case["level"] == 2:
            mute_role = guild.get_role(await self.ws.cache.get_mute_role(guild))
            member = guild.get_member(self.user)
            if member:
                if mute_role and mute_role in member.roles:
                    can_unmute = True
                add_roles = await self.ws.data.guild(guild).remove_roles()
        description = _(
            "Case #{number} deletion.\n**Click on the button to confirm your action.**"
        ).format(number=self.case_index + 1)
        if can_unmute or add_roles:
            description += _("\nNote: Deleting the case will also do the following:")
            if can_unmute:
                description += _("\n- unmute the member")
            if add_roles:
                description += _("\n- add all roles back to the member")
        embed.description = description
        response = await prompt_yes_or_no(self.bot, interaction, embed=embed, clear_after=False)
        if response is False:
            return
        await self.api.delete_case(guild, self.user, self.case_index + 1)  # does not starting at 0
        self.list.deleted_cases.append(self.case_index)
        await interaction.followup.edit_message(
            "@original", content=_("The case was successfully deleted!"), embed=None, view=None
        )


class WarningsSource(menus.ListPageSource):
    def __init__(self, entries: List[dict]):
        super().__init__(entries, per_page=25)

    async def format_page(self, menu: WarningsSelector, balls: List[dict]):
        menu.set_options(balls)
        return True  # signal to edit the page


class WarningsSelector(Pages[menus.ListPageSource]):
    def __init__(self, ctx: Context, user: Union[discord.Member, UnavailableMember], warnings: List[dict]):
        self.user = user
        self.ws = cast("WarnSystem", ctx.bot.get_cog("WarnSystem"))
        self.api: "API" = self.ws.api
        source = WarningsSource(warnings)
        super().__init__(source, ctx=ctx)
        self.deleted_cases: list[int] = []  # to prevent referencing deleted cases
        self.add_item(self.select_warning_menu)

    def _get_label(self, level: int) -> Tuple[str, str]:
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

    def set_options(self, cases: List[dict]):
        options: List[discord.SelectOption] = []
        for i, case in enumerate(cases, start=self.source.per_page * self.current_page):
            name, emote = self._get_label(case["level"])
            date = pretty_date(self.api._get_datetime(case["time"]))
            if case["reason"] and len(name) + len(case["reason"]) > 25:
                reason = case["reason"][:47] + "..."
            else:
                reason = case["reason"]
            option = SelectOption(
                label=name + " • " + date,
                value=str(i),
                emoji=emote,
                description=reason,
            )
            options.append(option)
        self.select_warning_menu.options = options

    @discord.ui.select(placeholder="Select a warning to view it.")
    async def select_warning_menu(self, interaction: discord.Interaction, item:discord.ui.Select):
        warning_str = lambda level, plural: {
            1: (_("Warning"), _("Warnings")),
            2: (_("Mute"), _("Mutes")),
            3: (_("Kick"), _("Kicks")),
            4: (_("Softban"), _("Softbans")),
            5: (_("Ban"), _("Bans")),
        }.get(level, _("unknown"))[1 if plural else 0]

        guild = interaction.guild
        i = int(interaction.data["values"][0])
        if i in self.deleted_cases:
            await interaction.response.send_message("This case was deleted.", ephemeral=True)
            return
        case = self.source.entries[i]
        level = case["level"]
        moderator = guild.get_member(case["author"])
        moderator = "ID: " + str(case["author"]) if not moderator else moderator.mention
        time = self.api._get_datetime(case["time"])
        embed = discord.Embed(description=_("Case #{number} informations").format(number=i + 1))
        embed.set_author(
            name=f"{self.user} | {self.user.id}", icon_url=self.user.display_avatar.url
        )
        embed.add_field(
            name=_("Level"), value=f"{warning_str(level, False)} ({level})", inline=True
        )
        embed.add_field(name=_("Moderator"), value=moderator, inline=True)
        if case["duration"]:
            duration = self.api._get_timedelta(case["duration"])
            embed.add_field(
                name=_("Duration"),
                value=_("{duration}\n(Until {date})").format(
                    duration=self.api._format_timedelta(duration),
                    date=self.api._format_datetime(time + duration),
                ),
            )
        embed.add_field(name=_("Reason"), value=case["reason"], inline=False)
        embed.timestamp = time
        embed.colour = await self.ws.data.guild(guild).colors.get_raw(level)
        is_mod = await mod.is_mod_or_superior(self.bot, interaction.user)
        await interaction.response.send_message(
            embed=embed,
            view=WarningEditionView(
                self.bot, self, user=self.user, case=case, case_index=i, disabled=not is_mod
            ),
        )
