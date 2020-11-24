import pytest

from typing import TYPE_CHECKING

from tournaments.objects import Match
from tournaments.pytest.tournament import *

if TYPE_CHECKING:
    from ...tournaments.objects import Streamer
    from pytest_mock import MockerFixture


def test_saving(streamer: "Streamer", filled_streamer: "Streamer"):
    filled_streamer._update_list()
    for streamer in (streamer, filled_streamer):
        tm = streamer.tournament
        data = streamer.to_dict()
        new_streamer = Streamer.from_saved_data(tm, data)
        streamer = streamer.__dict__.copy()
        new_streamer = new_streamer.__dict__.copy()
        streamer["member"] = streamer["member"].id
        new_streamer["member"] = new_streamer["member"].id
        assert streamer == new_streamer


@pytest.mark.asyncio
async def test_remove_matches(mocker: "MockerFixture", filled_streamer: "Streamer"):
    to_remove = filled_streamer.matches[1:4]  # two Match instances, one int
    spy = mocker.spy(Match, "cancel_stream")
    await filled_streamer.remove_matches(*[int(x.set) for x in to_remove[:-1]], to_remove[-1])
    assert len(filled_streamer.matches) == 2
    assert spy.await_count == 2
    for match in to_remove[:2]:
        assert match.on_hold is False
        assert match.streamer is None
        assert match.status == "ongoing"


def test_swap_matches(filled_streamer: "Streamer"):
    set1 = filled_streamer.matches[1]
    set2 = filled_streamer.matches[3]
    target_list = filled_streamer.matches.copy()
    target_list[1], target_list[3] = target_list[3], target_list[1]
    set1 = int(set1.set) if hasattr(set1, "set") else set1
    set2 = int(set2.set) if hasattr(set2, "set") else set2
    filled_streamer.swap_match(set1, set2)
    assert filled_streamer.matches == target_list


def test_insert_matches(filled_streamer: "Streamer"):
    i1, set1 = 1, filled_streamer.matches[1]
    i2, set2 = 3, filled_streamer.matches[3]
    target_list = filled_streamer.matches.copy()
    del target_list[i1]
    target_list.insert(i2, set1)
    set1 = int(set1.set) if hasattr(set1, "set") else set1
    set2 = int(set2.set) if hasattr(set2, "set") else set2
    filled_streamer.insert_match(set1, set2=set2)
    assert filled_streamer.matches == target_list


@pytest.mark.asyncio
async def test_end_stream(mocker: "MockerFixture", filled_streamer: "Streamer"):
    spy = mocker.spy(Match, "cancel_stream")
    matches = filled_streamer.matches[:3]
    await filled_streamer.end()
    assert spy.await_count == 3
    for match in matches:
        assert match.on_hold is False
        assert match.streamer is None
        assert match.status == "ongoing"


def test_update_list(filled_streamer: "Streamer"):
    filled_streamer._update_list()
    assert filled_streamer.current_match == filled_streamer.matches[0]


@pytest.mark.asyncio
async def test_next_stream(mocker: "MockerFixture", filled_streamer: "Streamer"):
    streamer = filled_streamer
    streamer._update_list()
    first_match = streamer.matches[0]
    await first_match.end(2, 0)
    spy = mocker.spy(streamer.matches[1], "start_stream")
    streamer._update_list()
    await streamer.tournament.launch_streams()
    assert len(streamer.matches) == 4
    assert streamer.current_match == streamer.matches[0]
    spy.assert_awaited_once()
    # tests done, we revert our changes for next tests
    await first_match._start()
    for player in (first_match.player1, first_match.player2):
        player.match = first_match
        player.spoke = False
