import discord

from discord.ui import Button
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, List, Mapping, Optional, Tuple

from .enums import EventPhase, StageListType
from .components import RegisterButton, StageListButton, UnregisterButton, CheckInButton

if TYPE_CHECKING:
    from .base import Tournament

__all__ = (
    "Buttons",
    "Channels",
    "Roles",
    "Settings",
    "RegisterEvent",
    "CheckinEvent",
)


class Buttons:
    """
    This is a "shortcut class" for accessing different buttons stored within a `Tournament`
    instance.

    `Tournament` had too many attributes, so we're doing this.

    Attributes
    ----------

    register: discord.ui.Button
        When clicked, user will be registered to the tournament.
    unregister: discord.ui.Button
        When clicked, user will be removed from the tournament.
    checkin: discord.ui.Button
        When clicked, user will check for the tournament.
    bracket:
        A URL button pointing to the bracket.
    """

    def __init__(self, tournament: "Tournament"):
        self.register = RegisterButton(tournament)
        self.unregister = UnregisterButton(tournament)
        self.checkin = CheckInButton(tournament)
        self.bracket = Button(style=discord.ButtonStyle.link, label="Bracket", url=tournament.url)
        if tournament.channels.ruleset:
            self.ruleset = Button(
                style=discord.ButtonStyle.link,
                label="Ruleset",
                emoji="\N{BLUE BOOK}",
                url="https://discord.com/channels/"
                f"{tournament.guild.id}/{tournament.channels.ruleset.id}",
            )
        else:
            self.ruleset = None
        if tournament.settings.stages:
            self.stages = StageListButton(tournament, StageListType.STAGES)
        else:
            self.stages = None
        if tournament.settings.counterpicks:
            self.counters = StageListButton(tournament, StageListType.COUNTERPICKS)
        else:
            self.counters = None


class Channels:
    """
    This is a "shortcut class" for accessing different channels stored within a `Tournament`
    instance.

    Attributes
    ----------

    category: Optional[discord.CategoryChannel]
        The category defined (our categories will be created below)
    announcements: Optional[discord.TextChannel]
        The channel for announcements
    queue: Optional[discord.TextChannel]
        The channel for match queue
    register: Optional[discord.TextChannel]
        The channel for registrations
    scores: Optional[discord.TextChannel]
        The channel for score setting
    stream: Optional[discord.TextChannel]
        The channel for announcing matches on stream
    to: discord.TextChanne]
        The channel for tournament organizers. Send warnings there.
    vip_register: Optional[discord.TextChannel]
        A channel where registrations are always open
    ruleset: Optional[discord.TextChannel]
        Channel for the rules
    """

    def __init__(self, guild: discord.Guild, data: dict):
        self.category: discord.CategoryChannel = guild.get_channel(
            data["channels"].get("category")
        )
        self.announcements: discord.TextChannel = guild.get_channel(
            data["channels"].get("announcements")
        )
        self.queue: discord.TextChannel = guild.get_channel(data["channels"].get("queue"))
        self.register: discord.TextChannel = guild.get_channel(data["channels"].get("register"))
        self.stream: discord.TextChannel = guild.get_channel(data["channels"].get("stream"))
        self.to: discord.TextChannel = guild.get_channel(data["channels"].get("to"))
        self.lag: discord.TextChannel = guild.get_channel(data["channels"].get("lag"))
        self.vip_register: discord.TextChannel = guild.get_channel(
            data["channels"].get("vipregister")
        )
        self.ruleset: discord.TextChannel = guild.get_channel(data["channels"]["ruleset"])


class Roles:
    """
    This is a "shortcut class" for accessing different roles stored within a `Tournament`
    instance.

    Attributes
    ----------

    participant: discord.Role
        The role given to participants
    game: Optional[discord.Role]
        The role that should be attached to the game being played. This will open registrations to
        that role only.
    streamer: Optional[discord.Role]
        Role giving access to stream commands
    to: Optional[discord.Role]
        Role giving access to T.O. commands
    tester: Optional[discord.Role]
        Role pinged when a lag test is invoked
    """

    def __init__(self, guild: discord.Guild, data: dict):
        self.participant: discord.Role = guild.get_role(data["roles"].get("participant"))
        self.game: Optional[discord.Role] = guild.get_role(data["roles"]["player"])
        self.streamer: Optional[discord.Role] = guild.get_role(data["roles"].get("streamer"))
        self.to: Optional[discord.Role] = guild.get_role(data["roles"].get("to"))
        self.tester: Optional[discord.Role] = guild.get_role(data["roles"].get("tester"))


class Settings:
    """
    Tournament settings.

    Attributes
    ----------
    baninfo: Optional[str]
        Baninfo set (ex: 3-4-2)
    ranking: dict
        Data for braacket ranking
    stages: List[str]
        List of allowed stages
    counterpicks: List[str]
        List of allowed counterpicks
    delay: int
        Time in minutes until disqualifying a participant for AFK
    start_bo5: int
        At which round should the tournament switch from BO3 to BO5?
    autostop_register: bool
        If registrations should be closed when the limit is hit.
    time_until_warn: dict
        Represents the different warn times for duration
    """

    def __init__(self, data: dict):
        self.baninfo: str = data["baninfo"]
        self.ranking: dict = data["ranking"]
        self.stages: list = data["stages"]
        self.counterpicks: list = data["counterpicks"]
        self.delay: timedelta = timedelta(seconds=data["delay"]) or None
        self.start_bo5: int = data["start_bo5"]
        self.autostop_register: bool = data["autostop_register"]
        self.time_until_warn: Mapping[str, Tuple[timedelta]] = {
            "bo3": tuple(
                timedelta(seconds=x) or None
                for x in data["time_until_warn"].get("bo3", (1500, 600))
            ),
            "bo5": tuple(
                timedelta(seconds=x) or None
                for x in data["time_until_warn"].get("bo5", (1800, 600))
            ),
        }  # the default values are somehow not loaded into the dict sometimes


class Event:
    """
    Represents an event with a start and stop date, and a phase.

    Attributes
    ----------
    phase: EventPhase
        The current state of the event
    start: Optional[datetime]
        Start time of the event
    stop: Optional[datetime]
        End time of the event
    method_prefix: str
        The prefix of the method that will be executed (e.g. ``register_`` or ``checkin_``)
    """

    method_prefix = ""

    def __init__(self, tournament: "Tournament", start: Optional[int], stop: Optional[int]):
        self.phase = EventPhase.MANUAL
        self.start: Optional[datetime] = None
        self.stop: Optional[datetime] = None

        if start:
            self.start = tournament.tournament_start - timedelta(seconds=start)
            self.phase = EventPhase.PENDING
        else:
            tournament.ignored_events.append(self.method_prefix + "start")

        if stop:
            self.stop = tournament.tournament_start - timedelta(seconds=stop)
        else:
            tournament.ignored_events.append(self.method_prefix + "start")


class RegisterEvent(Event):
    """
    Registrations in a tournament.

    Attributes
    ----------
    second_start: Optional[datetime]
        Second start time of the event
    message: Optional[discord.Message]
        The registrations message being updated over time
    """

    method_prefix = "register_"

    def __init__(
        self,
        tournament: "Tournament",
        start: Optional[int],
        second_start: Optional[int],
        stop: Optional[int],
    ):
        super().__init__(tournament, start, stop)

        self.second_start: Optional[datetime] = None
        if second_start:
            self.second_start = tournament.tournament_start - timedelta(seconds=second_start)
        else:
            tournament.ignored_events.append(self.method_prefix + "second_start")

        self.message: Optional[discord.Message] = None


class CheckinEvent(Event):
    """
    Check-in of the tournament.

    Attributes
    ----------
    reminders: List[Tuple[int, bool]]
        A list of timedeltas for reminding participants to check-in. This is associated to whether
        we should send DMs or not. Timedeltas are substracted from checkin.end
    last_reminder_message: Optional[discord.Message]
        The last reminder message sent. We're deleting the last one before sending a new one.
    """

    method_prefix = "checkin_"

    def __init__(self, tournament: "Tournament", start: Optional[int], stop: Optional[int]):
        super().__init__(tournament, start, stop)
        self.reminders: List[Tuple[int, bool]] = []
        self.last_reminder_message: Optional[discord.Message] = None
