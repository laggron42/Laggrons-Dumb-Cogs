import discord
import logging

from typing import TYPE_CHECKING, Optional, List, Union

from redbot.core.i18n import Translator

from ..enums import MatchPhase

if TYPE_CHECKING:
    from .match import Match
    from .tournament import Tournament

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)


class Streamer:
    """
    Represents a streamer in the tournament. Will be assigned to matches. Does not necessarily
    exists on remote depending on the provider.

    There is no API call in this class *for now*.

    Parameters
    ----------
    tournament: Tournament
        The current tournament
    member: discord.Member
        The streamer on Discord. Must be in the tournament's guild.
    channel: str
        The streamer's channel. Must only be the last part of the URL, not full. (e.g. for
        https://twitch.tv/el_laggron use ``channel="el laggron"``)

    Attributes
    ----------
    tournament: Tournament
        The current tournament
    member: discord.Member
        The streamer on Discord. Must be in the tournament's guild.
    channel: str
        The streamer's channel. Must only be the last part of the URL, not full. (e.g. for
        https://twitch.tv/el_laggron use ``channel="el laggron"``)
    link: str
        The streamer's full channel URL
    room_id: str
        Streamer's room ID, specific to Smash Bros.
    room_code: str
        Streamer's room code, specific to Smash Bros.
    matches: List[Union[Match, int]]
        The list of matches in the streamer's queue. Can be `Match` if it exists (both players
        available, on hold) or `int`, representing the set.
    current_match: Optional[Match]
        The streamer's current match.
    """

    def __init__(
        self,
        tournament: "Tournament",
        member: discord.Member,
        channel: str,
        respect_order: bool = False,
    ):
        self.tournament = tournament
        self.member = member
        self.channel = channel
        self.respect_order = respect_order
        self.link = f"https://www.twitch.tv/{channel}/"
        self.room_id = None
        self.room_code = None
        self.matches: List[Union["Match", int]] = []
        self.current_match: Optional["Match"] = None

    @classmethod
    def from_saved_data(cls, tournament: "Tournament", data: dict):
        guild = tournament.guild
        member = guild.get_member(data["member"])
        if member is None:
            raise RuntimeError("Streamer member lost.")
        cls = cls(tournament, member, data["channel"], data["respect_order"])
        cls.room_id = data["room_id"]
        cls.room_code = data["room_code"]
        cls.matches = list(
            filter(
                None, [tournament.find_match(match_set=str(x))[1] or x for x in data["matches"]]
            )
        )
        for match in cls.matches:
            if not isinstance(match, int):
                match.streamer = cls
        if data["current_match"]:
            cls.current_match = tournament.find_match(match_set=str(data["current_match"]))[1]
        return cls

    def to_dict(self) -> dict:
        return {
            "member": self.member.id,
            "channel": self.channel,
            "respect_order": self.respect_order,
            "room_id": self.room_id,
            "room_code": self.room_code,
            "matches": [self.get_set(x) for x in self.matches],
            "current_match": self.get_set(self.current_match) if self.current_match else None,
        }

    def get_set(self, x):
        """
        Return the set number of a match in the streamer's queue. Accepts `Match` or `int`.

        Parameters
        ----------
        x: Union[Match, int]
            The match you need
        """
        return int(x.set) if hasattr(x, "set") else x

    def __str__(self):
        return self.link

    def set_room(self, room_id: str, code: Optional[str] = None):
        """
        Set streamer's room info (specific to Smash Bros.)

        Parameters
        ----------
        room_id: str
            Streamer's room ID
        code: Optional[str]
            Streamer's room code
        """
        self.room_id = room_id
        self.room_code = code

    async def check_integrity(self, sets: int, *, add: bool = False):
        """
        Verify if the list of sets provided is valid before adding them to the list.

        Parameters
        ----------
        sets: int
            The list of sets you want to check (and add). Only `int`, no `Match` instance.
        add: bool
            If you want to add the valid sets to the queue at the same time.

        Returns
        -------
        dict
            A dictionnary of the errors that occured (set -> translated error msg). If this is
            empty, it's all good.
        """
        errors = {}
        for _set in sets:
            if _set in [self.get_set(x) for x in self.matches]:
                errors[_set] = _("You already have that set in your queue.")
                continue
            for streamer in self.tournament.streamers:
                if _set in [self.get_set(x) for x in streamer.matches]:
                    errors[_set] = _(
                        "That set already has a streamer defined *(<{streamer}>)*."
                    ).format(streamer=streamer)
                    continue
            match = self.tournament.find_match(match_set=str(_set))[1]
            if match:
                if match.phase == MatchPhase.DONE:
                    errors[_set] = _("That match is finished.")
                    continue
                if add is False:
                    continue
                match.streamer = self
                if match.phase == MatchPhase.ONGOING:
                    # match is ongoing, we have to tell players
                    if self.matches:
                        # match has to be paused
                        match.phase = MatchPhase.ON_HOLD
                    await match.stream_queue_add()
            if add:
                self.matches.append(match or _set)
        return errors

    async def add_matches(self, *sets):
        """
        Add matches to the streamer's queue.

        Parameters
        ----------
        *sets: Union[Match, int]
            The matches you want to add.
        """
        self.matches.extend(*sets)

    async def remove_matches(self, *sets: int):
        """
        Remove a list of matches from the streamer's queue.

        Parameters
        ----------
        *sets: int
            The list of sets you want to remove. Only `int`, no `Match` instance.

        Raises
        ------
        KeyError
            The list was unchanged.
        """
        new_list = []
        to_remove = []
        for match in self.matches:
            if self.get_set(match) in sets:
                to_remove.append(match)
            else:
                new_list.append(match)
        if not to_remove:
            raise KeyError("None of the given sets found.")
        else:
            self.matches = new_list
        for match in to_remove:
            if isinstance(match, Match):
                await match.cancel_stream()
                if match == self.current_match:
                    self.current_match = None

    def swap_match(self, set1: int, set2: int):
        """
        Swap the position of two matches in the streamer's queue.

        Parameters
        ----------
        set1: int
            The first set.
        set2: int
            The second set.

        Raises
        ------
        KeyError
            One or more sets not found
        """
        try:
            i1, match1 = next(
                filter(lambda x: set1 == self.get_set(x[1]), enumerate(self.matches))
            )
            i2, match2 = next(
                filter(lambda x: set2 == self.get_set(x[1]), enumerate(self.matches))
            )
        except StopIteration as e:
            raise KeyError("One set not found.") from e
        self.matches[i1] = match2
        self.matches[i2] = match1

    def insert_match(self, set: int, *, set2: int = None, position: int = None):
        """
        Insert a match in the list. The match must already exist in the list.

        Provide either ``set2`` or ``position`` as keyword argument.

        Parameters
        ----------
        set: int
            The set you want to move. Only `int` type, not `Match`.
        set2: int
            The set you want to use to define the position. Only `int` type, not `Match`.
        position: int
            The new position in the list. 0 = first ; 1 = second ...

            Providing a number out of bounds will move the item at the limit, it's just *Python's
            magic*. (eg: -5 moves to first place)

        Raises
        ------
        KeyError
            The given set was not found
        RuntimeError
            Neither ``set2`` or ``position`` was provided.
        """
        if set2 is None and position is None:
            raise RuntimeError("Provide set2 or position.")
        try:
            i, match = next(filter(lambda x: set == self.get_set(x[1]), enumerate(self.matches)))
            if set2:
                position = next(
                    filter(lambda x: set2 == self.get_set(x[1]), enumerate(self.matches))
                )[0]
        except StopIteration as e:
            raise KeyError("One set not found.") from e
        del self.matches[i]
        self.matches.insert(position, match)

    async def end(self):
        """
        Cancels all streams for the streamer's queue, telling the players.

        Basically calls `Match.cancel_stream` for existing matches.
        """
        for match in filter(lambda x: isinstance(x, Match), self.matches):
            await match.cancel_stream()

    def _update_list(self):
        matches = []
        for match in self.matches:
            if isinstance(match, Match):
                matches.append(match)
                continue
            match_object = self.tournament.find_match(match_set=str(match))[1]
            if match_object:
                if match_object.phase != MatchPhase.PENDING:
                    continue
                match_object.streamer = self
                matches.append(match_object)
            else:
                matches.append(match)
        self.matches = matches
        if self.current_match:
            if self.current_match.phase != MatchPhase.DONE:
                return  # wait for it to end
            try:
                self.matches.remove(self.current_match)
            except ValueError:
                pass
        self.current_match = None
        try:
            next_match = self.matches[0]
        except IndexError:
            return
        if isinstance(next_match, int):
            return
        self.current_match = next_match
