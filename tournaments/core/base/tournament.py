import discord
import logging
import asyncio
import aiohttp
import aiofiles
import aiofiles.os
import filecmp
import csv
import shutil

from discord.ui import View
from discord.ext import tasks
from random import shuffle
from itertools import islice
from datetime import datetime, timedelta, timezone
from babel.dates import format_date, format_time
from copy import copy
from typing import Optional, Tuple, List, Union

from redbot import __version__ as red_version
from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.i18n import Translator, get_babel_locale, set_contextual_locales_from_guild
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import humanize_timedelta, pagify

from .match import Match
from .participant import Participant
from .streamer import Streamer

from ..enums import Phase, EventPhase, MatchPhase
from ..dataclass import (
    Buttons,
    Channels,
    Roles,
    RegisterEvent,
    CheckinEvent,
    Settings,
)

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)

MAX_ERRORS = 5
TIME_UNTIL_CHANNEL_DELETION = 300
TIME_UNTIL_TIMEOUT_DQ = 300


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
    ignored_events: list
        A list of events to ignore (checkin/register start/stop)
    matches_to_announce: List[str]
        A list of strings to announce in the defined queue channel. This is done to prevent
        sending too many messages at once and hitting ratelimits, so we wrap them together.
    last_ranking_fetch: Optional[datetime]
        The last time when ranking data was fetched. There is a 5 min cooldown between requests.

    roles: Roles
        An object that stores all roles for the tournament.
    channels: Channels
        An object that stores all channels for the tournament.

    credentials: dict
        Credentials for connecting to the bracket

    settings: Settings
        An object that stores misc settings for the tournament.

    register: RegisterEvent
        Data about registrations, such as start and stop time, or the current phase.
    checkin: CheckinEvent
        Data about check-in, such as start and stop time, current phase and reminders.


    lock: asyncio.Lock
        A lock acquired when the tournament is being refreshed by the loop task, to prevent
        commands like win or dq from being run at the same time.

        *New since beta 13:* The lock is also acquired with the ``[p]in`` command to prevent too
        many concurrent tasks, breaking the limit.
    task: asyncio.Task
        The task for the `loop_task` function (`discord.ext.tasks.Loop` object)
    task_errors: int
        Number of errors that occured within the loop task. If it reaches 5, task is cancelled.

    phase: Phase
        Something very important! Used for knowing what is the current phase of the tournament.
        It is also used by commands to know if it is allowed to run.
    top_8: dict
        Represents when the top 8 and bo5 begins in the bracket.
    buttons: Buttons
        A collection of buttons that will be used during the tournament, prevents building them
        multiple times.
    mentions: discord.AllowedMentions
        The allowed mentions object for the bot announcements.
    """

    def __init__(
        self,
        bot: Red,
        guild: discord.Guild,
        config: Config,
        custom_config: str,
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
        # Basic attributes
        self.bot = bot
        self.guild = guild
        self.data = config
        self.config = custom_config
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

        # Initialize empty attributes
        self.participants: List[Participant] = []
        self.matches: List[Match] = []
        self.streamers: List[Streamer] = []
        self.winner_categories: List[discord.CategoryChannel] = []
        self.loser_categories: List[discord.CategoryChannel] = []
        self.ignored_events = []  # list of scheduled events to skip (register_start/checkin_stop)
        self.matches_to_announce: List[str] = []  # matches to announce in the queue channel
        self.last_ranking_fetch: Optional[datetime] = None  # 5 min cooldown on ranking fetch

        # Loading roles and channels
        self.roles = Roles(guild, data)
        self.channels = Channels(guild, data)

        # fitting to achallonge's requirements
        self.credentials = data["credentials"]
        self.credentials["login"] = self.credentials.pop("username")
        self.credentials["password"] = self.credentials.pop("api")

        # Misc settings
        self.settings = Settings(data)

        # Registrations and check-in events
        self.register = RegisterEvent(
            self,
            data["register"]["opening"],
            data["register"]["second_opening"],
            data["register"]["closing"],
        )
        self.checkin = CheckinEvent(self, data["checkin"]["opening"], data["checkin"]["closing"])

        # loop task things
        self.lock = asyncio.Lock()
        self.task: Optional[asyncio.Task] = None
        self.task_errors = 0

        # Other values that have to be initialized
        self.phase = Phase.PENDING  # main tournament phase
        self.top_8 = {
            "winner": {"top8": None, "bo5": None},
            "loser": {"top8": None, "bo5": None},
        }
        self.cancelling = False  # see Tournament.__del__ and Match.__del__
        self.buttons = Buttons(self)  # Register message buttons, saves times to build them once
        self.mentions = (
            discord.AllowedMentions(roles=[self.roles.game]) if self.roles.game else None
        )

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
        custom_config = data.pop("config")
        participants = data.pop("participants")
        matches = data.pop("matches")
        streamers = data.pop("streamers")
        winner_categories = data.pop("winner_categories")
        loser_categories = data.pop("loser_categories")
        phase = Phase(data.pop("phase"))
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
            custom_config,
            **data,
            tournament_start=tournament_start,
            cog_version=cog_version,
            data=config_data,
        )
        if phase == Phase.ONGOING:
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
            match = await tournament.match_object.from_saved_data(
                tournament, player1, player2, data
            )
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
                    await tournament.channels.to.send(
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
                    await tournament.channels.to.send(
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
        tournament.register.phase = EventPhase(register)
        tournament.checkin.phase = EventPhase(checkin)
        tournament.checkin.reminders = checkin_reminders
        tournament.ignored_events = ignored_events
        if register_message_id:
            for channel in (tournament.channels.register, tournament.channels.announcements):
                if not channel:
                    continue
                try:
                    message = await channel.fetch_message(register_message_id)
                except discord.NotFound:
                    pass
                else:
                    tournament.register.message = message
                    break
        if len(tournament.participants) > 0:
            tournament.buttons.unregister.disabled = False
        if tournament.register.phase == EventPhase.ONGOING:
            tournament.buttons.register.disabled = False
            tournament.buttons.unregister.disabled = False
        if tournament.checkin.phase == EventPhase.ONGOING:
            tournament.buttons.checkin.disabled = False
        return tournament

    def to_dict(self) -> dict:
        """Returns a dict ready for Config."""
        offset = self.tournament_start.utcoffset()
        if offset:
            offset = offset.total_seconds()
        else:
            offset = 0
        data = {
            "config": self.config,
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
            "phase": self.phase.value,
            "tournament_type": self.tournament_type,
            "register": self.register.phase.value,
            "checkin": self.checkin.phase.value,
            "checkin_reminders": self.checkin.reminders,
            "ignored_events": self.ignored_events,
            "register_message_id": self.register.message.id if self.register.message else None,
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
        if self.roles.to is not None:
            allowed_roles.append(self.roles.to)
        if self.roles.streamer is not None:
            allowed_roles.append(self.roles.streamer)
        if self.roles.tester is not None:
            allowed_roles.append(self.roles.tester)
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
            "register_start": (self.register.start, self.register.phase == EventPhase.PENDING),
            "checkin_stop": (self.checkin.stop, self.checkin.phase == EventPhase.ONGOING),
            "checkin_start": (self.checkin.start, self.checkin.phase == EventPhase.PENDING),
            "register_second_start": (
                self.register.second_start,
                self.register.phase == EventPhase.ON_HOLD,
            ),
            "register_stop": (self.register.stop, self.register.phase == EventPhase.ONGOING),
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
        dates = [
            (_("Registration start"), self.register.start, "register_start"),
            (_("Registration second start"), self.register.second_start, "register_second_start"),
            (_("Registration stop"), self.register.stop, "register_stop"),
            (_("Check-in start"), self.checkin.start, "checkin_start"),
            (_("Check-in stop"), self.checkin.stop, "checkin_stop"),
        ]
        passed = [(x, y, z) for x, y, z in dates if y and now > y]
        if passed:
            raise RuntimeError(_("Some dates are passed."), passed)
        if (
            self.register.start
            and self.register.stop
            and not self.register.start < self.register.stop
        ):
            dates = [dates[0] + dates[2]]
            raise RuntimeError(_("Registration start and stop times conflict."), dates)
        if self.register.second_start and (
            (self.register.start and not self.register.start < self.register.second_start)
            or (self.register.stop and not self.register.second_start < self.register.stop)
        ):
            dates = dates[:3]
            raise RuntimeError(_("Second registration start time conflict."), dates)
        if self.checkin.start and self.checkin.stop and not self.checkin.start < self.checkin.stop:
            dates = dates[3:]
            raise RuntimeError(_("Check-in start and stop times conflict."), dates)

    async def _get_available_category(self, dest: str, inc: int = 0):
        position = (
            self.channels.category.position + 1
            if self.channels.category
            else len(self.guild.categories)
        )
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
        if self.settings.start_bo5 > 0:
            top8["winner"]["bo5"] = top8["winner"]["top8"] + self.settings.start_bo5 - 1
        elif self.settings.start_bo5 in (0, 1):
            top8["winner"]["bo5"] = top8["winner"]["top8"] + self.settings.start_bo5
        else:
            top8["winner"]["bo5"] = top8["winner"]["top8"] + self.settings.start_bo5 + 1
        if self.settings.start_bo5 > 1:
            top8["loser"]["bo5"] = min(rounds)  # top 3 is loser final anyway
        else:
            top8["loser"]["bo5"] = top8["loser"]["top8"] - self.settings.start_bo5
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
        await self.channels.to.send(
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
    def _prepare_register_message(self) -> Union[str, View]:
        view = View()
        view.add_item(self.buttons.register)
        view.add_item(self.buttons.unregister)
        view.add_item(self.buttons.checkin)
        view.add_item(self.buttons.bracket)
        if self.checkin.start:
            checkin = _(":white_small_square: __Check-in:__ From {begin} to {end}\n").format(
                begin=self._format_datetime(self.checkin.start, True),
                end=self._format_datetime(self.checkin.stop or self.tournament_start, True),
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
        if self.channels.ruleset:
            ruleset = _(":white_small_square: __Ruleset:__ See {channel}\n").format(
                channel=self.channels.ruleset.mention
            )
        else:
            ruleset = ""
        register_status = _("Registrations are currently **{status}**.").format(
            status=_("open") if self.register.phase == EventPhase.ONGOING else _("closed")
        )
        checkin_status = _("Check-in is currently **{status}**.").format(
            status=_("open") if self.checkin.phase == EventPhase.ONGOING else _("closed")
        )
        content = _(
            "{role}\n"
            "**{t.name}** | *{t.game}*\n\n"
            ":white_small_square: __Date:__ {date}\n"
            ":white_small_square: __Register:__ Closing at {time}\n"
            "{checkin}"
            ":white_small_square: __Participants:__ {limit}\n"
            "{ruleset}\n"
            "{register_status}\n"
            "{checkin_status}\n\n"
            "You can register/unregister to this tournament using the buttons below.\n"
            "*Note: your Discord username will be used in the bracket.*"
        ).format(
            role=self.roles.game.mention if self.roles.game else "",
            t=self,
            date=self._format_datetime(self.tournament_start),
            time=self._format_datetime(self.register.stop or self.tournament_start, True),
            checkin=checkin,
            limit=limit,
            ruleset=ruleset,
            register_status=register_status,
            checkin_status=checkin_status,
        )
        return content, view

    async def _update_register_message(self):
        new_content = self._prepare_register_message()
        if not self.register.message:
            channel = self.channels.register or self.channels.announcements
            try:
                self.register.message = await channel.send(
                    content=new_content[0], allowed_mentions=self.mentions, view=new_content[1]
                )
            except discord.HTTPException:
                log.error(f"[Guild {self.guild.id}] Cannot send register message", exc_info=True)
            await self.save()
            return
        if new_content != self.register.message.content:
            try:
                await self.register.message.edit(content=new_content[0], view=new_content[1])
            except discord.NotFound as e:
                log.warning(
                    f"[Guild {self.guild.id}] Regiser message lost. Recovering...",
                    exc_info=e,
                )
                self.register.message = None
                await self._update_register_message()
            else:
                await self.save()

    async def start_registration(self, second=False):
        """
        Open the registrations and save.

        Parameters
        ----------
        second: bool
            If this is the second time registrations are started (will not annouce the same
            message, and keep updating the same pinned message). Defaults to `False`.
        """
        self.phase = Phase.REGISTER
        self.register.phase = EventPhase.ONGOING
        self.buttons.register.disabled = False
        self.buttons.unregister.disabled = False
        await self._update_register_message()
        if self.channels.announcements and self.channels.register:
            # Let's send a second message anyway
            if second:
                message = _(
                    "{role} Registrations for the tournament **{tournament}** "
                    "are now re-opened in {channel} until {date}!"
                ).format(
                    role=self.roles.game.mention
                    if self.roles.game != self.guild.default_role
                    else "",
                    tournament=self.name,
                    channel=self.channels.register.mention,
                    date=self._format_datetime(self.register.stop or self.tournament_start),
                )
            else:
                message = _(
                    "Registrations for the tournament **{tournament}** are now opened "
                    "in {channel}! Click on the buttons there to register.\n"
                    ":calendar_spiral: This tournament will take place on **{date}**."
                ).format(
                    tournament=self.name,
                    channel=self.channels.register.mention,
                    date=self._format_datetime(self.tournament_start),
                )
            await self.channels.announcements.send(message, allowed_mentions=self.mentions)
        await self.save()

    async def end_registration(self):
        """
        Close the registrations and save.

        If the check-in is also done, participants will be seeded and uploaded.
        """
        if self.register.second_start and self.register.second_start > datetime.now(self.tz):
            self.register.phase = EventPhase.ON_HOLD
        else:
            self.register.phase = EventPhase.DONE
        self.buttons.register.disabled = True
        await self._update_register_message()
        channel = self.channels.register or self.channels.announcements
        await channel.send(_("Registration ended."))
        if not self.next_scheduled_event():
            # no more scheduled events, upload and wait for start
            self.phase = Phase.AWAITING
            await self._background_seed_and_upload()
        await self.save()

    async def start_check_in(self):
        """
        Open the check-in and save.

        This will also calculate and fill the `checkin_reminders` list.
        """
        self.buttons.checkin.disabled = False
        if not self.participants:
            self.checkin.phase = EventPhase.DONE
            message = _("Cancelled check-in start since there are currently no participants. ")
            if not self.next_scheduled_event:
                # no more scheduled events, upload and wait for start
                self.phase = Phase.AWAITING
            else:
                message += _(
                    "Registrations are still ongoing, and new participants are pre-checked."
                )
            await self.channels.to.send(message)
            return
        self.phase = Phase.REGISTER
        self.checkin.phase = EventPhase.ONGOING
        message = _(
            "{role} The check-in for **{t.name}** has started!\n"
            "You have to confirm your presence by clicking the button above{end_time}.\n"
            'If you want to unregister, click the "Unregister" button instead.\n\n'
            ":warning: If you don't check in time, you will be unregistered!"
        ).format(
            t=self,
            role=self.roles.participant.mention,
            end_time=_(" until {}").format(
                self._format_datetime(self.checkin.stop, only_time=True)
            )
            if self.checkin.stop
            else "",
        )
        await self._update_register_message()
        mentions = discord.AllowedMentions(roles=[self.roles.participant])
        channel = self.channels.register or self.channels.announcements
        message = await channel.send(message, allowed_mentions=mentions)
        if self.checkin.stop:
            duration = (self.checkin.stop - datetime.now(self.tz)).total_seconds()
            if duration < 60:
                # don't start the check-in only to end it within a minute
                self.ignored_events.append("checkin_stop")
            else:
                duration //= 60  # number of minutes
                if duration >= 10:
                    self.checkin.reminders.append((5, False))
                if duration >= 20:
                    self.checkin.reminders.append((10, True))
                if duration >= 40:
                    self.checkin.reminders.append((15, False))
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
        channel = self.channels.register or self.channels.announcements
        if not self.checkin.stop:
            return
        members = [x for x in self.participants if not x.checked_in]
        if not members:
            return
        if self.checkin.last_reminder_message:
            try:
                await self.checkin.last_reminder_message.delete()
            except discord.HTTPException:
                log.error(
                    f"Can't remove last check-in call message for guild {self.guild.id}",
                    exc_info=True,
                )
        self.checkin.last_reminder_message = await channel.send(
            _(
                ":clock1: **Check-in reminder!**\n\n- {members}\n\n"
                "You have until {end_time} to check-in, or you'll be unregistered."
            ).format(
                members="\n- ".join([x.mention for x in members]),
                end_time=self._format_datetime(self.checkin.stop, only_time=True),
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
                                (self.checkin.stop - datetime.now(self.tz)).total_seconds() / 60
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
        """
        self.checkin.phase = EventPhase.DONE
        self.buttons.checkin.disabled = True
        to_remove = []
        failed = []
        for member in filter(lambda x: x.checked_in is False, self.participants):
            try:
                await member.remove_roles(
                    self.roles.participant, reason=_("Participant not checked.")
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
            await self.unregister_participant(member, send_dm=False)
        text = _(":information_source: Check-in was ended. {removed}").format(
            removed=_("{} participants didn't check and were unregistered.").format(len(to_remove))
            if to_remove
            else _("No participant was unregistered.")
        )
        if failed:
            text += _("\n\n:warning: {} participants couldn't have their roles removed:\n")
            text += " ".join([x.mention for x in failed])
        for page in pagify(text):
            await self.channels.to.send(page)
        await self._update_register_message()
        channel = self.channels.register or self.channels.announcements
        if channel:
            await channel.send(
                _("Check-in ended. Participants who didn't check are unregistered.")
            )
        if not self.next_scheduled_event:
            # no more scheduled events, upload and wait for start
            self.phase = Phase.AWAITING
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
        await member.add_roles(self.roles.participant, reason=_("Registering to tournament."))
        participant = self.participant_object(member, self)
        if self.checkin.phase == EventPhase.ONGOING or self.checkin.phase == EventPhase.DONE:
            # registering during or after check-in, count as already checked
            participant.checked_in = True
        if not (self.settings.ranking["league_name"] and self.settings.ranking["league_id"]) or (
            self.participants and self.participants[-1].player_id is not None
        ):
            # either there's no ranking, in which case we always upload on register, or
            # last registered participant has a player ID, so we should upload him to the bracket
            # first we seed him, if possible
            try:
                await self.seed_participants()
            except Exception:
                pass  # any exception will roll back the list of participants so we're safe
            await self.add_participant(participant)
        self.participants.append(participant)
        log.debug(f"[Guild {self.guild.id}] Player {member} registered.")
        if (
            self.limit
            and self.settings.autostop_register
            and self.register.phase == EventPhase.ONGOING
            and len(self.participants) >= self.limit
        ):
            await self.end_registration()
        await self.save()
        if not send_dm:
            return

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
            self.roles.participant, reason=_("Unregistering from tournament.")
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
        if self.last_ranking_fetch and self.last_ranking_fetch + timedelta(
            minutes=5
        ) < datetime.now(self.tz):
            # 5 min cooldown on ranking fetch
            return
        league_name, league_id = (
            self.settings.ranking["league_name"],
            self.settings.ranking["league_id"],
        )
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
        self.last_ranking_fetch = datetime.now(self.tz)

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
            if self.settings.ranking["league_name"] and self.settings.ranking["league_id"]:
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
            await self.channels.to.send(
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
        announcements_view = discord.ui.View()
        scores_view = discord.ui.View()
        bracket_button = discord.ui.Button(
            style=discord.ButtonStyle.link,
            label=_("Bracket"),
            emoji="\N{LINK SYMBOL}",
            url=self.url,
        )
        announcements_view.add_item(bracket_button)
        scores_view.add_item(bracket_button)
        if self.channels.ruleset:
            ruleset_button = discord.ui.Button(
                style=discord.ButtonStyle.link,
                label=_("Ruleset"),
                emoji="\N{BLUE BOOK}",
                url=channel_link(self.channels.ruleset),
            )
            announcements_view.add_item(ruleset_button)
            scores_view.add_item(ruleset_button)
        if self.channels.queue:
            queue_button = discord.ui.Button(
                style=discord.ButtonStyle.link,
                label=_("Sets"),
                emoji="\N{CLIPBOARD}\N{VARIATION SELECTOR-16}",
                url=channel_link(self.channels.queue),
            )
            announcements_view.add_item(queue_button)
        messages = {
            self.channels.announcements: (
                _(
                    "The tournament **{tournament}** has started!\n\n"
                    ":white_small_square: Bracket link:`{prefix}bracket`\n"
                    ":white_small_square: List of streams:`{prefix}streams`\n\n"
                    "{participant} Please read the instructions :\n"
                    ":white_small_square: The winner of a set must report the score **as soon as "
                    "possible** with the `{prefix}win` command.\n"
                    ":white_small_square: You can disqualify from the tournament with the "
                    "`{prefix}dq` command, or just abandon your current set with the `{prefix}ff` "
                    "command.\n"
                    ":white_small_square: In case of lag making the game unplayable, "
                    "use the `{prefix}lag` command to call the T.O.\n"
                    "{delay}."
                ).format(
                    tournament=self.name,
                    bracket=self.url,
                    participant=self.roles.participant.mention,
                    delay=_(
                        ":timer: **You will automatically be disqualified if "
                        "you don't talk in your channel within the first {delay}.**"
                    ).format(delay=humanize_timedelta(timedelta=self.settings.delay))
                    if self.settings.delay
                    else "",
                    prefix=self.bot_prefix,
                ),
                announcements_view,
            ),
            self.channels.queue: (
                _(
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
                        ":timer: **You will be disqualified if you were not "
                        "active in your channel** within {delay} after the set launch."
                    ).format(delay=humanize_timedelta(timedelta=self.settings.delay))
                    if self.settings.delay
                    else "",
                ),
                None,
            ),
        }
        for channel, message in messages.items():
            if channel is None:
                continue
            try:
                await channel.send(message[0], view=message[1])
            except discord.HTTPException as e:
                log.error(f"[Guild {self.guild.id}] Can't send message in {channel}.", exc_info=e)

    # now this is the loop task stuff, the one that runs during the tournament (not other phases)
    async def announce_sets(self):
        """
        Wraps the messages stored in `matches_to_announce` and sends them in the `channels.queue`.
        """
        if not self.channels.queue:
            return
        message = ""
        for match in self.matches_to_announce:
            message += match + "\n"
        self.matches_to_announce = []
        for page in pagify(message):
            await self.channels.queue.send(
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
            islice(
                filter(
                    lambda x: x.phase == MatchPhase.PENDING and x.channel is None, self.matches
                ),
                20,
            )
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
        for match in filter(lambda x: x.streamer and x.phase == MatchPhase.ON_HOLD, self.matches):
            if match.streamer.current_match and match.streamer.current_match.id == match.id:
                await match.start_stream()

    async def check_for_channel_timeout(self):
        """
        Look through the ongoing/finished matches and compare durations to see if AFK check or
        channel deletion is required, and proceed.
        """
        match: Match
        for i, match in filter(
            lambda x: x[1].phase != MatchPhase.PENDING and x[1].channel is not None,
            enumerate(self.matches),
        ):
            if self.settings.delay and match.phase == MatchPhase.ONGOING:
                if not match.checked_dq and match.duration > self.settings.delay:
                    log.debug(f"Checking inactivity for match {match.set}")
                    await match.check_inactive()
            elif match.phase == MatchPhase.DONE:
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
            lambda x: x.phase == MatchPhase.ONGOING and x.channel and x.streamer is None,
            self.matches,
        ):
            max_length = self.settings.time_until_warn["bo5" if match.is_bo5 else "bo3"]
            if match.warned is True:
                continue
            if not max_length[0]:
                continue
            if match.warned is None:
                if match.duration > max_length[0]:
                    await match.warn_length()
            elif max_length[1] and datetime.now(self.tz) > match.warned + max_length[1]:
                await match.warn_to_length()

    async def _loop_task(self):
        if self.task_errors >= MAX_ERRORS:
            log.critical(f"[Guild {self.guild.id}] Reached 5 errors, closing the task...")
            try:
                await self.channels.to.send(
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
        if self.settings.delay is None:
            return
        to_timeout = [
            x
            for x in self.matches
            if x.phase == MatchPhase.ONGOING
            and x.checked_dq is False
            and x.duration is not None
            and x.duration > self.settings.delay
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
        await self.channels.to.send(
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
