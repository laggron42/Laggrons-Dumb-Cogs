import pytest

from copy import deepcopy
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from tournaments.pytest.tournament import *

if TYPE_CHECKING:
    from ...tournaments.objects import Tournament
    from redbot.core import Config
    from pytest_mock import MockerFixture


def test_base(tournament: "Tournament"):
    assert len(tournament.matches) == 0


@pytest.mark.asyncio
async def test_saving(
    config: "Config",
    tournament: "Tournament",
    filled_tournament: "Tournament",
    launched_tournament: "Tournament",
):
    for i, tm in enumerate((tournament, filled_tournament, launched_tournament)):
        if tm.matches:
            tm.phase = "ongoing"
        data = tm.to_dict()
        new_tm = await tm.from_saved_data(
            bot=tournament._pytest_red,
            guild=tm.guild,
            config=config,
            cog_version=tm._pytest_cog_version,
            data=data,
            config_data=deepcopy(tm._pytest_cog_data),
        )
        for category_list in (new_tm.winner_categories, new_tm.loser_categories):
            for i, category in enumerate(category_list):
                category_list[i] = new_tm.guild.get_category(category.id)
        for t in (tm, new_tm):
            # remove things that are not saved/recovered and will probably differ
            t.lock = None
            t.matches_to_announce = []
        initial_dict = tm.__dict__.copy()
        new_dict = new_tm.__dict__.copy()
        initial_dict.pop("loop_task", None)
        participants = zip(initial_dict.pop("participants"), new_dict.pop("participants"))
        matches = zip(initial_dict.pop("matches"), new_dict.pop("matches"))
        assert initial_dict == new_dict
        for participant, new_participant in participants:
            participant = participant.__dict__.copy()
            new_participant = new_participant.__dict__.copy()
            for p in (participant, new_participant):
                # here we edit objects because they have a different internal ID, but we still
                # check if they're actually the same by simply using their Challonge ID
                p["match"] = p["match"].id
                p["tournament"] = p["tournament"].id
            assert participant == new_participant
        for match, new_match in matches:
            match = match.__dict__.copy()
            new_match = new_match.__dict__.copy()
            for m in (match, new_match):
                # same here
                m["player1"] = m["player1"].player_id
                m["player2"] = m["player2"].player_id
                m["tournament"] = m["tournament"].id
            assert match == new_match


@pytest.mark.asyncio
async def test_filled(filled_tournament: "Tournament"):
    assert len(filled_tournament.participants) == 128
    assert len(filled_tournament.matches) == 64


@pytest.mark.asyncio
async def test_launch_matches(launched_tournament: "Tournament"):
    assert all(x.status == "ongoing" for x in launched_tournament.matches)


@pytest.mark.asyncio
async def test_channel_timeout(mocker: "MockerFixture", unique_launched_tournament):
    tournament = unique_launched_tournament
    if tournament.matches[0].channel is None:
        return  # ignore the case where channels are missing
    for participant in tournament.participants[::3]:
        participant.spoke = True  # mark 2/3 as AFK to test both solo and double DQ
    afk_players = len([x for x in tournament.participants if not x.spoke])
    not_afk_matches = len([x for x in tournament.matches if x.player1.spoke and x.player2.spoke])
    mock_datetime = mocker.patch("tournaments.objects.base.datetime")
    mock_datetime.now = lambda *args: datetime.now(*args) + timedelta(minutes=20)
    spy_check = mocker.spy(tournament.match_object, "check_inactive")
    spy_dq = mocker.spy(tournament.participant_object, "destroy")
    await tournament.check_for_channel_timeout()
    if tournament.delay > 0:
        assert spy_check.await_count == 64
        assert spy_dq.await_count == afk_players
        assert len([x for x in tournament.matches if x.status == "ongoing"]) == not_afk_matches
    else:
        assert spy_check.await_count == 0
        assert all(x.status == "ongoing" for x in tournament.matches)


@pytest.mark.asyncio
async def test_match_length_warn(unique_launched_tournament):
    tournament = unique_launched_tournament
    if tournament.matches[0].channel is None:
        return
    if not tournament.time_until_warn["bo3"][0]:
        return
    for participant in tournament.participants:
        participant.spoke = True
    for match in tournament.matches:
        match.start_time -= timedelta(minutes=40)
    await tournament.check_for_too_long_matches()
    assert all(isinstance(x.warned, datetime) for x in tournament.matches)
    for match in tournament.matches:
        match.warned -= timedelta(minutes=15)
    await tournament.check_for_too_long_matches()
    assert all(x.warned is True for x in tournament.matches)
