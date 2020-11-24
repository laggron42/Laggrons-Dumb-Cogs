import pytest

from typing import TYPE_CHECKING

from tournaments.pytest.tournament import *

if TYPE_CHECKING:
    from ...tournaments import Tournaments
    from ...tournaments.objects import Tournament
    from redbot.core import commands
    from _pytest.fixtures import SubRequest


def test_events_order(tournament: "Tournament"):
    tournament._valid_dates()


@pytest.fixture()
async def pending_tm(tournament: "Tournament"):
    tournament.phase = "pending"
    return tournament


@pytest.fixture()
async def open_register_tm(tournament: "Tournament"):
    await tournament.start_registration()
    return tournament


@pytest.fixture()
async def closed_register_tm(open_register_tm: "Tournament"):
    await open_register_tm.end_registration()
    return open_register_tm


@pytest.fixture()
async def open_checkin_tm(filled_tournament: "Tournament"):
    filled_tournament.register_phase = "done"
    await filled_tournament.start_check_in()
    return filled_tournament


@pytest.fixture()
async def closed_checkin_tm(filled_tournament: "Tournament"):
    await filled_tournament.end_checkin()
    return filled_tournament


@pytest.fixture()
async def second_register_tm(closed_checkin_tm: "Tournament"):
    await closed_checkin_tm.start_registration(second=True)
    return closed_checkin_tm


@pytest.fixture()
async def second_register_closing_tm(second_register_tm: "Tournament"):
    await second_register_tm.end_registration()
    return second_register_tm


def get_any_phase_tm():
    fixtures = [
        "pending_tm",
        "open_register_tm",
        "closed_register_tm",
        "open_checkin_tm",
        "closed_checkin_tm",
        "second_register_tm",
        "second_register_closing_tm",
    ]
    for fixture in fixtures:
        fixture = pytest.lazy_fixture(fixture)
        yield fixture


@pytest.fixture(params=get_any_phase_tm())
def any_phase_tm(request: "SubRequest"):
    return request.param


@pytest.mark.asyncio
async def test_register_command(
    tournaments_cog: "Tournaments",
    any_phase_tm: "Tournament",
    ctx_factory,
    maybe_patch_member,
):
    async def test(not_registered=False):
        await tournaments_cog._in(ctx)
        try:
            if not_registered:
                assert ctx.author.id not in [x.id for x in tournament.participants]
            else:
                assert ctx.author.id in [x.id for x in tournament.participants]
        finally:
            tournament.participants.clear()

    ctx = ctx_factory.get()
    tournament = any_phase_tm
    tournament.participants.clear()
    ctx.author = maybe_patch_member(ctx.author)
    tournaments_cog.tournaments[ctx.guild.id] = tournament
    if tournament.register_channel:
        await test(True)
        ctx.channel = tournament.register_channel
    await test(
        False
        if tournament.register_phase == "ongoing"
        or (tournament.limit and len(tournament.participants) >= tournament.limit)
        else True
    )
