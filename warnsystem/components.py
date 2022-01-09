import discord

from discord.components import SelectOption
from discord.ui import Button, Select, View
from asyncio import TimeoutError as AsyncTimeoutError
from datetime import datetime
from typing import Optional, Union, TYPE_CHECKING

from redbot.core.i18n import Translator
from redbot.core.utils import predicates, mod

from .api import UnavailableMember

if TYPE_CHECKING:
    from redbot.core.bot import Red
    from .api import API
    from .cache import MemoryCache

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
    await interaction.edit_original_message(content=content, embed=embed, view=view)

    def check_same_user(inter):
        return inter.user.id == interaction.user.id

    try:
        x = await bot.wait_for("interaction", check=check_same_user, timeout=timeout)
    except AsyncTimeoutError:
        await interaction.edit_original_message(content=_("Request timed out."))
        return False
    else:
        custom_id = x.data.get("custom_id")
        if custom_id == f"yes-{interaction.message.id}":
            return True
        if negative_response:
            await interaction.edit_original_message(content=_("Cancelled."), view=None, embed=None)
        return False
    finally:
        if clear_after:
            await interaction.edit_original_message(
                content=interaction.message.content, embed=embed, view=None
            )


class EditReasonButton(Button):
    def __init__(
        self,
        bot: "Red",
        interaction: discord.Interaction,
        *,
        user: Union[discord.Member, UnavailableMember],
        case: dict,
        case_index: int,
        disabled: bool = False,
        row: Optional[int] = None,
    ):
        self.bot = bot
        self.inter = interaction
        self.ws = bot.get_cog("WarnSystem")
        self.api: "API" = self.ws.api
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=_("Edit reason"),
            disabled=disabled,
            emoji="✏",
            row=row or 0,
        )
        self.user = user
        self.case = case
        self.case_index = case_index

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        interaction = self.inter
        embed = discord.Embed()
        embed.description = _(
            "Case #{number} edition.\n\n**Please type the new reason to set**"
        ).format(number=self.case_index)
        embed.set_footer(text=_("You have two minutes to type your text in the chat."))
        await interaction.edit_original_message(embed=embed, view=None)
        try:
            response = await self.bot.wait_for(
                "message",
                check=predicates.MessagePredicate.same_context(interaction, user=interaction.user),
                timeout=120,
            )
        except AsyncTimeoutError:
            await interaction.delete_original_message()
            return
        new_reason = await self.api.format_reason(interaction.guild, response.content)
        embed.description = _("Case #{number} edition.").format(number=self.case_index)
        embed.add_field(name=_("Old reason"), value=self.case["reason"], inline=False)
        embed.add_field(name=_("New reason"), value=new_reason, inline=False)
        embed.set_footer(text=_("Click on ✅ to confirm the changes."))
        response = await prompt_yes_or_no(self.bot, interaction, embed=embed, clear_after=False)
        if response is False:
            return
        await self.api.edit_case(interaction.guild, self.user, self.case_index, new_reason)
        await interaction.edit_original_message(
            content=_("The reason was successfully edited!\n"), embed=None, view=None
        )


class DeleteWarnButton(Button):
    def __init__(
        self,
        bot: "Red",
        interaction: discord.Interaction,
        *,
        user: Union[discord.Member, UnavailableMember],
        case: dict,
        case_index: int,
        disabled: bool = False,
        row: Optional[int] = None,
    ):
        self.bot = bot
        self.inter = interaction
        self.ws = bot.get_cog("WarnSystem")
        self.api: "API" = self.ws.api
        self.cache: "MemoryCache" = self.ws.cache
        super().__init__(
            style=discord.ButtonStyle.danger,
            label=_("Delete case"),
            disabled=disabled,
            emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
            row=row or 0,
        )
        self.user = user
        self.case = case
        self.case_index = case_index

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        interaction = self.inter
        guild = interaction.guild
        embed = discord.Embed()
        can_unmute = False
        add_roles = False
        if self.case["level"] == 2:
            mute_role = guild.get_role(await self.cache.get_mute_role(guild))
            member = guild.get_member(self.user)
            if member:
                if mute_role and mute_role in member.roles:
                    can_unmute = True
                add_roles = await self.ws.data.guild(guild).remove_roles()
        description = _(
            "Case #{number} deletion.\n**Click on the button to confirm your action.**"
        ).format(number=self.case_index)
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
        await self.api.delete_case(guild, self.user, self.case_index)
        await interaction.edit_original_message(
            content=_("The case was successfully deleted!"), embed=None, view=None
        )


class WarningsList(Select):
    def __init__(
        self,
        bot: "Red",
        user: Union[discord.Member, UnavailableMember],
        cases: list,
        *,
        row: Optional[int] = None,
    ):
        self.bot = bot
        self.ws = bot.get_cog("WarnSystem")
        self.api: "API" = self.ws.api
        super().__init__(
            placeholder=_("Click to view the list of warnings."),
            min_values=1,
            max_values=1,
            options=self.generate_cases(cases),
            row=row,
        )
        self.user = user
        self.cases = cases

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

    def generate_cases(self, cases: list):
        options = []
        for i, case in enumerate(cases[:24]):
            name, emote = self._get_label(case["level"])
            date = pretty_date(self.api._get_datetime(case["time"]))
            if case["reason"] and len(name) + len(case["reason"]) > 25:
                reason = case["reason"][:47] + "..."
            else:
                reason = case["reason"]
            option = SelectOption(
                label=name + " • " + date,
                value=i,
                emoji=emote,
                description=reason,
            )
            options.append(option)
        return options

    async def callback(self, interaction: discord.Interaction):
        warning_str = lambda level, plural: {
            1: (_("Warning"), _("Warnings")),
            2: (_("Mute"), _("Mutes")),
            3: (_("Kick"), _("Kicks")),
            4: (_("Softban"), _("Softbans")),
            5: (_("Ban"), _("Bans")),
        }.get(level, _("unknown"))[1 if plural else 0]

        guild = interaction.guild
        i = int(interaction.data["values"][0])
        case = self.cases[i]
        level = case["level"]
        moderator = guild.get_member(case["author"])
        moderator = "ID: " + str(case["author"]) if not moderator else moderator.mention
        time = self.api._get_datetime(case["time"])
        embed = discord.Embed(description=_("Case #{number} informations").format(number=i + 1))
        embed.set_author(name=f"{self.user} | {self.user.id}", icon_url=self.user.avatar.url)
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
        embed.add_field(name=_("Reason"), value=case["reason"], inline=False),
        embed.timestamp = time
        embed.colour = await self.ws.data.guild(guild).colors.get_raw(level)
        is_mod = await mod.is_mod_or_superior(self.bot, interaction.user)
        view = View()
        view.add_item(
            EditReasonButton(
                self.bot,
                interaction,
                user=self.user,
                case=case,
                case_index=i,
                disabled=not is_mod,
            )
        )
        view.add_item(
            DeleteWarnButton(
                self.bot,
                interaction,
                user=self.user,
                case=case,
                case_index=i,
                disabled=not is_mod,
            )
        )
        await interaction.response.send_message(embed=embed, view=view)
