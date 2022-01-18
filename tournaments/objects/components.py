import asyncio
from datetime import datetime, timedelta
import discord
import logging
import re

from discord.components import SelectOption
from discord.ui import Button, Select, View

from typing import TYPE_CHECKING

from redbot.core.i18n import Translator
from redbot.core.utils import predicates
from redbot.core.utils.chat_formatting import pagify

from .enums import EventPhase, MatchPhase, StageListType

if TYPE_CHECKING:
    from . import Tournament, Match, Participant

_ = Translator("Tournaments", __file__)
log = logging.getLogger("red.laggron.tournaments")

SCORE_RE = re.compile(r"(?P<score1>[0-9]+) *\- *(?P<score2>[0-9]+)")


class RegisterButton(Button):
    def __init__(self, tournament: "Tournament", disabled: bool = True):
        self.tournament = tournament
        super().__init__(
            style=discord.ButtonStyle.success,
            label=_("Register"),
            emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}",
            disabled=disabled,
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        if self.tournament.limit and len(self.tournament.participants) >= self.tournament.limit:
            await interaction.response.send_message(
                _("No more places for this tournament."), ephemeral=True
            )
            return
        if self.tournament.register.phase != EventPhase.ONGOING:
            await interaction.response.send_message(
                _("Registrations aren't active."), ephemeral=True
            )
            return
        if self.tournament.roles.game and self.tournament.roles.game not in interaction.user.roles:
            await interaction.response.send_message(
                _("You do not have the role to register to this tournament."), ephemeral=True
            )
            return
        if self.tournament.find_participant(discord_id=interaction.user.id)[1]:
            await interaction.response.send_message(
                _("You already are registered to this tournament."), ephemeral=True
            )
            return
        async with self.tournament.lock:
            try:
                await self.tournament.register_participant(interaction.user)
            except discord.HTTPException as e:
                log.error(
                    f"[Guild {guild.id}] Can't register participant {interaction.user.id}",
                    exc_info=e,
                )
                await interaction.response.send_message(
                    _("I can't give you the role."), ephemeral=True
                )
                return
        await interaction.response.send_message(
            _("You are now registered to the tournament **{name}**!").format(
                name=self.tournament.name
            ),
            ephemeral=True,
        )


class UnregisterButton(Button):
    def __init__(self, tournament: "Tournament", disabled: bool = True):
        self.tournament = tournament
        super().__init__(
            style=discord.ButtonStyle.danger,
            label=_("Unregister"),
            emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
            disabled=disabled,
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await self.tournament.unregister_participant(interaction.user, send_dm=False)
        except KeyError:
            await interaction.response.send_message(
                _("You are not registered for this tournament."), ephemeral=True
            )
        else:
            await interaction.response.send_message(
                _("You have been unregistered from this tournament."), ephemeral=True
            )


class CheckInButton(Button):
    def __init__(self, tournament: "Tournament", disabled: bool = True):
        self.tournament = tournament
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=_("Check-in"),
            emoji="\N{MEMO}",
            disabled=disabled,
        )

    async def callback(self, interaction: discord.Interaction):
        player: "Participant" = self.tournament.find_participant(user_id=interaction.user.id)[1]
        if player is None:
            await interaction.response.send_message(
                _("You are not registered for this tournament."), ephemeral=True
            )
        elif player.checked_in:
            await interaction.response.send_message(
                _("You are already checked in."), ephemeral=True
            )
        else:
            await player.check(send_dm=False)
            await interaction.response.send_message(
                _("You have successfully checked-in for the tournament!"), ephemeral=True
            )


class CancelButton(Button):
    def __init__(self, interaction: discord.Integration = None):
        super().__init__(
            style=discord.ButtonStyle.danger,
            emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
        )
        self.inter = interaction
        self.deleted = False

    async def callback(self, interaction: discord.Interaction):
        if self.inter:
            await interaction.response.defer()
            interaction = self.inter
        await interaction.delete_original_message()
        self.deleted = True


class ScoreEntryButton(Button):
    def __init__(self, match: "Match"):
        self.match = match
        self.tournament = match.tournament
        super().__init__(
            style=discord.ButtonStyle.success, label=_("Score entry"), emoji="\N{MEMO}", row=1
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user not in (self.match.player1, self.match.player2):
            await interaction.response.send_message(
                _("You are not part of this match."), ephemeral=True
            )
            return
        if self.match.phase != MatchPhase.ONGOING:
            await interaction.response.send_message(
                _(
                    "Your match has not started yet.\n"
                    "You're either awaiting for a stream, or an error occured internally. "
                    "You can ask a T.O. for a manual score setting."
                ),
                ephemeral=True,
            )
        if self.match.channel and (self.match.start_time + timedelta(minutes=2)) > datetime.now(
            self.tournament.tz
        ):
            await interaction.response.send_message(
                _(
                    "You need to wait for 2 minutes at least after the beginning of your "
                    "match before being able to set your score. T.O.s can bypass this by "
                    "setting the score manually on the bracket."
                ),
                ephemeral=True,
            )
            return
        cancel_button = CancelButton(interaction)
        view = View()
        view.add_item(cancel_button)
        await interaction.response.send_message(
            _(
                "By clicking this button, you declare that you are the winner of this set.\n"
                "Please send the score of your match in the following format : 2-0 ; 2-1 ..."
            ),
            view=view,
        )
        try:
            response: discord.Message = await self.bot.wait_for(
                "message",
                check=predicates.MessagePredicate.same_context(interaction, user=interaction.user),
                timeout=120,
            )
        except asyncio.TimeoutError:
            await interaction.delete_original_message()
            return
        if cancel_button.deleted:
            return
        score = SCORE_RE.match(response.content)
        if score is None:
            await interaction.followup.send(
                _(
                    "The given format is incorrect.\n"
                    "Please retry in the right format (3-0, 2-1, 3-2...)"
                )
            )
            return
        score = (int(score.group("score1")), int(score.group("score2")))
        if score == (0, 0):
            await interaction.followup.send(
                _(
                    "That's a quite special score you've got there dude, you gotta tell "
                    "me how to win without playing, I'm interested..."
                )
            )
            return
        if score[0] == score[1]:
            await interaction.followup.send(
                _(
                    "Hmm... So you're telling me there is a tie *but* you're somehow still "
                    "the winner of your match? Review the formatting of your score."
                )
            )
            return
        if score[1] > score[0]:
            # command used by winner, highest score first
            score = score[::-1]
        if interaction.user.id == self.match.player2.id:
            score = score[::-1]  # player1-player2 format
        async with self.tournament.lock:
            pass  # don't update scores while cache is being updated
        await self.match.end(*score)
        await interaction.followup.send(_(":tada: The score of your match has been set!"))


class LagTestButton(Button):
    def __init__(self, match: "Match"):
        self.match = match
        self.tournament = match.tournament
        super().__init__(
            style=discord.ButtonStyle.danger,
            label=_("Ask for a lag test"),
            emoji="\N{RIGHT-POINTING MAGNIFYING GLASS}",
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
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
        await interaction.response.send_message(
            content=_(
                "If your opponent is lagging too much, you may ask for a TO to come and "
                "perform a lag test.\nPress the button below to confirm your action."
            ),
            view=view,
            ephemeral=True,
        )

        def check_same_user(inter):
            return inter.user.id == interaction.user.id

        try:
            x = await self.tournament.bot.wait_for(
                "interaction", check=check_same_user, timeout=60
            )
        except asyncio.TimeoutError:
            await interaction.followup.edit_message(
                "@original", content=_("Request timed out."), view=None
            )
            return
        custom_id = x.data.get("custom_id")
        if custom_id == f"no-{interaction.message.id}":
            await interaction.followup.edit_message("@original", content=_("Cancelled"), view=None)
            return
        msg = _(":satellite: **Lag report** : TOs are invited to check channel {channel}.").format(
            channel=self.match.channel.mention
        )
        if self.tournament.roles.tester:
            msg = f"{self.tournament.roles.tester.mention} {msg}"
            mentions = discord.AllowedMentions(roles=[self.tournament.roles.tester])
        else:
            mentions = None
        lag_channel = self.tournament.channels.lag or self.tournament.channels.to
        await lag_channel.send(msg, allowed_mentions=mentions)
        await interaction.followup.send(_("TOs were called. Prepare a new arena for them..."))


# Will be instanciated twice for stages and counterpicks
class StageListButton(Button):
    def __init__(self, tournament: "Tournament", type: StageListType):
        self.tournament = tournament
        if type == StageListType.STAGES:
            label = _("Stage list")
            emoji = "\N{CROSSED SWORDS}"
            text = _("__Legal stages:__") + "\n\n- " + "\n- ".join(tournament.settings.stages)
        else:
            label = _("Counterpicks list")
            emoji = "\N{SHIELD}"
            text = _("__Counters:__") + "\n\n- " + "\n- ".join(tournament.settings.counterpicks)
        self.text = list(pagify(text))
        super().__init__(style=discord.ButtonStyle.primary, label=label, emoji=emoji)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(self.text[0])
        # Send one message per page. I don't expect this to be abused to the point where more
        # than two pages have to be sent, as all stages have to be set at once with a command
        for page in self.text[1:]:
            await interaction.followup.send(page)
