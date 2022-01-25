import discord
import logging
import asyncio
import contextlib

from discord.ui import View
from random import choice
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional, List, Union

from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_timedelta

from ..components import LagTestButton, ScoreEntryButton
from ..enums import MatchPhase

if TYPE_CHECKING:
    from .match import Match
    from .participant import Participant
    from .streamer import Streamer
    from .tournament import Tournament

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)


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
    phase: MatchPhase
        Defines the current state of the match.
    warned: Optional[Union[datetime, bool]]
        Defines if there was a warn for duration. `None` if no warn was sent, `datetime.datetime`
        if there was one first warn sent (correspond to the time when it was send, we rely on that
        to know when to send the second warn), and finally `True` when the second warn is sent
        (to the T.O.s).
    streamer: Optional[Streamer]
        The streamer assigned to this match, if any.
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
        tournament: "Tournament",
        round: int,
        set: str,
        id: int,
        underway: bool,
        player1: "Participant",
        player2: "Participant",
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
        self.phase = MatchPhase.PENDING
        self.warned: Optional[Union[datetime, bool]] = None
        # time of the first warn for duration, if any. if a second warn was sent, set to True
        self.streamer: Optional["Streamer"] = None
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

        self.message: Optional[discord.Message] = None
        self.score_entry_button = ScoreEntryButton(self)
        self.lag_test_button = LagTestButton(self)
        self.view = View()
        if self.tournament.buttons.stages:
            self.view.add_item(self.tournament.buttons.stages)
        if self.tournament.buttons.counters:
            self.view.add_item(self.tournament.buttons.counters)
        if self.tournament.buttons.ruleset:
            self.view.add_item(self.tournament.buttons.ruleset)
        self.view.add_item(self.tournament.buttons.bracket)
        self.view.add_item(self.score_entry_button)
        self.view.add_item(self.lag_test_button)

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
    async def from_saved_data(
        cls, tournament: "Tournament", player1, player2, data: dict
    ) -> "Match":
        match = cls(
            tournament, data["round"], data["set"], data["id"], data["underway"], player1, player2
        )
        match.channel = tournament.guild.get_channel(data["channel"])
        match.message = await match.channel.fetch_message(data["message"])
        warned = data["warned"]
        if isinstance(warned, bool) or warned is None:
            match.warned = warned
        else:
            match.warned = datetime.fromtimestamp(warned, tz=tournament.tz)
        match.phase = MatchPhase(data["phase"])
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
            "phase": self.phase.value,
            "checked_dq": self.checked_dq,
            "warned": self.warned.timestamp()
            if isinstance(self.warned, datetime)
            else self.warned,
            "message": self.message.id if self.message else None,
        }

    async def _enable_buttons(self):
        self.score_entry_button.disabled = False
        self.lag_test_button.disabled = False
        if not self.message:
            return
        await self.message.edit(view=self.view)

    async def _disable_buttons(self):
        self.score_entry_button.disabled = True
        self.lag_test_button.disabled = True
        if not self.message:
            return
        await self.message.edit(view=self.view)

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
        message += _(
            ":white_small_square: **As soon as the set is done**, the winner "
            "sets the score with the button below.\n"
            ":arrow_forward: You will play this set as a {type}.\n"
        ).format(
            type=_("**BO5** *(best of 5)*") if self.is_bo5 else _("**BO3** *(best of 3)*"),
        )
        if self.tournament.settings.baninfo:
            chosen_player = choice([self.player1, self.player2])
            message += _(
                ":game_die: **{player}** was picked to begin the bans *({baninfo})*.\n"
            ).format(player=chosen_player.mention, baninfo=self.tournament.settings.baninfo)
        if self.streamer is not None and self.phase == MatchPhase.ON_HOLD:
            await self._disable_buttons()
            message += _(
                "**\nYou will be on stream on {streamer}!**\n"
                ":warning: **Do not play your set for now and wait for your turn.** "
                "I will send a message once it is your turn with instructions."
            ).format(streamer=self.streamer.link)
            # else, we're about to send another message with instructions

        try:
            self.message = await self.channel.send(message, view=self.view)
        except discord.HTTPException as e:
            log.error(
                f"[Guild {self.guild.id}] Can't send messages for the set {self.set}",
                exc_info=e,
            )
            return
        await self.message.pin()
        self.tournament.matches_to_announce.append(
            _(
                ":arrow_forward: **{name}** ({bo_type}): {player1} vs {player2}"
                "{on_stream} {top8} in {channel}."
            ).format(
                name=self.round_name,
                bo_type=_("BO5") if self.is_bo5 else _("BO3"),
                player1=self.player1.mention,
                player2=self.player2.mention,
                on_stream=_(" **on stream!**") if self.streamer else "",
                top8=top8,
                channel=self.channel.mention,
            )
        )

    async def start_stream(self):
        """
        Send a pending set, awaiting for its turn, on stream. Only call this if there's a streamer.
        """
        if self.streamer.room_id:
            access = _("\n\nHere are the access codes:\nID: {id}\nPasscode: {passcode}").format(
                id=self.streamer.room_id, passcode=self.streamer.room_code
            )
        else:
            access = ""
        if self.phase != MatchPhase.ONGOING:
            await self._start()
        self.checked_dq = True
        await self.channel.send(
            _("You can go on stream on {channel} !{access}").format(
                channel=self.streamer.link, access=access
            )
        )
        if self.tournament.channels.stream:
            await self.tournament.channels.stream.send(
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
        self.checked_dq = True
        if self.phase == MatchPhase.ON_HOLD:
            self.start_time = None
            self.underway = False
            await self.channel.send(
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
                await self.tournament.channels.to.send(
                    _(
                        "There was an issue unmarking set {set} as underway. The bracket may not "
                        "display correct informations, but this isn't critical at all.\n"
                        "Players may have issues setting their score, "
                        "you can set that manually on the bracket."
                    ).format(set=self.channel.mention if self.channel else f"#{self.set}")
                )
                await self.channel.send(
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
            await self.channel.send(
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
        self.streamer = None
        await self._start()
        await self.channel.send(
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
        self.phase = MatchPhase.ONGOING
        self.underway = True
        self.checked_dq = False
        self.start_time = datetime.now(self.tournament.tz)
        try:
            await asyncio.wait_for(self.mark_as_underway(), timeout=60)
        except Exception as e:
            log.warning(
                f"[Guild {self.guild.id}] Can't mark set {self.set} as underway.", exc_info=e
            )
            await self.tournament.channels.to.send(
                _(
                    "There was an issue marking set {set} as underway. The bracket may not "
                    "display correct informations, but this isn't critical at all.\n"
                    "Players may have issues setting their score, "
                    "you can set that manually on the bracket."
                ).format(set=self.channel.mention if self.channel else f"#{self.set}")
            )
            await self.channel.send(
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
        if self.phase != MatchPhase.ON_HOLD:
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
            self.phase = MatchPhase.ONGOING
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
            await self.tournament.channels.to.send(
                _(
                    ":information_source: **Automatic DQ** of {player1} and {player2} for "
                    "inactivity, the set #{set} is cancelled."
                ).format(player1=self.player1.mention, player2=self.player2.mention, set=self.set)
            )
            self.channel = None
            await self.cancel()
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
                await self.tournament.channels.to.send(
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
                await self.cancel()
                break

    async def warn_length(self):
        """
        Warn players in their channels because of the duration of their match.
        """
        message = _(
            ":warning: This match is taking a lot of time!\n"
            "As soon as this is finished, set your score using the button "
            "on the pinned message or with the command `{prefix}win`."
        ).format(prefix=self.tournament.bot_prefix)
        time = self.tournament.settings.time_until_warn["bo5" if self.is_bo5 else "bo3"][1]
        if time:
            message += _(
                "\nT.O.s will be warned if this match is still ongoing in {time}."
            ).format(time=humanize_timedelta(timedelta=time))
        try:
            await self.channel.send(message)
        except discord.NotFound:
            self.channel = None
        self.warned = datetime.now(self.tournament.tz)

    async def warn_to_length(self):
        """
        Warn T.O.s because of the duration of this match. Also tell the players
        """
        await self.tournament.channels.to.send(
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
        await self.channel.send(_("Your match is taking too much time, T.O.s were warned."))

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
        await self.cancel()
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

    async def disqualify(self, player: Union["Participant", int]):
        """
        Called when a player in the set is destroyed.

        There is no API call, just messages sent to the players.

        player: Union[Participant, int]
            The disqualified player. Provide an `int` if the member left.
        """
        await self.cancel()
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

    async def forfeit(self, player: "Participant"):
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
        await self.cancel()
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

    async def cancel(self):
        """
        Mark a match as finished (updated `status` and `end_time` + calls `Participant.reset`)
        """
        try:
            await self._disable_buttons()
        except Exception:
            log.warn(
                f"[Guild {self.tournament.guild.id}] Failed to disable buttons for set {self.set}",
                exc_info=True,
            )
        with contextlib.suppress(AttributeError):
            self.player1.reset()
            self.player2.reset()
        self.phase = MatchPhase.DONE
        self.end_time = datetime.now(self.tournament.tz)

    async def set_scores(
        self, player1_score: int, player2_score: int, winner: Optional["Participant"] = None
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
