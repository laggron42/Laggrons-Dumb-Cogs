from __future__ import annotations
from copy import copy

import discord
import logging
import asyncio
import aiohttp
import contextlib
import aiofiles
import aiofiles.os
import filecmp
import csv
import shutil

from discord.ext import tasks
from random import choice, shuffle
from itertools import islice
from datetime import datetime, timedelta, timezone
from babel.dates import format_date, format_time
from typing import Optional, Tuple, List, Union

from redbot import __version__ as red_version
from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.i18n import Translator, get_babel_locale, set_contextual_locales_from_guild
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import pagify

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)

MAX_ERRORS = 5
TIME_UNTIL_CHANNEL_DELETION = 300
TIME_UNTIL_TIMEOUT_DQ = 300


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

    def __init__(self, member: discord.Member, tournament: Tournament):
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
        self.match: Optional[Match] = None
        self.spoke = False  # True as soon as the participant sent a message in his channel
        # used to detect inactivity after the launch of a set

    def __repr__(self):
        return (
            "<Participant player_id={0.player_id} tournament_name={0.tournament.name} "
            "tournament_id={0.tournament.id} spoke={0.spoke} id={1.id} name={1.name!r}>"
        ).format(self, self._user)

    @classmethod
    def from_saved_data(cls, tournament: Tournament, data: dict):
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


class Match:
    """
    Defines a match in the tournament, with two players facing each other.

    This should only be created when convenient, aka when a match needs to be started. Matches
    with no players yet or finished are not builded.

    If you're implementing this for a new provider, the following methods need to be implemented:

    *   `set_scores`
    *   `mark_as_underway`
    *   `unmark_as_underway` (unused for now)

    Parameters
    ----------
    tournament: Tournament
        The match's tournament.
    round: str
        The round of this match in the bracket (e.g. 1 for first round of winner bracket, -1 for
        first round of loser bracket).
    set: str
        The number of the match. Challonge calls this the suggested play order (goes from 1 to N,
        the number of matches in the bracket).
    id: int
        A unique identifier for the API
    underway: bool
        If the match is underway (provided by API)
    player1: Participant
        The first player of this match.
    player2: Participant
        The second player of this match.

    Attributes
    ----------
    tournament: Tournament
        The match's tournament.
    round: str
        The round of this match in the bracket (e.g. 1 for first round of winner bracket, -1 for
        first round of loser bracket).
    set: str
        The number of the match. Challonge calls this the suggested play order (goes from 1 to N,
        the number of matches in the bracket).
    id: int
        A unique identifier for the API
    player1: Participant
        The first player of this match.
    player2: Participant
        The second player of this match.
    channel: Optional[discord.TextChannel]
        The channel for this match. May be `None` if the match hasn't started yet, or if it
        couldn't be created and is therefore in DM.
    start_time: Optional[datetime]
        Start time of this match. `None` if it hasn't started yet.
    end_time: Optional[datetime]
        End time of this match, or time of the latest message. `None` if it hasn't started or
        ended yet. This is updated as soon as a message is sent in the channel. Used for knowing
        when to delete the channel (5 min after last message).
    status: str
        Defines the current state of the match.

        *   ``"pending"``: Waiting to be launched (no channel or stream pending)
        *   ``"ongoing"``: Match started
        *   ``"finished"``: Score set, awaiting channel deletion
    warned: Optional[Union[datetime, bool]]
        Defines if there was a warn for duration. `None` if no warn was sent, `datetime.datetime`
        if there was one first warn sent (correspond to the time when it was send, we rely on that
        to know when to send the second warn), and finally `True` when the second warn is sent
        (to the T.O.s).
    streamer: Optional[Streamer]
        The streamer assigned to this match, if any.
    on_hold: bool
        `True` if the match is not started but on hold, awaiting something (most likely inside a
        stream queue, waiting for its turn)
    is_top8: bool
        `True` if the match is in the top 8 of the tournament
    is_bo5: bool
        `True` if the match is in BO5 format instead of BO3
    round_name: str
        Name of the round (ex: Winner semi-finals, Loser round -2)
    checked_dq: bool
        If we performed AFK checks. Setting this to `True` is possible and will disable further
        AFK checks for this match.
    """

    def __init__(
        self,
        tournament: Tournament,
        round: int,
        set: str,
        id: int,
        underway: bool,
        player1: Participant,
        player2: Participant,
    ):
        self.guild: discord.Guild = tournament.guild
        self.tournament = tournament
        self.round = round
        self.set = set
        self.id = id
        self.underway = underway
        self.player1 = player1
        self.player2 = player2
        self.channel: Optional[discord.TextChannel] = None
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.status = "pending"  # can be "pending" "ongoing" "finished"
        self.warned: Optional[Union[datetime, bool]] = None
        # time of the first warn for duration, if any. if a second warn was sent, set to True
        self.streamer: Optional[Streamer] = None
        self.on_hold = False  # True if this is match is awaiting for a stream
        # one or more players can be None
        # if this is the case, the bot will most likely close the match right after this
        with contextlib.suppress(AttributeError):
            player1.match = self
            player2.match = self
        self.is_top8 = (
            round >= tournament.top_8["winner"]["top8"]
            or round <= tournament.top_8["loser"]["top8"]
        )
        self.is_bo5 = (
            round >= tournament.top_8["winner"]["bo5"] or round <= tournament.top_8["loser"]["bo5"]
        )
        self.round_name = self._get_name()
        self.checked_dq = True if self.is_top8 else False

    def __repr__(self):
        return (
            "<Match status={0.status} round={0.round} set={0.set} id={0.id} underway={0.underway} "
            "channel={0.channel} start={0.start_time} tournament={0.tournament.name} "
            "guild_id={0.guild.id} player1={0.player1.name} player2={0.player2.name}>"
        ).format(self)

    def __del__(self):
        if self.streamer is not None:
            self.streamer.current_match = None
            try:
                self.streamer.matches.remove(self)
            except ValueError:
                pass
        if self.tournament.cancelling is False and self.channel:
            channel = self.guild.get_channel(self.channel.id)
            if channel is not None:
                log.warning(
                    f"[Guild {self.guild.id}] Set {self.set} removed from memory while "
                    f"the text channel with ID {channel.id} still exists."
                )

    @property
    def duration(self) -> Optional[timedelta]:
        """
        Returns the duration of this match, or `None` if it hasn't started.
        """
        if self.start_time:
            return datetime.now(self.tournament.tz) - self.start_time

    @classmethod
    def from_saved_data(cls, tournament: Tournament, player1, player2, data: dict) -> Match:
        match = cls(
            tournament, data["round"], data["set"], data["id"], data["underway"], player1, player2
        )
        match.channel = tournament.guild.get_channel(data["channel"])
        warned = data["warned"]
        if isinstance(warned, bool) or warned is None:
            match.warned = warned
        else:
            match.warned = datetime.fromtimestamp(warned, tz=tournament.tz)
        match.on_hold = bool(data["on_hold"])
        match.status = data["status"]
        match.checked_dq = data["checked_dq"]
        match.start_time = (
            datetime.fromtimestamp(data["start_time"], tz=tournament.tz)
            if data["start_time"]
            else None
        )
        match.end_time = (
            datetime.fromtimestamp(data["end_time"], tz=tournament.tz)
            if data["end_time"]
            else None
        )
        return match

    def to_dict(self) -> dict:
        return {
            "round": self.round,
            "set": self.set,
            "id": self.id,
            "underway": self.underway,
            "player1": self.player1.player_id,
            "player2": self.player2.player_id,
            "channel": self.channel.id if self.channel else None,
            "start_time": self.start_time.timestamp() if self.start_time else None,
            "end_time": self.end_time.timestamp() if self.end_time else None,
            "status": self.status,
            "checked_dq": self.checked_dq,
            "warned": self.warned.timestamp()
            if isinstance(self.warned, datetime)
            else self.warned,
            "on_hold": self.on_hold,
        }

    def _get_name(self) -> str:
        if self.round > 0:
            max_round = self.tournament.top_8["winner"]["top8"] + 2
            return {
                max_round: _("Grand Final"),
                max_round - 1: _("Winners Final"),
                max_round - 2: _("Winners Semi-Final"),
                max_round - 3: _("Winners Quarter-Final"),
            }.get(self.round, _("Winners round {round}").format(round=self.round))
        elif self.round < 0:
            max_round = self.tournament.top_8["loser"]["top8"] - 3
            return {
                max_round: _("Losers Final"),
                max_round + 1: _("Losers Semi-Final"),
                max_round + 2: _("Losers Quarter-Final"),
            }.get(self.round, _("Losers round {round}").format(round=self.round))

    async def _dm_players(self, message: str):
        players = (self.player1, self.player2)
        for player in players:
            try:
                await player.send(message)
            except discord.HTTPException as e:
                log.warning(f"Can't send a DM to {str(player)} for his set.", exc_info=e)

    async def send_message(self, reset: bool = False) -> bool:
        """
        Send a message in the created channel.

        Parameters
        ----------
        reset: bool
            ``True`` if the match is started because of a reset.

        Returns
        -------
        bool
            ``False`` if the message couldn't be sent, and was sent in DM instead.
        """
        if reset is True:
            message = _(
                ":warning: **The bracket was modified!** This results in this match having to be "
                "replayed. Please check your new position on the bracket.\n\n"
            )
        else:
            message = ""
        top8 = _("**(top 8)** :fire:") if self.is_top8 else ""
        message += _(
            ":arrow_forward: **{0.set}** : {0.player1.mention} vs {0.player2.mention} {top8}\n"
        ).format(self, top8=top8)
        if self.tournament.ruleset_channel:
            message += _(
                ":white_small_square: The rules must follow the ones given in {channel}\n"
            ).format(channel=self.tournament.ruleset_channel.mention)
        if self.tournament.stages:
            message += _(
                ":white_small_square: The list of legal stages "
                "is available with `{prefix}stages` command.\n"
            ).format(prefix=self.tournament.bot_prefix)
        if self.tournament.counterpicks:
            message += _(
                ":white_small_square: The list of counter stages "
                "is available with `{prefix}counters` command.\n"
            ).format(prefix=self.tournament.bot_prefix)
        score_channel = (
            _("in {channel}").format(channel=self.tournament.scores_channel.mention)
            if self.tournament.scores_channel
            else ""
        )
        message += _(
            ":white_small_square: In case of lag making the game unplayable, use the "
            "`{prefix}lag` command to call the T.O. and solve the problem.\n"
            ":white_small_square: **As soon as the set is done**, the winner sets the "
            "score {score_channel} with the `{prefix}win` command.\n"
            ":arrow_forward: You will play this set as a {type}.\n"
        ).format(
            prefix=self.tournament.bot_prefix,
            score_channel=score_channel,
            type=_("**BO5** *(best of 5)*") if self.is_bo5 else _("**BO3** *(best of 3)*"),
        )
        if self.tournament.baninfo:
            chosen_player = choice([self.player1, self.player2])
            message += _(
                ":game_die: **{player}** was picked to begin the bans *({baninfo})*.\n"
            ).format(player=chosen_player.mention, baninfo=self.tournament.baninfo)
        if self.streamer is not None and self.on_hold is True:
            message += _(
                "**\nYou will be on stream on {streamer}!**\n"
                ":warning: **Do not play your set for now and wait for your turn.** "
                "I will send a message once it is your turn with instructions."
            ).format(streamer=self.streamer.link)
            # else, we're about to send another message with instructions

        async def send_in_dm():
            nonlocal message
            message += _(
                "\n\n**You channel can't be created because of a problem. "
                "Do your set in DM and come back to set the result.**"
            )
            await self._dm_players(message)

        if self.channel is None:
            await send_in_dm()
            result = False
        else:
            try:
                await self.channel.send(message)
            except discord.HTTPException as e:
                log.error(
                    f"[Guild {self.guild.id}] Can't create a channel for the set {self.set}",
                    exc_info=e,
                )
                await send_in_dm()
                result = False
            else:
                result = True
        self.tournament.matches_to_announce.append(
            _(
                ":arrow_forward: **{name}** ({bo_type}): {player1} vs {player2}"
                "{on_stream} {top8} {channel}."
            ).format(
                name=self.round_name,
                bo_type=_("BO5") if self.is_bo5 else _("BO3"),
                player1=self.player1.mention,
                player2=self.player2.mention,
                on_stream=_(" **on stream!**") if self.streamer else "",
                top8=top8,
                channel=_("in {channel}").format(channel=self.channel.mention)
                if result is True
                else _("in DM"),
            )
        )
        return result

    async def start_stream(self):
        """
        Send a pending set, awaiting for its turn, on stream. Only call this if there's a streamer.
        """
        destination = self.channel.send if self.channel else self._dm_players
        if self.streamer.room_id:
            access = _("\n\nHere are the access codes:\nID: {id}\nPasscode: {passcode}").format(
                id=self.streamer.room_id, passcode=self.streamer.room_code
            )
        else:
            access = ""
        if self.status != "ongoing":
            await self._start()
        self.on_hold = False
        self.checked_dq = True
        await destination(
            _("You can go on stream on {channel} !{access}").format(
                channel=self.streamer.link, access=access
            )
        )
        if self.tournament.stream_channel:
            await self.tournament.stream_channel.send(
                _(
                    ":arrow_forward: Sending set {set} ({name}) on stream "
                    "with **{streamer}**: {player1} vs {player2}"
                ).format(
                    set=self.set,
                    name=self._get_name(),
                    streamer=self.streamer.channel,
                    player1=self.player1.mention,
                    player2=self.player2.mention,
                ),
                allowed_mentions=discord.AllowedMentions(users=False),
            )

    async def stream_queue_add(self):
        """
        Modify the status of an ongoing match to tell that it is now on stream.

        This is called when a streamer adds an ongoing match to its queue, then the following
        things are done:

        *   AFK checks are cancelled

        *   **If the match is the first one in the stream queue:** Nothing is cancelled, we just
            ping the players with the stream informations.

        *   **If the match is not the first one in the stream queue:** We mark the match as not
            underway, change the status to pending, and tell the players.
        """
        destination = self.channel.send if self.channel else self._dm_players
        self.checked_dq = True
        if self.on_hold is True:
            self.status = "pending"
            self.start_time = None
            self.underway = False
            await destination(
                _(
                    "{player1} {player2}\n"
                    ":warning: Your match was just added to {channel}'s stream queue ({link})\n"
                    "**You must stop playing now and wait for your turn.** "
                    "Sorry for this sudden change, please contact a T.O. if you have a question."
                ).format(
                    player1=self.player1.mention,
                    player2=self.player2.mention,
                    channel=self.streamer.channel,
                    link=self.streamer.link,
                )
            )
            try:
                await asyncio.wait_for(self.unmark_as_underway(), timeout=60)
            except Exception as e:
                log.warning(
                    f"[Guild {self.guild.id}] Can't unmark set {self.set} as underway.", exc_info=e
                )
                await self.tournament.to_channel.send(
                    _(
                        "There was an issue unmarking set {set} as underway. The bracket may not "
                        "display correct informations, but this isn't critical at all.\n"
                        "Players may have issues setting their score, "
                        "you can set that manually on the bracket."
                    ).format(set=self.channel.mention if self.channel else f"#{self.set}")
                )
                await destination(
                    _(
                        "There was an issue unmarking your set as underway. The bracket may not "
                        "display correct informations, but this isn't critical.\n"
                        "If you encounter an issue setting your score, contact a T.O."
                    )
                )
        else:
            if self.streamer.room_id:
                access = _(
                    "\n\nHere are the access codes:\nID: {id}\nPasscode: {passcode}"
                ).format(id=self.streamer.room_id, passcode=self.streamer.room_code)
            else:
                access = ""
            await destination(
                _(
                    "{player1} {player2}\n"
                    ":warning: Your match was just added to {channel}'s stream ({link}).\n"
                    "**You must now play on stream!**{access}"
                ).format(
                    player1=self.player1.mention,
                    player2=self.player2.mention,
                    channel=self.streamer.channel,
                    link=self.streamer.link,
                    access=access,
                )
            )

    async def cancel_stream(self):
        """
        Call if the stream is cancelled (streamer left of match removed from queue).

        A message will be sent, telling players to start playing, and AFK checks will be
        re-enabled.
        """
        destination = self.channel.send if self.channel else self._dm_players
        self.streamer = None
        self.on_hold = False
        await self._start()
        await destination(
            _(
                "{player1} {player2} The stream was cancelled. You can start/continue "
                "your match normally.\n:warning: AFK checks are re-enabled."
            ).format(player1=self.player1.mention, player2=self.player2.mention)
        )

    async def create_channel(
        self, category: discord.CategoryChannel, *allowed_roles: list
    ) -> discord.TextChannel:
        """
        Creates a channel for the match and returns its object.

        Returns
        -------
        discord.TextChannel
            The created text channel
        """
        overwrites = {
            self.guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True
            ),
            self.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            self.player1: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            self.player2: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        for role in allowed_roles:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        return await self.guild.create_text_channel(
            self.set, category=category, overwrites=overwrites, reason=_("Set launch")
        )

    async def _start(self):
        target = self.channel.send if self.channel else self._dm_players
        self.status = "ongoing"
        self.underway = True
        self.checked_dq = False
        self.start_time = datetime.now(self.tournament.tz)
        try:
            await asyncio.wait_for(self.mark_as_underway(), timeout=60)
        except Exception as e:
            log.warning(
                f"[Guild {self.guild.id}] Can't mark set {self.set} as underway.", exc_info=e
            )
            await self.tournament.to_channel.send(
                _(
                    "There was an issue marking set {set} as underway. The bracket may not "
                    "display correct informations, but this isn't critical at all.\n"
                    "Players may have issues setting their score, "
                    "you can set that manually on the bracket."
                ).format(set=self.channel.mention if self.channel else f"#{self.set}")
            )
            await target(
                _(
                    "There was an issue marking your set as underway. The bracket may not "
                    "display correct informations, but you can play as usual for now.\n"
                    "If you encounter an issue setting your score, contact a T.O."
                )
            )

    async def launch(
        self,
        *,
        category: Optional[discord.CategoryChannel] = None,
        restart: bool = False,
        allowed_roles: List[discord.Role] = [],
    ):
        """
        Launches the set.

        This does the following:

        *   Try to create a text channel with permissions for the two players and the given roles
        *   Send a DM to both members
        *   Mark the set as ongoing

        Parameters
        ----------
        category: Optional[discord.CategoryChannel]
            The category where to put the channel. If this is not provided, one will be found.
            If you're launching multiple sets at once with asyncio.gather, use this to prevent
            seeing one category per channel
        restart: bool
            If the match is restarted.
        allowed_roles: List[discord.Role]
            A list of roles with read_messages permission in the text channel.
        """
        if category is None:
            category = await self.tournament._get_available_category(
                "winner" if self.round > 0 else "loser"
            )
        allowed_roles = list(allowed_roles)
        allowed_roles.extend(self.tournament.allowed_roles)
        try:
            channel = await self.create_channel(category, *allowed_roles)
        except discord.HTTPException as e:
            log.error(
                f"[Guild {self.guild.id}] Couldn't create a channel for the set {self.set}.",
                exc_info=e,
            )
        else:
            self.channel = channel
        await self.send_message(reset=restart)
        if self.on_hold is False:
            await self._start()
            if self.streamer is not None:
                await self.start_stream()

    async def relaunch(self):
        """
        This is called in case of a match reset (usually from remote).

        We inform the players they need to play their set again, eventually re-use their old
        channel if it still exists.
        """
        if self.channel is not None:
            await self.mark_as_underway()
            self.status = "ongoing"
            await self.channel.send(
                _(
                    "{player1} {player2}\n"
                    ":warning: The score of this set was reset on the bracket. "
                    "Therefore, **the set must be replayed**. Ask the T.O. if you have "
                    "questions or believe this is a mistake."
                ).format(player1=self.player1.mention, player2=self.player2.mention)
            )
            self.underway = True
            self.start_time = datetime.now(self.tournament.tz)
        else:
            await self.launch(restart=True)

    async def check_inactive(self):
        """
        Checks for inactive players (reads `Participant.spoke` only), and DQ them if required.

        .. warning:: This doesn't check durations and assumes it's been done already.

        Will set `checked_dq` to `True`.
        """
        self.checked_dq = True
        players = (self.player1, self.player2)
        if all((x.spoke is False for x in players)):
            log.debug(
                f"[Guild {self.guild.id}] Both players inactive, DQing "
                f"both and cancelling set #{self.set}."
            )
            await self.player1.destroy()
            await self.player2.destroy()
            try:
                await self.channel.delete()
            except discord.HTTPException as e:
                log.warn(
                    f"[Guild {self.guild.id}] Can't delete set channel #{self.set}.", exc_info=e
                )
            await self.tournament.to_channel.send(
                _(
                    ":information_source: **Automatic DQ** of {player1} and {player2} for "
                    "inactivity, the set #{set} is cancelled."
                ).format(player1=self.player1.mention, player2=self.player2.mention, set=self.set)
            )
            self.channel = None
            self.cancel()
            return
        for player in players:
            if player.spoke is False:
                log.debug(
                    f"[Guild {self.guild.id}] DQing player {player} "
                    f"for inactivity (set #{self.set})"
                )
                await player.destroy()
                await self.channel.send(
                    _(":timer: **Automatic DQ of {player} for inactivity.**").format(
                        player=player.mention
                    )
                )
                await self.tournament.to_channel.send(
                    _(
                        ":information_source: **Automatic DQ** of {player} "
                        "for inactivity, set #{set}."
                    ).format(player=player.mention, set=self.set)
                )
                try:
                    await player.send(
                        _(
                            "Sorry, you were disqualified from this tournament "
                            "because you weren't active in your channel. Contact the T.O. "
                            "if you believe this is a mistake."
                        )
                    )
                except discord.HTTPException:
                    # blocked or DMs not allowed
                    pass
                self.cancel()
                break

    async def warn_length(self):
        """
        Warn players in their channels because of the duration of their match.
        """
        target = self.channel.send or self._dm_players
        message = _(
            ":warning: This match is taking a lot of time!\n"
            "As soon as this is finished, set your score with `{prefix}win`{channel}."
        ).format(
            prefix=self.tournament.bot_prefix,
            channel=_(" in {channel}").format(channel=self.tournament.scores_channel.mention)
            if self.tournament.scores_channel
            else "",
        )
        time = self.tournament.time_until_warn["bo5" if self.is_bo5 else "bo3"][1]
        if time:
            message += _(
                "\nT.O.s will be warned if this match is still ongoing in {time} minutes."
            ).format(time=time)
        try:
            await target(message)
        except discord.NotFound:
            self.channel = None
        self.warned = datetime.now(self.tournament.tz)

    async def warn_to_length(self):
        """
        Warn T.O.s because of the duration of this match. Also tell the players
        """
        await self.tournament.to_channel.send(
            _(
                ":warning: The set {set} is taking a lot of time (now open since {time} minutes)."
            ).format(
                set=self.channel.mention
                if self.channel
                else _("#{set} (in DM)").format(set=self.set),
                time=round(self.duration.total_seconds() // 60),
            )
        )
        self.warned = True
        target = self.channel.send or self._dm_players
        await target(_("Your match is taking too much time, T.O.s were warned."))

    async def end(self, player1_score: int, player2_score: int, upload: bool = True):
        """
        Set the score and end the match.

        The winner is determined by comparing the two scores (defaults to player 1 if equal).

        Parameters
        ----------
        player1_score: int
            First player's score.
        player2_score: int
            Second player's score.
        upload: bool
            If the score should be uploaded to the bracket. Set `False` to only send the message
            with a note "score set on bracket" added. Defaults to `True`.
        """
        if upload is True:
            await self.set_scores(player1_score, player2_score)
        self.cancel()
        winner = self.player1 if player1_score > player2_score else self.player2
        score = (
            f"{player1_score}-{player2_score}"
            if player1_score > player2_score
            else f"{player2_score}-{player1_score}"
        )
        if self.channel is not None:
            await self.channel.send(
                _(
                    ":bell: __Score reported__ : **{winner}** wins{score} !\n"
                    "*In case of a problem, call a T.O. to fix the score.*\n"
                    "*Note : this channel will be deleted after 5 minutes of inactivity.*{remote}"
                ).format(
                    winner=winner.mention,
                    score=f" **{score}**" if player1_score + player2_score > 0 else "",
                    remote=_("\n\n:information_source: The score was directly set on the bracket.")
                    if upload is False
                    else "",
                )
            )

    async def force_end(self):
        """
        Called when a set is cancelled (remove bracket modifications or reset).

        The channel is deleted, a DM is sent, and the instance will most likely be deleted soon
        after.
        """
        self.player1.reset()
        self.player2.reset()
        for player in (self.player1, self.player2):
            try:
                await player.send(
                    _(
                        ":warning: **Your set is cancelled!** This is probably because of "
                        "manual bracket modifications.\nCheck the bracket, and contact a T.O. "
                        "if you believe this is a problem."
                    )
                )
            except discord.HTTPException:
                pass
        if self.channel is not None:
            try:
                await self.channel.delete(
                    reason=_(
                        "Remote returned a different match list, or the bracket was reset. I am "
                        "therefore clearing the outdated matches. Check the bracket for details."
                    )
                )
            except discord.HTTPException as e:
                log.warn(
                    f"[Guild {self.guild.id}] Can't delete set channel #{self.set}.", exc_info=e
                )

    async def disqualify(self, player: Union[Participant, int]):
        """
        Called when a player in the set is destroyed.

        There is no API call, just messages sent to the players.

        player: Union[Participant, int]
            The disqualified player. Provide an `int` if the member left.
        """
        self.cancel()
        if isinstance(player, int):
            winner = (
                self.player1
                if self.player1 is not None and self.player1.player_id != player
                else self.player2
            )
            player = _("Player with ID {id} (lost on Discord) ").format(id=player)
        else:
            winner = self.player1 if self.player1.id != player.id else self.player2
            player = _("Player {player}").format(player=player.mention)
        if self.channel is not None:
            await self.channel.send(
                _(
                    "{player} disqualified from the tournament.\n"
                    "{winner.mention} is winning this set!"
                ).format(player=player, winner=winner)
            )
        else:
            try:
                await winner.send(
                    _(
                        "Your opponent was disqualified from the tournament.\n"
                        "You are winning this set!"
                    )
                )
            except discord.HTTPException:
                pass

    async def forfeit(self, player: Participant):
        """
        Called when a player in the set forfeits this match.

        This doesn't always mean that the player quits the tournament, he may continue in the
        loser bracker.

        Sets a score of -1 0

        Parameters
        ----------
        player: Participant
            The player that forfeits.
        """
        if player.id == self.player1.id:
            score = (-1, 0)
        else:
            score = (0, -1)
        await self.set_scores(*score)
        self.cancel()
        winner = self.player1 if self.player1.id != player.id else self.player2
        if self.channel is not None:
            await self.channel.send(
                _(
                    "Player {player.mention} forfeits this set.\n{winner.mention} is winning!"
                ).format(player=player, winner=winner)
            )
        else:
            try:
                await winner.send(_("Your opponent forfeited.\nYou are winning this set!"))
            except discord.HTTPException:
                pass

    def cancel(self):
        """
        Mark a match as finished (updated `status` and `end_time` + calls `Participant.reset`)
        """
        with contextlib.suppress(AttributeError):
            self.player1.reset()
            self.player2.reset()
        self.status = "finished"
        self.end_time = datetime.now(self.tournament.tz)

    async def set_scores(
        self, player1_score: int, player2_score: int, winner: Optional[Participant] = None
    ):
        """
        Set the score for the set.

        Parameters
        ----------
        player1_score: int
            The score of the first player.
        player2_score: int
            The score of the second player.
        winner: Optional[Participant]
            The winner of the set. If not provided, the player with the highest score will be
            selected.
        """
        raise NotImplementedError

    async def mark_as_underway(self):
        """
        Marks the match as underway.
        """
        raise NotImplementedError

    async def unmark_as_underway(self):
        """
        Unmarks the match as underway.

        This shouldn't ever be needed, just here in case of.
        """
        raise NotImplementedError


class Tournament:
    """
    Represents a tournament in a guild.

    This object is created as soon as the tournament is setup, and destroyed only once it ends.

    The config is loaded inside and will not be updated unless reloaded.

    This contains all of the methods useful for the tournament, a list of `Participant` and a list
    of `Match`, and a `discord.ext.tasks.Loop` task updating the infos from the bracket.

    This contains the base structure, but no interface with a bracket, this has to be implemented
    later by inheriting from this class and overwriting the abstract methods, allowing multiple
    providers to work with the same structure.

    If you're implementing this for a new provider, the following methods need to be implemented:

    *   `_get_all_rounds`
    *   `_update_match_list`
    *   `_update_participants_list`
    *   `start`
    *   `stop`
    *   `add_participant`
    *   `add_participants`
    *   `destroy_player`
    *   `list_participants`
    *   `list_matches`
    *   `reset`

    And set the following class vars with your other inherited objects for `Participant` and
    `Match` :

    *   `match_object`
    *   `participant_object`

    See ``challonge.py`` for an example.

    Parameters
    ----------
    bot: redbot.core.bot.Red
        The bot object
    guild: discord.Guild
        The current guild for the tournament
    config: redbot.core.Config
        The cog's Config object
    name: str
        Name of the tournament
    game: str
        Name of the game
    url: str
        Link of the bracket
    id: str
        Internal ID for the tournament
    limit: Optional[int]
        An optional limit of participants
    status: str
        The status provided by the API
    tournament_start: datetime.datetime
        Expected start time for this tournament. Planned events are based on this.
    bot_prefix: str
        A prefix to use for displaying commands without context.
    cog_version: str
        Current version of Tournaments
    data: dict
        A dict with all the config required for the tournament (combines guild and game settings)

    Attributes
    ----------
    bot: redbot.core.bot.Red
        The bot object
    guild: discord.Guild
        The current guild for the tournament
    config: redbot.core.Config
        The cog's Config object
    name: str
        Name of the tournament
    game: str
        Name of the game
    url: str
        Link of the bracket
    id: str
        Internal ID for the tournament
    limit: Optional[int]
        An optional limit of participants
    status: str
        The status provided by the API
    tournament_start: datetime.datetime
        Expected start time for this tournament. Planned events are based on this.
    tz: datetime.tzinfo
        The timezone of the tournament. You need to use this when creating datetime objects.

        .. code-block:: python

            from datetime import datetime
            now = datetime.now(tz=tournament.tz)
    bot_prefix: str
        A prefix to use for displaying commands without context.
    cog_version: str
        Current version of Tournaments
    participants: List[Participant]
        List of participants in the tournament
    matches: List[Match]
        List of open matches in the tournament
    streamers: List[Streamer]
        List of streamers in the tournament
    winner_categories: List[discord.CategoryChannel]
        List of categories created for the winner bracket
    loser_categories: List[discord.CategoryChannel]
        List of categories created for the loser bracket
    category: Optional[discord.CategoryChannel]
        The category defined (our categories will be created below)
    announcements_channel: Optional[discord.TextChannel]
        The channel for announcements
    checkin_channel: Optional[discord.TextChannel]
        The channel for check-in
    queue_channel: Optional[discord.TextChannel]
        The channel for match queue
    register_channel: Optional[discord.TextChannel]
        The channel for registrations
    scores_channel: Optional[discord.TextChannel]
        The channel for score setting
    stream_channel: Optional[discord.TextChannel]
        The channel for announcing matches on stream
    to_channel: discord.TextChanne]
        The channel for tournament organizers. Send warnings there.
    vip_register_channel: Optional[discord.TextChannel]
        A channel where registrations are always open
    participant_role: discord.Role
        The role given to participants
    streamer_role: Optional[discord.Role]
        Role giving access to stream commands
    to_role: Optional[discord.Role]
        Role giving access to T.O. commands
    credentials: dict
        Credentials for connecting to the bracket
    delay: int
        Time in minutes until disqualifying a participant for AFK
    time_until_warn: dict
        Represents the different warn times for duration
    autostop_register: bool
        Should the bot close registrations when it's full?
    ignored_events: list
        A list of events to ignore (checkin/register start/stop)
    register_start: Optional[datetime.datetime]
        When we should open the registrations automatically
    register_second_start: Optional[datetime.datetime]
        When we should open the registrations a second time automatically
    register_stop: Optional[datetime.datetime]
        When we should close the registrations automatically
    checkin_start: Optional[datetime.datetime]
        When we should open the checkin automatically
    checkin_stop: Optional[datetime.datetime]
        When we should close the checkin automatically
    ruleset_channel: Optional[discord.TextChannel]
        Channel for the rules
    game_role: Optional[discord.Role]
        Role targeted at players for this game. Basically we use that role when opening the
        registrations, for opening the channel and pinging.
    baninfo: Optional[str]
        Baninfo set (ex: 3-4-2)
    ranking: dict
        Data for braacket ranking
    stages: List[str]
        List of allowed stages
    counterpicks: List[str]
        List of allowed counterpicks
    phase: str
        Something very important! Used for knowing what is the current phase of the tournament.
        It is also used by commands to know if it is allowed to run.

        Can be the following values:

        *   ``"pending"``: Tournament just setup, nothing open yet
        *   ``"register"``: Registrations or check-in started and are not finished
        *   ``"awaiting"``: Registrations and check-in done, awaiting upload and start
        *   ``"ongoing"``: Tournament is started and ongoing
        *   ``"finished"``: Tournament done. Should be immediatly deleted unless there's an issue
    register_phase: str
        Defines the current status of registration.

        Can be the following values:

        *   ``"manual"``: No start date setup, waiting for manual start
        *   ``"pending"``: Start date setup, awaiting automatic start
        *   ``"ongoing"``: Registrations active
        *   ``"onhold"``: Registrations started and ended once, but awaiting a second start
        *   ``"done"``: Registrations ended
    checkin_phase: str
        Defines the current status of check-in.

        Can be the following values:

        *   ``"manual"``: No start date setup, waiting for manual start
        *   ``"pending"``: Start date setup, awaiting automatic start
        *   ``"ongoing"``: Check-in active
        *   ``"onhold"``: Check-in started and ended once, but awaiting a second start
        *   ``"done"``: Check-in ended
    register_message: Optional[discord.Message]
        The pinned message in the registrations channel
    checkin_reminders: List[Tuple[int, bool]]
        A list of reminders to send for the check-in. Contains tuples of two items: when to send
        the reminder (minutes before check-in end date), and if the bot should DM members. This is
        calculated on check-in start.
    lock: asyncio.Lock
        A lock acquired when the tournament is being refreshed by the loop task, to prevent
        commands like win or dq from being run at the same time.

        *New since beta 13:* The lock is also acquired with the ``[p]in`` command to prevent too
        many concurrent tasks, breaking the limit.
    task: asyncio.Task
        The task for the `loop_task` function (`discord.ext.tasks.Loop` object)
    task_errors: int
        Number of errors that occured within the loop task. If it reaches 5, task is cancelled.
    top_8: dict
        Represents when the top 8 and bo5 begins in the bracket.
    matches_to_announce: List[str]
        A list of strings to announce in the defined queue channel. This is done to prevent sending
        too many messages at once and hitting ratelimits, so we wrap messages together.
    """

    def __init__(
        self,
        bot: Red,
        guild: discord.Guild,
        config: Config,
        name: str,
        game: str,
        url: str,
        id: str,
        limit: Optional[int],
        status: str,
        tournament_start: datetime,
        bot_prefix: str,
        cog_version: str,
        data: dict,
    ):
        self.bot = bot
        self.guild = guild
        self.data = config
        self.name = name
        self.game = game
        self.url = url
        self.id = id
        self.limit = limit
        self.status = status
        self.tz = tournament_start.tzinfo
        self.tournament_start = tournament_start
        self.bot_prefix = bot_prefix
        self.cog_version = cog_version
        self.participants: List[Participant] = []
        self.matches: List[Match] = []
        self.streamers: List[Streamer] = []
        self.winner_categories: List[discord.CategoryChannel] = []
        self.loser_categories: List[discord.CategoryChannel] = []
        self.category: discord.CategoryChannel = guild.get_channel(
            data["channels"].get("category")
        )
        self.announcements_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("announcements")
        )
        self.checkin_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("checkin")
        )
        self.queue_channel: discord.TextChannel = guild.get_channel(data["channels"].get("queue"))
        self.register_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("register")
        )
        self.scores_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("scores")
        )
        self.stream_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("stream")
        )
        self.to_channel: discord.TextChannel = guild.get_channel(data["channels"].get("to"))
        self.vip_register_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("vipregister")
        )
        self.participant_role: discord.Role = guild.get_role(data["roles"].get("participant"))
        self.streamer_role: discord.Role = guild.get_role(data["roles"].get("streamer"))
        self.to_role: discord.Role = guild.get_role(data["roles"].get("to"))
        # self.tester_role: discord.Role = guild.get_role(data["roles"].get("tester"))
        self.tester_role = None
        self.credentials = data["credentials"]
        # fitting to achallonge's requirements
        self.credentials["login"] = self.credentials.pop("username")
        self.credentials["password"] = self.credentials.pop("api")
        self.delay: int = data["delay"]
        self.time_until_warn = {
            "bo3": data["time_until_warn"].get("bo3", (25, 10)),
            "bo5": data["time_until_warn"].get("bo5", (30, 10)),
        }  # the default values are somehow not loaded into the dict sometimes
        self.register: dict = data["register"]
        self.checkin: dict = data["checkin"]
        self.start_bo5: int = data["start_bo5"]
        self.autostop_register: bool = data["autostop_register"]
        self.ignored_events = []  # list of scheduled events to skip (register_start/checkin_stop)
        # works with next_scheduled_event, used for manual early starts/stops
        if data["register"]["second_opening"] != 0:
            self.register_second_start: datetime = tournament_start - timedelta(
                minutes=data["register"]["second_opening"]
            )
        else:
            self.register_second_start = None
            self.ignored_events.append("register_second_start")
        if data["register"]["opening"] != 0:
            self.register_start: datetime = tournament_start - timedelta(
                minutes=data["register"]["opening"]
            )
        else:
            self.register_start = None
            self.ignored_events.append("register_start")
        if data["register"]["closing"] != 0:
            self.register_stop: datetime = tournament_start - timedelta(
                minutes=data["register"]["closing"]
            )
        else:
            self.register_stop = None
            self.ignored_events.append("register_stop")
        if data["checkin"]["opening"] != 0:
            self.checkin_start: datetime = tournament_start - timedelta(
                minutes=data["checkin"]["opening"]
            )
        else:
            self.checkin_start = None
            self.ignored_events.append("checkin_start")
        if data["checkin"]["closing"] != 0:
            self.checkin_stop: datetime = tournament_start - timedelta(
                minutes=data["checkin"]["closing"]
            )
        else:
            self.checkin_stop = None
            self.ignored_events.append("checkin_stop")
        self.ruleset_channel: discord.TextChannel = guild.get_channel(data["ruleset"])
        self.game_role: discord.Role = guild.get_role(data["role"]) or guild.default_role
        self.baninfo: str = data["baninfo"]
        self.ranking: dict = data["ranking"]
        self.stages: list = data["stages"]
        self.counterpicks: list = data["counterpicks"]
        self.phase = "pending"  # can be multiple values:
        # "pending": initial value, when the tournament is registered
        # "register": when registration/checkin is active
        # "awaiting": registration is done, participants are ready, waiting for upload and start
        # "ongoing": tournament started, also called the "high panic and RAM usage moment"
        # "finished": tournament ended. not even sure if it's possible, since tournament is deleted
        self.register_phase = "pending" if self.register_start else "manual"  # can be:
        # "manual": no opening time provided, waiting for user
        # "pending": awaiting first registration start
        # "ongoing": active, first or second phase, or even manual
        # "onhold": done once, but there's still a scheduled opening time (most likely two-stage)
        # "done": ended, no more opening scheduled
        self.checkin_phase = "pending" if self.checkin_start else "manual"
        # same as above (yes "onhold" too, there could be a first manual start)
        self.register_message: Optional[discord.Message] = None  # message being updated
        # list of timedeltas for checkin reminders, associated to whether we should send DMs or not
        # timedeltas are substracted from checkin_end (ex: 10 min before checkin ending)
        self.checkin_reminders: List[Tuple[int, bool]] = []
        # loop task things
        self.lock = asyncio.Lock()
        self.task: Optional[asyncio.Task] = None
        self.task_errors = 0
        self.top_8 = {
            "winner": {"top8": None, "bo5": None},
            "loser": {"top8": None, "bo5": None},
        }
        # self.debug_task = asyncio.get_event_loop().create_task(self.debug_loop_task())
        self.matches_to_announce: List[str] = []  # matches to announce in the queue channel
        self.cancelling = False  # see Tournament.__del__ and Match.__del__

    def __repr__(self):
        return (
            "<Tournament name={0.name} phase={0.phase} status={0.status} url={0.url} "
            "game={0.game} limit={0.limit} id={0.id} guild_id={0.guild.id}>"
        ).format(self)

    participant_object = Participant
    match_object = Match
    tournament_type = "base"  # should be "challonge", or "smash.gg"...

    def cancel(self):
        """
        Correctly clears the object, stopping the task and removing ranking data.
        """
        self.cancelling = True
        if self.task:
            self.stop_loop_task()
        # try:
        #     self.debug_task.cancel()
        # except AttributeError:
        #     pass
        shutil.rmtree(
            cog_data_path(None, raw_name="Tournaments") / "ranking" / str(self.guild.id),
            ignore_errors=True,
        )

    def __del__(self):
        self.cancel()

    # Config-related stuff
    @classmethod
    async def from_saved_data(
        cls,
        bot: Red,
        guild: discord.Guild,
        config: Config,
        cog_version: str,
        data: dict,
        config_data: dict,
    ):
        """
        Loads a tournament from Config.

        Due to Python's weird behaviour, this method must be reimplemented and simply called back
        without changes.
        """
        tournament_start = datetime.fromtimestamp(
            int(data["tournament_start"][0]),
            tz=timezone(timedelta(seconds=data["tournament_start"][1])),
        )
        participants = data.pop("participants")
        matches = data.pop("matches")
        streamers = data.pop("streamers")
        winner_categories = data.pop("winner_categories")
        loser_categories = data.pop("loser_categories")
        phase = data.pop("phase")
        register = data.pop("register")
        checkin = data.pop("checkin")
        ignored_events = data.pop("ignored_events")
        register_message_id = data.pop("register_message_id")
        checkin_reminders = data.pop("checkin_reminders")
        del data["tournament_start"], data["tournament_type"]
        tournament = cls(
            bot,
            guild,
            config,
            **data,
            tournament_start=tournament_start,
            cog_version=cog_version,
            data=config_data,
        )
        if phase == "ongoing":
            await tournament._get_top8()
        tournament.participants = list(
            filter(
                None,
                [
                    tournament.participant_object.from_saved_data(tournament, data)
                    for data in participants
                ],
            )
        )
        if len(tournament.participants) < len(participants):
            await tournament._update_participants_list()
        if not tournament.participants and matches:
            raise RuntimeError(
                "Participants list is empty while there are ongoing matches! "
                "We probably don't want to continue resuming the tournament, as this "
                "could result in the disqualification of absolutely everyone."
            )
        for data in matches:
            player1 = tournament.find_participant(player_id=data["player1"])[1]
            player2 = tournament.find_participant(player_id=data["player2"])[1]
            match = tournament.match_object.from_saved_data(tournament, player1, player2, data)
            if player1 is None and player2 is None:
                if match.channel:
                    await tournament.destroy_player(data["player1"])
                    await tournament.destroy_player(data["player2"])
                    try:
                        await match.channel.delete()
                    except discord.HTTPException as e:
                        log.warn(
                            f"[Guild {guild.id}] Can't delete set channel #{match.set}.",
                            exc_info=e,
                        )
                    await tournament.to_channel.send(
                        _(":information_source: Set {match} cancelled, both players left.").format(
                            set=match.set
                        )
                    )
                    continue
            stop = False
            for i, player in enumerate((player1, player2), start=1):
                if player is None:
                    await tournament.destroy_player(data[f"player{i}"])
                    await match.disqualify(data[f"player{i}"])
                    await tournament.to_channel.send(
                        _(
                            ":information_source: Set {set} finished, "
                            "player with ID {player} can't be found."
                        ).format(set=match.set, player=data[f"player{i}"])
                    )
                    stop = True
            if stop:
                continue
            tournament.matches.append(match)
        tournament.streamers = [Streamer.from_saved_data(tournament, x) for x in streamers]
        tournament.winner_categories = list(
            filter(None, [guild.get_channel(x) for x in winner_categories])
        )
        tournament.loser_categories = list(
            filter(None, [guild.get_channel(x) for x in loser_categories])
        )
        tournament.phase = phase
        tournament.register_phase = register
        tournament.checkin_phase = checkin
        tournament.ignored_events = ignored_events
        tournament.checkin_reminders = checkin_reminders
        if register_message_id and tournament.register_channel:
            try:
                message = await tournament.register_channel.fetch_message(register_message_id)
            except discord.NotFound:
                pass
            else:
                tournament.register_message = message
        return tournament

    def to_dict(self) -> dict:
        """Returns a dict ready for Config."""
        offset = self.tournament_start.utcoffset()
        if offset:
            offset = offset.total_seconds()
        else:
            offset = 0
        data = {
            "name": self.name,
            "game": self.game,
            "url": self.url,
            "id": self.id,
            "limit": self.limit,
            "status": self.status,
            "tournament_start": (int(self.tournament_start.timestamp()), offset),
            "bot_prefix": self.bot_prefix,
            "participants": [x.to_dict() for x in self.participants],
            "matches": [x.to_dict() for x in self.matches],
            "streamers": [x.to_dict() for x in self.streamers],
            "winner_categories": [x.id for x in self.winner_categories],
            "loser_categories": [x.id for x in self.loser_categories],
            "phase": self.phase,
            "tournament_type": self.tournament_type,
            "register": self.register_phase,
            "checkin": self.checkin_phase,
            "checkin_reminders": self.checkin_reminders,
            "ignored_events": self.ignored_events,
            "register_message_id": self.register_message.id if self.register_message else None,
        }
        return data

    async def save(self):
        """
        Saves data with Config. This is done with the loop task during a tournament but must be
        called while it's not ongoing.
        """
        data = self.to_dict()
        await self.data.guild(self.guild).tournament.set(data)

    @property
    def allowed_roles(self):
        """
        Return a list of roles that should have access to the temporary channels.
        """
        allowed_roles = []
        if self.to_role is not None:
            allowed_roles.append(self.to_role)
        if self.streamer_role is not None:
            allowed_roles.append(self.streamer_role)
        return allowed_roles

    # some common utils
    @staticmethod
    def _format_datetime(date: datetime, only_time=False):
        locale = get_babel_locale()
        _date = format_date(date, format="full", locale=locale)
        time = format_time(date, format="short", locale=locale)
        if only_time:
            return time
        return _("{date} at {time}").format(date=_date, time=time)

    def next_scheduled_event(self) -> Tuple[str, timedelta]:
        """
        Returns the next scheduled event (register/checkin/None) with the corresponding timedelta
        """
        now = datetime.now(self.tz)
        # the order here is important, as max() return the first highest value
        # it's pretty common to have some events with the same datetime, and the loop only runs
        # one event per iteration, so we place them in a logical order here
        events = {
            "register_start": (self.register_start, self.register_phase == "pending"),
            "checkin_stop": (self.checkin_stop, self.checkin_phase == "ongoing"),
            "checkin_start": (self.checkin_start, self.checkin_phase == "pending"),
            "register_second_start": (self.register_second_start, self.register_phase == "onhold"),
            "register_stop": (self.register_stop, self.register_phase == "ongoing"),
        }
        for name, (date, condition) in events.items():
            if date is None:
                events[name] = None
                continue
            if name in self.ignored_events:
                events[name] = None
                continue
            delta = date - now
            if condition is True:
                events[name] = delta
            else:
                events[name] = None
        events = dict(filter(lambda x: x[1] is not None, events.items()))
        return min(events.items(), key=lambda x: x[1], default=None)

    def _valid_dates(self):
        now = datetime.now(self.tz)
        if now > self.tournament_start:
            raise RuntimeError(
                _("The tournament's date has already passed."),
                [(_("Start date"), self.tournament_start)],
            )
        dates = [
            (_("Registration start"), self.register_start),
            (_("Registration second start"), self.register_second_start),
            (_("Registration stop"), self.register_stop),
            (_("Check-in start"), self.checkin_start),
            (_("Check-in stop"), self.checkin_stop),
        ]
        passed = {x: y for x, y in dates if y and now > y}
        if passed:
            raise RuntimeError(_("Some dates are passed."), dates)
        if (
            self.register_start
            and self.register_stop
            and not self.register_start < self.register_stop
        ):
            dates = [dates[0] + dates[2]]
            raise RuntimeError(_("Registration start and stop times conflict."), dates)
        if self.register_second_start and (
            (self.register_start and not self.register_start < self.register_second_start)
            or (self.register_stop and not self.register_second_start < self.register_stop)
        ):
            dates = dates[:3]
            raise RuntimeError(_("Second registration start time conflict."), dates)
        if self.checkin_start and self.checkin_stop and not self.checkin_start < self.checkin_stop:
            dates = dates[3:]
            raise RuntimeError(_("Check-in start and stop times conflict."), dates)

    async def _get_available_category(self, dest: str, inc: int = 0):
        position = self.category.position + 1 if self.category else len(self.guild.categories)
        if dest == "winner":
            categories = self.winner_categories
        else:
            categories = self.loser_categories
        position += len(categories)
        try:
            return next(filter(lambda x: len(x.channels) + inc < 50, categories))
        except StopIteration:
            if dest == "winner":
                name = "Winner bracket"
            else:
                name = "Loser bracket"
            channel = await self.guild.create_category(
                name, reason=_("New category of sets."), position=position
            )
            await channel.edit(position=position)  # discord won't let me place it on first try
            if dest == "winner":
                self.winner_categories.append(channel)
            else:
                self.loser_categories.append(channel)
            return channel

    async def _clear_categories(self):
        categories = self.winner_categories + self.loser_categories
        for category in categories:
            try:
                await category.delete()
            except discord.HTTPException as e:
                log.error(
                    f"[Guild {self.guild.id}] Can't delete category {category} "
                    "(_clear_categories was called).",
                    exc_info=e,
                )
        self.winner_categories = []
        self.loser_categories = []

    async def _get_top8(self):
        # if you're wondering how this works, well I have no idea :D
        # this was mostly taken from the original bot this cog is based on, ATOS by Wonderfall
        # https://github.com/Wonderfall/ATOS/blob/master/bot.py#L1355-L1389
        rounds = await self._get_all_rounds()
        if not rounds:
            raise RuntimeError("There are no matches available.")
        top8 = self.top_8
        # calculate top 8
        top8["winner"]["top8"] = max(rounds) - 2
        top8["loser"]["top8"] = min(rounds) + 2
        # minimal values, in case of a small tournament
        if top8["winner"]["top8"] < 1:
            top8["winner"]["top8"] = 1
        if top8["loser"]["top8"] > -1:
            top8["loser"]["top8"] = -1
        # calculate bo5 start
        if self.start_bo5 > 0:
            top8["winner"]["bo5"] = top8["winner"]["top8"] + self.start_bo5 - 1
        elif self.start_bo5 in (0, 1):
            top8["winner"]["bo5"] = top8["winner"]["top8"] + self.start_bo5
        else:
            top8["winner"]["bo5"] = top8["winner"]["top8"] + self.start_bo5 + 1
        if self.start_bo5 > 1:
            top8["loser"]["bo5"] = min(rounds)  # top 3 is loser final anyway
        else:
            top8["loser"]["bo5"] = top8["loser"]["top8"] - self.start_bo5
        # avoid aberrant values
        if top8["winner"]["bo5"] > max(rounds):
            top8["winner"]["bo5"] = max(rounds)
        if top8["winner"]["bo5"] < 1:
            top8["winner"]["bo5"] = 1
        if top8["loser"]["bo5"] < min(rounds):
            top8["loser"]["bo5"] = min(rounds)
        if top8["loser"]["bo5"] > -1:
            top8["loser"]["bo5"] = -1

    async def warn_bracket_change(self, *sets):
        """
        Warn T.O.s of a bracket change.

        Parameters
        ----------
        *sets: str
            The list of affected sets.
        """
        await self.to_channel.send(
            _(
                ":information_source: Changes were detected on the upstream bracket.\n"
                "This may result in multiple sets ending, relaunch or cancellation.\n"
                "Affected sets: {sets}"
            ).format(sets=", ".join([f"#{x}" for x in sets]))
        )

    # tools for finding objects within the instance's lists of Participants, Matches and Streamers
    def find_participant(
        self,
        *,
        player_id: Optional[str] = None,
        discord_id: Optional[int] = None,
        discord_name: Optional[str] = None,
    ) -> Tuple[int, Participant]:
        """
        Find a participant in the internal cache, and returns its object and position in the list.

        You need to provide only one of the parameters.

        Parameters
        ----------
        player_id: Optional[str]
            Player's ID on the bracket, as returned by `Participant.player_id`
        discord_id: Optional[int]
            Player's Discord ID
        discord_name: Optional[str], as returned by `discord.Member.id`
            Player's full Discord name, as returned by ``str(discord.Member)``

        Returns
        -------
        Tuple[int, Participant]
            The index of the participant in the list (useful for deletion or deplacement) and
            its `Participant` object

        Raises
        ------
        RuntimeError
            No parameter was provided
        """
        if player_id:
            try:
                return next(
                    filter(lambda x: x[1].player_id == player_id, enumerate(self.participants))
                )
            except StopIteration:
                return None, None
        elif discord_id:
            try:
                return next(filter(lambda x: x[1].id == discord_id, enumerate(self.participants)))
            except StopIteration:
                return None, None
        elif discord_name:
            try:
                return next(
                    filter(lambda x: str(x[1]) == discord_name, enumerate(self.participants))
                )
            except StopIteration:
                return None, None
        raise RuntimeError("Provide either player_id, discord_id or discord_name")

    def find_match(
        self,
        *,
        match_id: Optional[int] = None,
        match_set: Optional[int] = None,
        channel_id: Optional[int] = None,
    ) -> Tuple[int, Match]:
        """
        Find a match in the internal cache, and returns its object and position in the list.

        You need to provide only one of the parameters.

        Parameters
        ----------
        match_id: Optional[int]
            Match's ID on the bracket, as returned by `Match.id`
        match_set: Optional[int]
            Match's number, or suggested play order, on the bracket, as returned by `Match.set`
        channel_id: Optional[id]
            Discord channel's ID, as returned by `discord.TextChannel.id`

            .. warning:: A match may not have a channel assigned

        Returns
        -------
        Tuple[int, Match]
            The index of the match in the list (useful for deletion or deplacement) and
            its `Match` object

        Raises
        ------
        RuntimeError
            No parameter was provided
        """
        if match_id:
            try:
                return next(filter(lambda x: x[1].id == match_id, enumerate(self.matches)))
            except StopIteration:
                return None, None
        elif match_set:
            try:
                return next(filter(lambda x: x[1].set == match_set, enumerate(self.matches)))
            except StopIteration:
                return None, None
        elif channel_id:
            try:
                return next(
                    filter(
                        lambda x: x[1].channel and x[1].channel.id == channel_id,
                        enumerate(self.matches),
                    )
                )
            except StopIteration:
                return None, None
        raise RuntimeError("Provide either match_id, match_set or channel_id")

    def find_streamer(
        self, *, channel: Optional[str] = None, discord_id: Optional[int] = None
    ) -> Tuple[int, Streamer]:
        """
        Find a streamer in the internal cache, and returns its object and position in the list.

        You need to provide only one of the parameters.

        Parameters
        ----------
        channel: Optional[str]
            The streamer's channel, as returned by `Streamer.channel` (not full URL, only last
            part). Example for https://twitch.tv/dreekius, use ``channel="dreekius"``.
        discord_id: Optional[int]
            Streamer's Discord ID

        Returns
        -------
        Tuple[int, Streamer]
            The index of the streamer in the list (useful for deletion or deplacement) and
            its `Streamer` object

        Raises
        ------
        RuntimeError
            No parameter was provided
        """
        if channel:
            try:
                return next(filter(lambda x: x[1].channel == channel, enumerate(self.streamers)))
            except StopIteration:
                return None, None
        elif discord_id:
            try:
                return next(
                    filter(lambda x: x[1].member.id == discord_id, enumerate(self.streamers))
                )
            except StopIteration:
                return None, None
        raise RuntimeError("Provide either channel or discord_id")

    # registration and check-in related methods
    def _prepare_register_message(self):
        if self.checkin_start:
            checkin = _(":white_small_square: __Check-in:__ From {begin} to {end}\n").format(
                begin=self._format_datetime(self.checkin_start, True),
                end=self._format_datetime(self.checkin_stop or self.tournament_start, True),
            )
        else:
            checkin = ""
        if self.limit:
            limit = _("{registered}/{limit} participants registered").format(
                registered=len(self.participants), limit=self.limit
            )
        else:
            limit = _("{registered} participants registered *(no limit set)*").format(
                registered=len(self.participants)
            )
        if self.ruleset_channel:
            ruleset = _(":white_small_square: __Ruleset:__ See {channel}\n").format(
                channel=self.ruleset_channel.mention
            )
        else:
            ruleset = ""
        return _(
            "**{t.name}** | *{t.game}*\n\n"
            ":white_small_square: __Date:__ {date}\n"
            ":white_small_square: __Register:__ Closing at {time}\n"
            "{checkin}"
            ":white_small_square: __Participants:__ {limit}\n"
            ":white_small_square: __Bracket:__ {t.url}\n"
            "{ruleset}\n"
            "You can register/unregister to this tournament with "
            "the `{t.bot_prefix}in` and `{t.bot_prefix}out` commands.\n"
            "*Note: your Discord username will be used in the bracket.*"
        ).format(
            t=self,
            date=self._format_datetime(self.tournament_start),
            time=self._format_datetime(self.register_stop or self.tournament_start, True),
            checkin=checkin,
            limit=limit,
            ruleset=ruleset,
        )

    async def start_registration(self, second=False):
        """
        Open the registrations and save.

        Parameters
        ----------
        second: bool
            If this is the second time registrations are started (will not annouce the same
            message, and keep updating the same pinned message). Defaults to `False`.
        """
        self.phase = "register"
        self.register_phase = "ongoing"
        if self.register_channel:
            if not second:
                self.register_message = await self.register_channel.send(
                    self._prepare_register_message()
                )
                await self.register_message.pin()
            await self.register_channel.set_permissions(
                self.game_role, read_messages=True, send_messages=True
            )
        if self.announcements_channel:
            if second:
                message = _(
                    "{role} Registrations for the tournament **{tournament}** "
                    "are now re-opened{channel} until {date}!"
                ).format(
                    role=self.game_role.mention
                    if self.game_role != self.guild.default_role
                    else "",
                    tournament=self.name,
                    channel=_(" in {channel}").format(channel=self.register_channel.mention)
                    if self.register_channel
                    else "",
                    date=self._format_datetime(self.register_stop or self.tournament_start),
                )
            elif self.register_channel:
                message = _(
                    "{role} Registrations for the tournament **{tournament}** are now opened "
                    "in {channel}! See the pinned message there for details.\n"
                    ":calendar_spiral: This tournament will take place on **{date}**."
                ).format(
                    tournament=self.name,
                    channel=self.register_channel.mention,
                    role=self.game_role.mention
                    if self.game_role != self.guild.default_role
                    else "",
                    date=self._format_datetime(self.tournament_start),
                )
            else:
                if self.checkin_start:
                    checkin = _(
                        ":white_small_square: __Check-in:__ From {begin} to {end}\n"
                    ).format(
                        begin=self._format_datetime(self.checkin_start, True),
                        end=self._format_datetime(
                            self.checkin_stop or self.tournament_start, True
                        ),
                    )
                else:
                    checkin = ""
                if self.limit:
                    limit = _("Limited to {limit} particiapants.").format(
                        registered=len(self.participants), limit=self.limit
                    )
                else:
                    limit = _("No limit set.")
                if self.ruleset_channel:
                    ruleset = _(":white_small_square: __Ruleset:__ See {channel}\n").format(
                        channel=self.ruleset_channel.mention
                    )
                else:
                    ruleset = ""
                message = _(
                    "{role} Registrations for the tournament **{t.name}** are now opened!\n"
                    ":calendar_spiral: This tournament will take place on **{date}**.\n\n"
                    ":white_small_square: __Register:__ Closing at {time}\n"
                    "{checkin}"
                    ":white_small_square: __Participants:__ {limit}\n"
                    ":white_small_square: __Bracket:__ {t.url}\n"
                    "{ruleset}\n"
                    "You can register/unregister to this tournament with "
                    "the `{t.bot_prefix}in` and `{t.bot_prefix}out` commands.\n"
                    "*Note: your Discord username will be used in the bracket.*"
                ).format(
                    t=self,
                    role=self.game_role.mention
                    if self.game_role != self.guild.default_role
                    else "",
                    date=self._format_datetime(self.tournament_start),
                    time=self._format_datetime(self.register_stop or self.tournament_start, True),
                    register=self._format_datetime(self.register_start or self.tournament_start),
                    checkin=checkin,
                    limit=limit,
                    ruleset=ruleset,
                )
            mentions = discord.AllowedMentions(roles=[self.game_role]) if self.game_role else None
            await self.announcements_channel.send(message, allowed_mentions=mentions)
        await self.save()

    async def end_registration(self):
        """
        Close the registrations and save.

        If the check-in is also done, participants will be seeded and uploaded.

        Parameters
        ----------
        background: bool
            If the function is called in a background loop. If `True`, the bot will do actions
            knowing there's no context command (for now, means a background seed and upload).
            Defaults to `False`.
        """
        if self.register_second_start and self.register_second_start > datetime.now(self.tz):
            self.register_phase = "onhold"
        else:
            self.register_phase = "done"
        if self.register_channel:
            if self.register_message:
                await self.register_message.edit(content=self._prepare_register_message())
            await self.register_channel.set_permissions(
                self.game_role, read_messages=True, send_messages=False
            )
            await self.register_channel.send(_("Registration ended."))
        elif self.announcements_channel:  # no registration channel, so we announce somewhere else
            await self.announcements_channel.send(_("Registration ended."))
        if not self.next_scheduled_event():
            # no more scheduled events, upload and wait for start
            self.phase = "awaiting"
            await self._background_seed_and_upload()
        await self.save()

    async def start_check_in(self):
        """
        Open the check-in and save.

        This will also calculate and fill the `checkin_reminders` list.
        """
        if not self.participants:
            self.checkin_phase = "done"
            message = _("Cancelled check-in start since there are currently no participants. ")
            if not self.next_scheduled_event:
                # no more scheduled events, upload and wait for start
                self.phase = "awaiting"
            else:
                message += _(
                    "Registrations are still ongoing, and new participants are pre-checked."
                )
            await self.to_channel.send(message)
            return
        self.phase = "register"
        self.checkin_phase = "ongoing"
        message = _(
            "{role} The check-in for **{t.name}** has started!\n"
            "You have to confirm your presence by typing `{t.bot_prefix}in` here{end_time}.\n"
            "If you want to unregister, type `{t.bot_prefix}out` instead.\n\n"
            ":warning: If you don't check in time, you will be unregistered!"
        ).format(
            t=self,
            role=self.participant_role.mention,
            end_time=_(" until {}").format(
                self._format_datetime(self.checkin_stop, only_time=True)
            )
            if self.checkin_stop
            else "",
        )
        mentions = discord.AllowedMentions(roles=[self.participant_role])
        if self.checkin_channel:
            message = await self.checkin_channel.send(message, allowed_mentions=mentions)
            await message.pin()
            await self.checkin_channel.set_permissions(
                self.participant_role, read_messages=True, send_messages=True
            )
        elif self.announcements_channel:
            await self.announcements_channel.send(message, allowed_mentions=mentions)
        if self.register_channel and self.register_phase == "ongoing":
            await self.register_channel.send(
                _(
                    ":information_source: Check-in started{channel}!\n"
                    "You can still register here until {end_time}. "
                    "Anyone registering as of now will already be checked in."
                ).format(
                    channel=_(" in {}").format(self.checkin_channel.mention)
                    if self.checkin_channel
                    else "",
                    end_time=self._format_datetime(
                        self.register_stop or self.tournament_start, only_time=True
                    ),
                )
            )
        if self.checkin_stop:
            duration = (self.checkin_stop - datetime.now(self.tz)).total_seconds()
            duration //= 60  # number of minutes
            if duration >= 10:
                self.checkin_reminders.append((5, False))
            if duration >= 20:
                self.checkin_reminders.append((10, True))
            if duration >= 40:
                self.checkin_reminders.append((15, False))
        await self.save()

    async def call_check_in(self, with_dm: bool = False):
        """
        Pings participants that have not checked in yet.

        Only works with a check-in channel setup and a stop time.

        Parameters
        ----------
        with_dm: bool
            If the bot should DM unchecked members too. Defaults to `False`.

            .. caution:: Prevent using this if there are too many unchecked members, as Discord
                started to ban bots sending too many DMs.
        """
        if not self.checkin_channel:
            return
        if not self.checkin_stop:
            return
        members = [x for x in self.participants if not x.checked_in]
        if not members:
            return
        await self.checkin_channel.send(
            _(
                ":clock1: **Check-in reminder!**\n\n- {members}\n\n"
                "You have until {end_time} to check-in, or you'll be unregistered."
            ).format(
                members="\n- ".join([x.mention for x in members]),
                end_time=self._format_datetime(self.checkin_stop, only_time=True),
            )
        )
        if with_dm:
            for member in members:
                try:
                    await member.send(
                        _(
                            ":warning: **Attention!** You have **{time} minutes** left "
                            "for checking-in to the tournament **{tournament}**."
                        ).format(
                            time=round(
                                (self.checkin_stop - datetime.now(self.tz)).total_seconds() / 60
                            ),
                            tournament=self.name,
                        )
                    )
                except discord.HTTPException:
                    pass

    async def end_checkin(self):
        """
        Close the check-in, unregister unchecked members (attempts to DM) and save.

        If the registrations are also done, participants will be seeded and uploaded.

        Parameters
        ----------
        background: bool
            If the function is called in a background loop. If `True`, the bot will do actions
            knowing there's no context command (for now, means a background seed and upload).
            Defaults to `False`.
        """
        self.checkin_phase = "done"
        to_remove = []
        failed = []
        for member in filter(lambda x: x.checked_in is False, self.participants):
            try:
                await member.remove_roles(
                    self.participant_role, reason=_("Participant not checked.")
                )
            except discord.HTTPException as e:
                log.warn(
                    f"[Guild {self.guild.id}] Can't remove participant role from unchecked "
                    f"participant {member} (ID: {member.id}) after check-in end.",
                    exc_info=e,
                )
                failed.append(member)
            try:
                await member.send(
                    _(
                        "You didn't check-in on time. "
                        "You are therefore unregistered from the tournament **{tournament}**."
                    ).format(tournament=self.name)
                )
            except discord.HTTPException:
                pass
            to_remove.append(member)
        for member in to_remove:
            self.participants.remove(member)
        text = _(":information_source: Check-in was ended. {removed}").format(
            removed=_("{} participants didn't check and were unregistered.").format(len(to_remove))
            if to_remove
            else _("No participant was unregistered.")
        )
        if failed:
            text += _("\n\n:warning: {} participants couldn't have their roles removed:\n")
            text += " ".join([x.mention for x in failed])
        for page in pagify(text):
            await self.to_channel.send(page)
        if self.checkin_channel:
            await self.checkin_channel.set_permissions(
                self.game_role, read_messages=True, send_messages=False
            )
            await self.checkin_channel.send(
                _("Check-in ended. Participants who didn't check are unregistered.")
            )
        elif self.announcements_channel:
            await self.announcements_channel.send(
                _("Check-in ended. Participants who didn't check are unregistered.")
            )
        if not self.next_scheduled_event:
            # no more scheduled events, upload and wait for start
            self.phase = "awaiting"
            await self._background_seed_and_upload()
        await self.save()

    async def register_participant(self, member: discord.Member, send_dm: bool = True):
        """
        Register a new participant to the tournament (add role) and save.

        If the check-in has started, participant will be pre-checked.

        If there is a limit of participants, the auto-stop setting for registrations is enabled and
        the limit is reached, registrations will be closed.

        The `Participant` object is not returned and directly added to the list.

        Parameters
        ----------
        member: discord.Member
            The member to register. He must be in the server.
        send_dm: bool
            If the bot should DM the new participant for his registrations. Defaults to `True`.
        """
        if self.limit and len(self.participants) >= self.limit:
            raise RuntimeError("Limit reached.")
        await member.add_roles(self.participant_role, reason=_("Registering to tournament."))
        participant = self.participant_object(member, self)
        if self.checkin_phase != "pending":
            # registering during check-in, count as already checked
            participant.checked_in = True
        if self.participants and self.participants[-1].player_id is not None:
            # last registered participant has a player ID, so we should upload him to the bracket
            await self.add_participant(participant)
        self.participants.append(participant)
        log.debug(f"[Guild {self.guild.id}] Player {member} registered.")
        if (
            self.limit
            and self.autostop_register
            and self.register_phase == "ongoing"
            and len(self.participants) >= self.limit
        ):
            await self.end_registration()
        await self.save()
        if not send_dm:
            return
        try:
            await member.send(
                _("You are now registered to the tournament **{name}**!").format(name=self.name)
            )
        except discord.HTTPException:
            pass

    async def unregister_participant(self, member: discord.Member, send_dm: bool = True):
        """
        Remove a participant.

        If the player is uploaded on the bracket, he will also be removed from there. If the
        tournament has started, member will be disqualified instead.

        This removes roles and DMs the participant.

        Parameters
        ----------
        member: discord.Member
            The member to disqualify

        Raise
        -----
        KeyError
            The member is not registered
        """
        i, participant = self.find_participant(discord_id=member.id)
        if i is None:
            raise KeyError("Participant not found.")
        if participant.player_id is not None:
            await participant.destroy()
            if participant.match is not None:
                await participant.match.disqualify(participant)
        await participant.remove_roles(
            self.participant_role, reason=_("Unregistering from tournament.")
        )
        del self.participants[i]
        await self.save()
        if not send_dm:
            return
        try:
            await participant.send(_("You were unregistered from the tournament."))
        except discord.Forbidden:
            pass

    # seeding stuff
    # 95% of this code is made by Wonderfall, from ATOS bot (original)
    # https://github.com/Wonderfall/ATOS/blob/master/utils/seeding.py
    async def _fetch_braacket_ranking_info(self):
        league_name, league_id = self.ranking["league_name"], self.ranking["league_id"]
        headers = {
            "User-Agent": (
                f"Red-DiscordBot {red_version} Laggrons-Dumb-Cogs/tournaments {self.cog_version}"
            ),
            "Connection": "close",
        }
        path = cog_data_path(None, raw_name="Tournaments") / "ranking" / str(self.guild.id)
        path.mkdir(parents=True, exist_ok=True)
        async with aiohttp.ClientSession(headers=headers) as session:
            for page in range(1, 6):
                url = f"https://braacket.com/league/{league_name}/ranking/{league_id}"
                parameters = {
                    "rows": 200,
                    "page": page,
                    "export": "csv",
                }
                file_path = path / f"page{page}.csv"
                async with session.get(url, params=parameters) as response:
                    if response.status >= 400:
                        raise RuntimeError(response.status, response.reason)
                    async with aiofiles.open(file_path, mode="wb") as file:
                        await file.write(await response.read())
                if page != 1 and filecmp.cmp(file_path, path / f"page{page-1}.csv"):
                    await aiofiles.os.remove(file_path)
                    break

    async def _seed_participants(self):
        ranking = {}
        path = cog_data_path(None, raw_name="Tournaments") / "ranking"
        # open and parse the previously downloaded CSV
        for file in list(path.rglob("*.csv")):
            with open(file, errors="surrogateescape") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ranking[row["Player"]] = int(row["Points"])
        # base elo : put at bottom
        base_elo = min(list(ranking.values()))
        ranked = []
        not_ranked = []
        # assign elo ranking to each player
        for player in self.participants:
            try:
                player.elo = ranking[str(player)]
                ranked.append(player)
            except KeyError:
                player.elo = base_elo  # base Elo if none found
                not_ranked.append(player)
        # Sort & clean
        shuffle(not_ranked)
        sorted_participants = sorted(ranked, key=lambda x: x.elo, reverse=True)
        self.participants = sorted_participants + not_ranked

    async def seed_participants(self, remove_unchecked: bool = False):
        """
        Seed the participants if ranking info is configured.

        .. warning:: If an exception occurs, the list of participants will be rolled back to its
            previous state, then the error propagates.

        Parameters
        ----------
        remove_unchecked: bool
            If unchecked members should be removed from the internal list and the upload. Defaults
            to `False`
        """
        prev_participants = copy(self.participants)
        try:
            if self.ranking["league_name"] and self.ranking["league_id"]:
                await self._fetch_braacket_ranking_info()
                await self._seed_participants()
            if remove_unchecked is True:
                self.participants = [x for x in self.participants if x.checked_in]
        except Exception:
            # roll back to a previous state
            self.participants = prev_participants
            raise

    async def _background_seed_and_upload(self):
        """
        Run self.seed_participants_and_upload, but catch and log exceptions to the to channel.

        Used when it needs to be ran in the background (register/checkin automated close, no
        context), because an issue with this needs to be told.
        """
        try:
            await self.seed_participants()
            await self.add_participants()
        except Exception as e:
            log.error(
                f"[Guild {self.guild.id}] Can't seed and upload participants (background).",
                exc_info=e,
            )
            await self.to_channel.send(
                _(
                    ":warning: An issue occured when trying to seed and upload participants "
                    "after registration/checkin close. Try running it manually with `{prefix}"
                    "upload`, and contact admins if the issue persists."
                ).format(prefix=self.bot_prefix)
            )

    # starting the tournament...
    async def send_start_messages(self):
        """
        Send the required messages when starting the tournament.

        Depending on the configured channels, announcements will be sent in:

        *   The announcements channel
        *   The scores channel
        *   The queue channel
        """
        scores_channel = (
            _(" in {channel}").format(channel=self.scores_channel.mention)
            if self.scores_channel
            else ""
        )
        messages = {
            self.announcements_channel: _(
                "The tournament **{tournament}** has started! Bracket: {bracket}\n"
                ":white_small_square: You can access it "
                "anytime with the `{prefix}bracket` command.\n"
                ":white_small_square: You can check the current "
                "streams with the `{prefix}streams` command.\n\n"
                "{participant} Please read the instructions :\n"
                "{queue_channel}"
                "{rules_channel}"
                ":white_small_square: The winner of a set must report the score **as soon as "
                "possible**{scores_channel} with the `{prefix}win` command.\n"
                ":white_small_square: You can disqualify from the tournament with the "
                "`{prefix}dq` command, or just abandon your current set with the `{prefix}ff` "
                "command.\n"
                ":white_small_square: In case of lag making the game unplayable, use the `{prefix}"
                "lag` command to call the T.O.\n"
                "{delay}."
            ).format(
                tournament=self.name,
                bracket=self.url,
                participant=self.participant_role.mention,
                queue_channel=_(
                    ":white_small_square: Your sets are announced in {channel}.\n"
                ).format(channel=self.queue_channel.mention)
                if self.queue_channel
                else "",
                rules_channel=_(
                    ":white_small_square: The ruleset is available in {channel}.\n"
                ).format(channel=self.ruleset_channel.mention)
                if self.ruleset_channel
                else "",
                scores_channel=scores_channel,
                delay=_(
                    ":timer: **You will automatically be disqualified if you don't talk in your "
                    "channel within the first {delay} minutes.**"
                ).format(delay=self.delay)
                if self.delay != 0
                else "",
                prefix=self.bot_prefix,
            ),
            self.scores_channel: _(
                ":information_source: Management of the scores for the "
                "tournament **{tournament}** is automated:\n"
                ":white_small_square: Only **the winner of the set** "
                "sends his score with the `{prefix}win` command.\n"
                ":white_small_square: You must follow this "
                "format: `{prefix}win 2-0, 3-2, 3-1, ...`.\n"
                ":white_small_square: Look at the bracket to **check** the informations: {url}\n"
                ":white_small_square: In case of a wrong input, contact a T.O. for a manual fix."
            ).format(tournament=self.name, url=self.url, prefix=self.bot_prefix),
            self.queue_channel: _(
                ":information_source: **Set launch is automated.** "
                "Please follow the instructions in this channel.\n"
                ":white_small_square: Any streamed set will be "
                "announced here, and in your channel.\n"
                ":white_small_square: Any BO5 set will be precised here and in your channel.\n"
                ":white_small_square: The player beginning the bans is picked and "
                "annonced in your channel (you can also use `{prefix}flip`).\n\n{dq}"
            ).format(
                prefix=self.bot_prefix,
                dq=_(
                    ":timer: **You will be disqualified if you were not active in your channel** "
                    "within the {delay} first minutes after the set launch."
                ).format(delay=self.delay)
                if self.delay > 0
                else "",
            ),
        }
        for channel, message in messages.items():
            if channel is None:
                continue
            try:
                await channel.send(message)
            except discord.HTTPException as e:
                log.error(f"[Guild {self.guild.id}] Can't send message in {channel}.", exc_info=e)

    # now this is the loop task stuff, the one that runs during the tournament (not other phases)
    async def announce_sets(self):
        """
        Wraps the messages stored in `matches_to_announce` and sends them in the `queue_channel`.
        """
        if not self.queue_channel:
            return
        message = ""
        for match in self.matches_to_announce:
            message += match + "\n"
        self.matches_to_announce = []
        for page in pagify(message):
            await self.queue_channel.send(
                page, allowed_mentions=discord.AllowedMentions(users=False)
            )

    async def launch_sets(self):
        """
        Launch pending matches, creating a channel and marking the match as ongoing.

        This only launches 20 matches max.

        This is wrapped inside `asyncio.gather`, so errors will not propagate.
        """
        match: Match
        coros = []
        # islice will limit the output to 20. see this as list[:20] but with a generator
        for i, match in enumerate(
            islice(filter(lambda x: x.status == "pending" and x.channel is None, self.matches), 20)
        ):
            # we get the category in the iteration instead of the gather
            # because if all functions call _get_available_category at the same time,
            # a new category will be returned for each
            bracket = "winner" if match.round > 0 else "loser"
            category = await self._get_available_category(bracket, i)
            coros.append(match.launch(category=category))
        if not coros:
            return
        results = await asyncio.gather(*coros, return_exceptions=True)
        for result in filter(None, results):
            log.error(f"[Guild {self.guild.id}] Can't launch a set.", exc_info=result)
        await self.announce_sets()

    def update_streamer_list(self):
        """
        Update the internal streamer's list (next stream attr)
        """
        for streamer in self.streamers:
            streamer._update_list()

    async def launch_streams(self):
        """
        Launch the streams (call the next matches in the streamer's queue).

        You must call `update_streamer_list` first.
        """
        match: Match
        for match in filter(lambda x: x.streamer and x.on_hold, self.matches):
            if match.streamer.current_match and match.streamer.current_match.id == match.id:
                await match.start_stream()

    async def check_for_channel_timeout(self):
        """
        Look through the ongoing/finished matches and compare durations to see if AFK check or
        channel deletion is required, and proceed.
        """
        match: Match
        for i, match in filter(
            lambda x: x[1].status != "pending" and x[1].channel is not None,
            enumerate(self.matches),
        ):
            if self.delay > 0 and match.status == "ongoing":
                if not match.checked_dq and match.duration > timedelta(minutes=self.delay):
                    log.debug(f"Checking inactivity for match {match.set}")
                    await match.check_inactive()
            elif match.status == "finished":
                if match.channel and (match.end_time + timedelta(minutes=5)) < datetime.now(
                    self.tz
                ):
                    log.debug(f"Checking deletion for match {match.set}")
                    try:
                        await match.channel.delete(reason=_("5 minutes passed after set end."))
                    except discord.HTTPException as e:
                        log.warn(
                            f"[Guild {self.guild.id}] Can't delete set channel #{match.set}.",
                            exc_info=e,
                        )
                    del self.matches[i]

    async def check_for_too_long_matches(self):
        """
        Look through the ongoing matches and verifies the duration. Warn if necessary.
        """
        match: Match
        for match in filter(
            lambda x: x.status == "ongoing" and x.channel and not x.on_hold and x.streamer is None,
            self.matches,
        ):
            max_length = self.time_until_warn["bo5" if match.is_bo5 else "bo3"]
            if match.warned is True:
                continue
            if not max_length[0]:
                continue
            if match.warned is None:
                if match.duration > timedelta(minutes=max_length[0]):
                    await match.warn_length()
            elif max_length[1] and datetime.now(self.tz) > match.warned + timedelta(
                minutes=max_length[1]
            ):
                await match.warn_to_length()

    async def _loop_task(self):
        if self.task_errors >= MAX_ERRORS:
            log.critical(f"[Guild {self.guild.id}] Reached 5 errors, closing the task...")
            try:
                await self.to_channel.send(
                    _(
                        ":warning: **Attention**\nMultiple bugs occured within the loop task. "
                        "It is therefore stopped. The bot will stop refreshing informations "
                        "and launching matches.\nIf you believe the issue is fixed, resume "
                        "the tournament with `{prefix}tfix resumetask`, else contact bot "
                        "administrators."
                    ).format(prefix=self.bot_prefix)
                )
            except Exception as e:
                log.error(f"[Guild {self.guild.id}] Can't tell TOs of the above bug.", exc_info=e)
            finally:
                self.stop_loop_task()
            return  # shouldn't be reached but to make sure
        try:
            await self._update_participants_list()
            await self._update_match_list()
            self.update_streamer_list()
        except Exception as e:
            log.error(
                f"[Guild {self.guild.id}] Can't update internal match and participant list! "
                "This may be an error from the upstream bracket, or the bot failed when "
                "checking for changes.",
                exc_info=e,
            )
            self.task_errors += 1
            return
        coros = [
            self.launch_sets(),
            self.check_for_channel_timeout(),
            self.check_for_too_long_matches(),
        ]
        results = await asyncio.gather(*coros, return_exceptions=True)
        for i, result in enumerate(results):
            if result is None:
                continue
            log.warning(f"[Guild {self.guild.id}] Failed with coro {coros[i]}.", exc_info=result)
            self.task_errors += 1
        try:
            await self.launch_streams()
        except Exception as e:
            log.error(f"[Guild {self.guild.id}] Can't update streams.", exc_info=e)
            self.task_errors += 1
        # saving is done after all of our jobs, so the data shouldn't move too much
        await self.save()

    @tasks.loop(seconds=15)
    async def loop_task(self):
        """
        A `discord.ext.tasks.Loop` object, started with the tournament's start and running each 15
        seconds.

        Does the required background stuff, such as updating the matches list, launch new matches,
        update streamers, check for AFK...

        Running this will acquire our `lock`.

        See the documentation on a Loop object for more details.

        .. warning:: Use `start_loop_task` for starting the task, not `Loop.start
            <discord.ext.tasks.Loop.start>`.

        Raises
        ------
        asyncio.TimeoutError
            Running the task took more than 30 seconds
        """
        # we're using a lock to prevent actions such as score setting of DQs being done while we're
        # updating the match list, which can make the bot think there were manual bracket changes
        try:
            async with self.lock:
                # since this will block other commands, we put an uncatched timeout
                await asyncio.wait_for(self._loop_task(), 30)
        except Exception:
            raise
        else:
            if self.task_errors:
                # there were previous errors but the task ran without any new exception
                # so we're resetting the errors count (or 502 errors will keep cancelling the task)
                self.task_errors = 0

    loop_task.__doc__ = loop_task.coro.__doc__

    async def cancel_timeouts(self):
        """
        Sometimes relaunching the bot after too long will result in a lot of DQs due to AFK checks,
        so this function will cancel all AFK checks for the matches that are going to have
        players DQed.
        """
        if self.delay == 0:
            return
        to_timeout = [
            x
            for x in self.matches
            if x.status == "ongoing"
            and x.checked_dq is False
            and x.duration is not None
            and x.duration > timedelta(minutes=self.delay)
            and (x.player1.spoke is False or x.player2.spoke is False)
        ]
        if not to_timeout:
            return
        log.warning(
            f"[Guild {self.guild.id}] Cancelling DQ checks for {len(to_timeout)} "
            "matches due to loop task being resumed."
        )
        for match in to_timeout:
            match.checked_dq = True
        await self.to_channel.send(
            _(
                ":information_source: Task is being resumed after some time. To prevent "
                "participants being incorrectly marked as AFK, {len} matches' AFK check are "
                "disabled."
            ).format(len=len(to_timeout))
        )

    async def start_loop_task(self):
        """
        Starts the internal loop task.

        This will check for possible leftovers and cancel any previous task matching our name
        within the current asyncio loop. We **do not** want duplicated tasks, as this will result
        in the worst nightmare (RIP DashDances #36 and Super Smash Bronol #46).

        Then we try to prevent abusive disqualifications with `cancel_timeouts`. Oh and we also
        set a contextual locale for i18n, see
        `redbot.core.i18n.set_contextual_locales_from_guild`.

        Finally, the task is started and given the name "Tournament {tournamet_id}"
        """
        # We had some issues with duplicated tasks, this isn't even supposed to be possible, but
        # it somehow happened, and more than once. Having duplicated tasks is the worst scenario,
        # all channels and messages are duplicated, and most commands won't work,
        # ruining a tournament
        #
        # To prevent this from happening, we're giving a name to our task (based on ID) and
        # check if there are tasks with the same name within the current asyncio loop
        # If we find tasks with matching names, we cancel them
        #
        task_name = f"Tournament {self.id}"
        old_tasks = [x for x in asyncio.all_tasks() if x.get_name() == task_name]
        if old_tasks:
            log.warning(f"[Guild {self.guild.id}] Found old tasks, cancelling")
            for old_task in old_tasks:
                if not old_task.done():
                    old_task.cancel()
        try:
            await self.cancel_timeouts()
        except Exception as e:
            log.error(
                f"[Guild {self.guild.id}] Failed cancelling timeouts. "
                "Loop task will still be resumed.",
                exc_info=e,
            )
        await set_contextual_locales_from_guild(self.bot, self.guild)
        self.task = self.loop_task.start()
        self.task.set_name(task_name)

    def stop_loop_task(self):
        """
        Stops the loop task. This is preferred over `discord.ext.tasks.Loop.cancel`.
        """
        if self.task and not self.task.done():
            self.task.cancel()

    # debug util
    # def _debug_dump(self):
    #     file = open(cog_data_path(raw_name="Tournaments") / "debug.txt", "w+")
    #     s = self
    #     content = (
    #         f"----- TOURNAMENT {s.name} -----\n"
    #         f"url={s.url} id={s.id} status={s.status} phase={s.phase}\n"
    #         f"tstart={s.tournament_start}\nrstart={s.register_start} "
    #         f"rsecstart={s.register_second_start} rstop={s.register_stop}\n"
    #         f"cstart={s.checkin_start} cstop={s.checkin_stop}\n"
    #         f"next_event={s.next_scheduled_event()} ignored={s.ignored_events}\n"
    #         f"rphase={s.register_phase} participantslen={len(s.participants)}\n"
    #         f"cphase={s.register_phase} "
    #         f"checkedlen={len([x for x in s.participants if x.checked_in])}"
    #     )
    #     content += "\n\n\n"
    #     m: Match
    #     for i, m in enumerate(self.matches):
    #         if m.start_time and m.checked_dq is False:
    #             time_until_dq_check = (
    #                 m.start_time + timedelta(minutes=self.delay)
    #             ) - datetime.now(self.tz)
    #         else:
    #             time_until_dq_check = None
    #         if m.end_time:
    #             time_until_delete = (m.end_time + timedelta(minutes=5)) - datetime.now(self.tz)
    #         else:
    #             time_until_delete = None
    #         content += (
    #             f"----- MATCH {i} -----\n"
    #             f"status={m.status} round={m.round} set={m.set} id={m.id}\n"
    #             f"start_time={m.start_time.strftime('%H:%M:%S') if m.start_time else None} "
    #             f"end_time={m.end_time.strftime('%H:%M:%S') if m.end_time else None} "
    #             f"underway={m.underway} channel={m.channel.id if m.channel else None}\n"
    #             f"checked_dq={m.checked_dq} time_until_dq_check={time_until_dq_check} "
    #             f"time_until_delete={time_until_delete}\n"
    #             f"player1= name={m.player1} player_id={m.player1.player_id} spoke="
    #             f"{m.player1.spoke} discord_id={m.player1.id}\n"
    #             f"player1= name={m.player2} player_id={m.player2.player_id} spoke="
    #             f"{m.player2.spoke} discord_id={m.player2.id}\n\n"
    #         )
    #     content += "\n\n\n"
    #     s: Streamer
    #     for i, s in enumerate(self.streamers):
    #         content += (
    #             f"----- STREAMER {i} -----\n"
    #             f"link={s.link} room_id={s.room_id} room_code={s.room_code}\n"
    #             f"member={s.member}\n"
    #             f"current_match={s.current_match}\n"
    #             f"matches={s.matches}\n\n"
    #         )
    #     content += "\n\n\n"
    #     p: Participant
    #     for i, p in enumerate(self.participants):
    #         content += (
    #             f"----- PARTICIPANT {i} -----\n"
    #             f"name={p} id={p.id} player_id={p.player_id}\n"
    #             f"match_set={p.match.set if p.match else None} match_id="
    #             f"{p.match.id if p.match else None} spoke={p.spoke} check={p.checked_in}\n\n"
    #         )
    #     file.write(content)
    #     file.close()

    # async def debug_loop_task(self):

    #     while True:
    #         self._debug_dump()
    #         await asyncio.sleep(1)

    # abstract methods that will have to be overwritten by the class that inherits from this
    # represents the API calls done to the remote bracket
    async def _get_all_rounds(self) -> List[int]:
        """
        Return a list of all rounds in the bracket. This is used to determine the top 8.

        This is a new method because our Match class will not be created without players, so
        we add this new method which only fetch what we need.

        Returns
        -------
        List[int]
            The list of rounds.
        """
        raise NotImplementedError

    async def _update_participants_list(self):
        """
        Updates the internal list of participants, checking for changes such as:

        *   Player DQ/removal
        *   New player added (pre game)

        .. warning:: A name change on remote is considered as a player removal + addition. If the
            name doesn't match any member, he will be rejected.
        """
        raise NotImplementedError

    async def _update_match_list(self):
        """
        Updates the internal list of changes, checking for changes such as:

        *   Score set manually

        *   Score modified (if there are ongoing/finished sets beyond this match in the bracket,
            they will be reset)

        *   Match reset (the set will be relaunched, ongoing/finished sets beyond this match in
            the bracket will be reset)
        """
        raise NotImplementedError

    async def start(self):
        """
        Starts the tournament.

        Raises
        ------
        RuntimeError
            The tournament is already started.
        """
        raise NotImplementedError

    async def stop(self):
        """
        Stops the tournament.

        Raises
        ------
        RuntimeError
            The tournament is already stopped or not started.
        """
        raise NotImplementedError

    async def add_participant(self, name: str, seed: Optional[int] = None):
        """
        Adds a participant to the tournament.

        Parameters
        ----------
        name: str
            The name of the participant
        seed: int
            The participant's new seed. Must be between 1 and the current number of participants
            (including the new record). Omit to place at the bottom.
        """
        raise NotImplementedError

    async def add_participants(
        self, participants: Optional[List[Participant]] = None, force: bool = False
    ) -> int:
        """
        Adds a list of participants to the tournament, ordered as you want them to be seeded.
        The participants will have their `Participant.player_id` updated as needed.

        Parameters
        ----------
        participants: Optional[List[Participant]]
            The list of participants. The first element will be seeded 1. If not provided, will
            use the instance's `participants` attribute instead.
        force: bool
            If you want the bot to override the previous list of participants on the bracket.
            Defaults to `False`.

            *   If set to `True`: All manually added participants and seeding will be lost, and
                the new list will be exactly the same as what's provided. All player IDs will
                be modified.

            *   If set to `False`: The bot will call `list_participants` and remove all elements
                from the list where the player ID is already inside the upstream list. Then we
                bulk add what's remaining, without clearing the rest.

                Participants are still seeded, but at the end, separated from the rest.

        Returns
        -------
        int
            How many members were appended to the list. Can be useful for knowing if the bot
            appended participants or if it was an initial upload (or forced).

        Raise
        -----
        RuntimeError
            The list of participants provided was empty, or there was nothing new to upload.
        """
        raise NotImplementedError

    async def destroy_player(self, player_id: str):
        """
        Destroys a player. This is the same call as Player.destroy, but only the player ID is
        needed. Useful for unavailable discord member.

        Parameters
        ----------
        player_id: str
            The player to remove.
        """
        raise NotImplementedError

    async def list_participants(self) -> List[Participant]:
        """
        Returns the list of participants from the tournament host.

        Returns
        -------
        List[str]
            The list of participants.
        """
        raise NotImplementedError

    async def list_matches(self) -> List[Match]:
        """
        Returns the list of matches from the tournament host.

        Returns
        -------
        List[str]
            The list of matches.
        """
        raise NotImplementedError

    async def reset(self):
        """
        Resets the bracket.
        """
        raise NotImplementedError


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
        tournament: Tournament,
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
        self.matches: List[Union[Match, int]] = []
        self.current_match: Optional[Match] = None

    @classmethod
    def from_saved_data(cls, tournament: Tournament, data: dict):
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
                if match.status == "finished":
                    errors[_set] = _("That match is finished.")
                    continue
                if add is False:
                    continue
                match.streamer = self
                if match.status == "ongoing":
                    # match is ongoing, we have to tell players
                    if not self.matches:
                        # first match in the list, no need to interrupt, just send info
                        match.on_hold = False
                    else:
                        # match has to be paused
                        match.on_hold = True
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
                if match_object.status != "pending":
                    continue
                match_object.streamer = self
                match_object.on_hold = True
                matches.append(match_object)
            else:
                matches.append(match)
        self.matches = matches
        if self.current_match:
            if self.current_match.status != "finished":
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
