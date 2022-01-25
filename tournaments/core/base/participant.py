import discord
import logging

from typing import TYPE_CHECKING, Optional

from redbot.core.i18n import Translator

if TYPE_CHECKING:
    from .match import Match
    from .tournament import Tournament

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)


class Participant(discord.Member):
    """
    Defines a participant in the tournament.

    This inherits from `discord.Member` and adds the necessary additional methods.

    If you're implementing this for a new provider, the following methods need to be implemented:

    *   `player_id` (may be a var or a property)
    *   `destroy`

    Parameters
    ----------
    member: discord.Member
        The member participating to the tournament
    tournament: Tournament
        The current tournament

    Attributes
    ----------
    member: discord.Member
        The member participating to the tournament
    tournament: Tournament
        The current tournament
    elo: int
        An integer representing the player's elo (seeding from braacket)
    checked_in: bool
        Defines if the member checked in
    match: Optional[Match]
        The player's current match. `None` if not in game.
    spoke: bool
        Defines if the member spoke once in his channel (used for AFK check)
    """

    def __init__(self, member: discord.Member, tournament: "Tournament"):
        # code from discord.Member._copy
        self._roles = discord.utils.SnowflakeList(member._roles, is_sorted=True)
        self.joined_at = member.joined_at
        self.premium_since = member.premium_since
        self._client_status = member._client_status.copy()
        self.guild = member.guild
        self.nick = member.nick
        self.activities = member.activities
        self._state = member._state
        # Reference will not be copied unless necessary by PRESENCE_UPDATE
        self._user = member._user
        # now our own stuff
        self.tournament = tournament
        self._player_id = None
        self.elo = None  # ranking and seeding stuff
        self.checked_in = False
        self.match: Optional["Match"] = None
        self.spoke = False  # True as soon as the participant sent a message in his channel
        # used to detect inactivity after the launch of a set

    def __repr__(self):
        return (
            "<Participant name={1.name!r} id={1.id} player_id={0.player_id} tournament_name={0.tournament.name} "
            "tournament_id={0.tournament.id} spoke={0.spoke}>"
        ).format(self, self._user)

    @classmethod
    def from_saved_data(cls, tournament: "Tournament", data: dict):
        member = tournament.guild.get_member(data["discord_id"])
        if member is None:
            log.warning(f"[Guild {tournament.guild.id}] Lost participant {data['discord_id']}")
            return None
        participant = cls(member, tournament)
        participant._player_id = data["player_id"]
        participant.spoke = data["spoke"]
        participant.checked_in = data["checked_in"]
        return participant

    def to_dict(self) -> dict:
        return {
            "discord_id": self.id,
            "player_id": self.player_id,
            "spoke": self.spoke,
            "checked_in": self.checked_in,
        }

    def reset(self):
        """
        Resets the `match` attribute to `None` and `spoke` to `False` (match ended).
        """
        self.match = None
        self.spoke = False

    async def check(self, send_dm: bool = True):
        """
        Checks the member in.

        In addition to changing the `checked_in` attribute, it also DMs the member
        and saves the config.
        """
        self.checked_in = True
        log.debug(f"[Guild {self.guild.id}] Player {self} registered.")
        await self.tournament.save()
        if not send_dm:
            return
        try:
            await self.send(
                _("You successfully checked in for the tournament **{name}**!").format(
                    name=self.tournament.name
                )
            )
        except discord.Forbidden:
            pass

    @property
    def player_id(self):
        """
        Returns an identifier for the player, specific to the bracket.

        This should be overwritten.
        """
        raise NotImplementedError

    async def destroy(self):
        """
        Removes the participant from the tournament.

        Represents an API call and should be overwritten.
        """
        raise NotImplementedError