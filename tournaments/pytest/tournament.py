import random
import discord
import pytest

from copy import copy, deepcopy
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from redbot.core import Config

from ..tournaments import Tournaments
from ..objects import ChallongeTournament, Streamer, Match

if TYPE_CHECKING:
    from ..objects import Tournament
    from _pytest.fixtures import SubRequest
    from pytest_mock import MockerFixture
    from redbot.core.bot import Red


@pytest.fixture(scope="package")
def tournaments_cog(config: Config, package_mocker: "MockerFixture", red: "Red"):
    package_mocker.patch.object(Config, "get_conf", side_effect=lambda *args, **kwargs: config)
    n = Tournaments(red)
    n._eject(red)
    n._inject(red)
    yield n
    n.registration_loop.cancel()


def get_all_params():
    def get_id():
        return random.randint(1, 999999999)

    # test configs
    configs = [
        {},  # base config
        {  # simple registrations + checkin
            "register": {"opening": 20, "second_opening": 0, "closing": 10},
            "checkin": {"opening": 60, "closing": 15},
        },
        {  # + autostop + second start
            "register": {"opening": 20, "second_opening": 15, "closing": 10},
            "checkin": {"opening": 60, "closing": 15},
            "autostop_register": True,
        },
        {"delay": 0},  # disabled auto-DQ
        {
            "time_until_warn": {"bo3": (0, 0), "bo5": (0, 0)},
        },  # disabled warnings
        {"roles": {"streamer": get_id(), "to": get_id()}},  # testing roles
        {  # testing channels
            "channels": {
                "announcements": get_id(),
                "category": get_id(),
                "checkin": get_id(),
                "queue": get_id(),
                "register": get_id(),
                "scores": get_id(),
                "stream": get_id(),
                "vipregister": get_id(),
            }
        },
        {  # testing with announcements and no register/checkin channel
            "channels": {
                "announcements": get_id(),
                "category": get_id(),
                "checkin": None,
                "queue": get_id(),
                "register": None,
                "scores": get_id(),
                "stream": get_id(),
                "vipregister": get_id(),
            }
        },
    ]
    for i, config in enumerate(configs):
        try:
            config["roles"]["participant"] = get_id()
        except KeyError:
            config["roles"] = {"participant": get_id()}
        try:
            config["channels"]["to"] = get_id()
        except KeyError:
            config["channels"] = {"to": get_id()}
        yield config
        # return


@pytest.fixture(scope="package", params=get_all_params())
async def cog_data(request: "SubRequest", tournaments_cog: Tournaments, guild: discord.Guild):
    options = request.param
    data = await tournaments_cog.data.guild(guild).all()
    data.update(await tournaments_cog.data.custom("GAME", guild.id, "test game").all())
    data.update(options)
    return data


@pytest.fixture(scope="package", params=[ChallongeTournament])
def tournament_class(request: "SubRequest", package_mocker: "MockerFixture"):
    tm: Tournament = request.param
    package_mocker.patch.object(tm.participant_object, "remove_roles")
    # match_mock = mocker.patch.object(tm.match_object, "__eq__")
    return tm


@pytest.fixture(scope="module")
async def tournament_factory(
    module_mocker: "MockerFixture",
    tournament_class: "Tournament",
    red: "Red",
    guild: discord.Guild,
    config: Config,
    cog_data: dict,
):
    mock = module_mocker

    async def rounds(*args, **kwargs):
        return list(range(-7, 0)) + list(range(1, 9))

    async def request(*args, **kwargs):
        pass

    class TournamentFactory:
        async def get(self):
            attrs = {
                "_get_all_rounds": (rounds, False),
                "request": (request, False),
                "_pytest_cog_data": (cog_data, True),
                "_pytest_red": (red, True),
                "_pytest_cog_version": (Tournaments.__version__, True),
            }
            for attr, args in attrs.items():
                mock.patch.object(tournament_class, attr, args[0], create=args[1])
            tournament = tournament_class(
                bot=red,
                guild=guild,
                config=config,
                name="A test tournament",
                game="Super Smash Bros. Ultimate",
                url="https://laggron.red/testtournament",
                id=random.randint(1, 99999),
                limit=128,
                status="open",
                tournament_start=datetime.now(tz=timezone.utc).replace(microsecond=0)
                + timedelta(days=7),
                bot_prefix="!",
                cog_version=Tournaments.__version__,
                data=deepcopy(cog_data),
            )
            await tournament._get_top8()
            return tournament

    return TournamentFactory()


@pytest.fixture(scope="module")
async def tournament(tournament_factory):
    yield await tournament_factory.get()


@pytest.fixture(scope="module")
def participant_factory(member_factory, tournament: "Tournament"):
    class ParticipantFactory:
        def get(self):
            member = member_factory.get()
            participant = tournament.participant_object(member, tournament)
            participant._player_id = random.randint(1, 999999999)
            return participant

    return ParticipantFactory()


@pytest.fixture()
def participant(participant_factory):
    return participant_factory.get()


@pytest.fixture(scope="module")
def match_factory(tournament: "Tournament", participant_factory):
    class MatchFactory:
        def get(self):
            return tournament.match_object(
                tournament=tournament,
                round=random.randint(-7, 8),
                set=str(len(tournament.matches) + 1),
                id=random.randint(1, 99999),
                underway=False,
                player1=participant_factory.get(),
                player2=participant_factory.get(),
            )

    return MatchFactory()


@pytest.fixture(scope="module")
async def filled_tournament_factory(request: "SubRequest", match_factory):
    class FilledTournamentFactory:
        def get(self, tournament=None):
            tournament: "Tournament" = tournament or request.getfixturevalue("tournament")
            tournament.participants.clear()
            tournament.matches.clear()
            tournament.streamers.clear()
            for i in range(64):
                match: "Match" = match_factory.get()
                tournament.participants.append(match.player1)
                tournament.participants.append(match.player2)
                tournament.matches.append(match)
            matches = [x.set for x in tournament.matches]
            assert len(matches) == len(set(matches))  # check for duplicates
            return tournament

    return FilledTournamentFactory()


def _filled_tournament(tournament: "Tournament", filled_tournament_factory):
    return filled_tournament_factory.get(tournament)


filled_tournament = pytest.fixture(scope="module")(_filled_tournament)
unique_filled_tournament = pytest.fixture()(_filled_tournament)


@pytest.fixture()
def pending_match(filled_tournament: "Tournament"):
    return random.choice(filled_tournament.matches)


@pytest.fixture(scope="module", params=[False, True])
async def launched_tournament_factory(
    request: "SubRequest",
    module_mocker: "MockerFixture",
    raise_http_error,
):
    class LaunchedTournamentFactory:
        async def get(self, tournament=None):
            tournament = tournament or request.getfixturevalue("unique_filled_tournament")
            if request.param is True:
                mock = module_mocker.patch.object(
                    tournament.guild,
                    "create_text_channel",
                )
                mock.side_effect = raise_http_error()
            for i in range(5):
                # launches are sliced by 20, so we theorically need 4 runs
                # adding one to be sure
                await tournament.launch_sets()
            return tournament

    return LaunchedTournamentFactory()


@pytest.fixture(scope="module")
async def launched_tournament(filled_tournament: "Tournament", launched_tournament_factory):
    tm = await launched_tournament_factory.get(filled_tournament)
    return copy(tm)


@pytest.fixture()
async def unique_launched_tournament(filled_tournament_factory, launched_tournament_factory):
    return await launched_tournament_factory.get(filled_tournament_factory.get())


@pytest.fixture()
def launched_match(launched_tournament: "Tournament"):
    return random.choice(launched_tournament.matches)


@pytest.fixture(params=[0, 1])
def match(
    request: "SubRequest", filled_tournament: "Tournament", launched_tournament: "Tournament"
):
    tournament = (filled_tournament, launched_tournament)[request.param]
    return random.choice(tournament.matches)


@pytest.fixture()
def streamer(launched_tournament: "Tournament", member_factory):
    streamer = Streamer(launched_tournament, member_factory.get(), "el_laggron")
    launched_tournament.streamers.append(streamer)
    yield streamer
    launched_tournament.streamers.remove(streamer)


@pytest.fixture()
async def filled_streamer(mocker: "MockerFixture", streamer: "Streamer"):
    tm = streamer.tournament
    tm_matches = tm.matches
    spy = mocker.spy(Match, "stream_queue_add")
    matches = []
    for i in range(3):
        while True:
            match = random.choice(tm_matches)
            if match not in matches:
                matches.append(match)
                break
    await streamer.add_matches(*[int(x.set) for x in matches], 257, 258)
    tm.update_streamer_list()
    assert streamer.matches == [
        *matches,
        257,
        258,
    ]
    assert spy.await_count == 3
    assert matches[0].on_hold is False
    assert matches[1].on_hold is True
    assert matches[2].on_hold is True
    for match in matches:
        assert match.streamer == streamer
    yield streamer
    for match in streamer.matches:
        if isinstance(match, int):
            continue
        await match.cancel_stream()
