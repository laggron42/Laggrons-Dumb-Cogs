import discord
import logging

from discord.components import SelectOption
from discord.ui import Button, Select, View

from typing import TYPE_CHECKING

from redbot.core.i18n import Translator

from .enums import EventPhase

if TYPE_CHECKING:
    from . import Tournament, Participant

_ = Translator("Tournaments", __file__)
log = logging.getLogger("red.laggron.tournaments")


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
