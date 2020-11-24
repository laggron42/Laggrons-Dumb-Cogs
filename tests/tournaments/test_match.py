import pytest

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from tournaments.pytest.tournament import *

if TYPE_CHECKING:
    from ...tournaments.objects import Match
    from pytest_mock import MockerFixture


def test_duration(mocker: "MockerFixture", launched_match: "Match"):
    offset = timedelta(minutes=20)
    mock_datetime = mocker.patch("tournaments.objects.base.datetime")
    mock_datetime.now = lambda *args: datetime.now(*args) + offset
    _offset = offset.total_seconds()
    # margin in case of debugging
    assert _offset <= round(launched_match.duration.total_seconds()) <= _offset + 30


@pytest.mark.asyncio
async def test_saving(match: "Match"):
    tm = match.tournament
    data = match.to_dict()
    new_match = tm.match_object.from_saved_data(tm, match.player1, match.player2, data)
    assert match.__dict__ == new_match.__dict__


def test_name(mocker: "MockerFixture", match: "Match"):
    mocker.patch.object(match, "round", new_callable=mocker.PropertyMock)
    expected = {
        8: "Grand Final",
        7: "Winners Final",
        6: "Winners Semi-Final",
        5: "Winners Quarter-Final",
        4: "Winners round 4",
        -8: "Losers Final",
        -7: "Losers Semi-Final",
        -6: "Losers Quarter-Final",
        -5: "Losers round -5",
    }
    results = {}
    for round in expected:
        match.round = round
        results[round] = match._get_name()
    assert expected == results


@pytest.mark.asyncio
async def test_relaunch(launched_match: "Match"):
    await launched_match.relaunch()


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [(2, 0), (2, 1), (0, 2), (2, 3)])
@pytest.mark.parametrize("upload", [False, True])
async def test_end(mocker: "MockerFixture", launched_match: "Match", score, upload):
    mock = mocker.patch.object(launched_match, "set_scores")
    spy = mocker.spy(launched_match, "cancel")
    await launched_match.end(*score, upload=upload)
    if upload is True:
        mock.assert_awaited_once_with(*score)
    else:
        mock.assert_not_awaited()
    assert launched_match.status == "finished"
    spy.assert_called_once()


@pytest.mark.asyncio
async def test_force_end(mocker: "MockerFixture", launched_match: "Match", maybe_patch_member):
    spy_deletion = None
    if launched_match.channel:
        spy_deletion = mocker.spy(launched_match.channel, "delete")
    spies_dm = []
    for player in (launched_match.player1, launched_match.player2):
        player = maybe_patch_member(player)
        spies_dm.append(mocker.spy(player, "send"))
    await launched_match.force_end()
    for spy in spies_dm:
        spy.assert_awaited_once()
    if spy_deletion:
        spy_deletion.assert_awaited_once()
