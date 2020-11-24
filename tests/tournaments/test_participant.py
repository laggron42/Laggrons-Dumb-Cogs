import pytest
import random
import discord

from typing import TYPE_CHECKING

from tournaments.pytest.tournament import *

if TYPE_CHECKING:
    from ...tournaments.objects import Participant, Match, Tournament
    from pytest_mock import MockerFixture


@pytest.mark.asyncio
async def test_saving(participant: "Participant"):
    tm = participant.tournament
    data = participant.to_dict()
    new_participant = tm.participant_object.from_saved_data(tm, data)
    assert participant.__dict__ == new_participant.__dict__


@pytest.mark.asyncio
@pytest.mark.parametrize("player", [1, 2])
async def test_forfeit(mocker: "MockerFixture", player, match: "Match"):
    if player == 1:
        loser = match.player1
        winner = match.player2
    else:
        loser = match.player2
        winner = match.player1
    spy_set_score = mocker.spy(match, "set_scores")
    spy_message = mocker.spy(*((match.channel, "send") if match.channel else (winner, "send")))
    await match.forfeit(loser)
    spy_set_score.assert_awaited_once_with(*((-1, 0) if player == 1 else (0, -1)))
    spy_message.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("has_match", [True, False])
async def test_disqualify(
    mocker: "MockerFixture", participant: "Participant", match: "Match", has_match: bool
):
    if has_match:
        participant, winner = [match.player1, match.player2][:: random.choice((1, -1))]
    await participant.destroy()
    if has_match is False:
        return
    spy_message = mocker.spy(*((match.channel, "send") if match.channel else (winner, "send")))
    await match.disqualify(participant)
    spy_message.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("dm", ([False, True]))
async def test_register(
    tournament: "Tournament",
    member: discord.Member,
    dm: bool,
    maybe_patch_member,
):
    member = maybe_patch_member(member)
    await tournament.register_participant(member, send_dm=dm)


@pytest.mark.asyncio
@pytest.mark.parametrize("dm", ([False, True]))
async def test_unregister(
    filled_tournament: "Tournament",
    dm: bool,
    maybe_patch_member,
):
    member = random.choice(filled_tournament.participants)
    member = maybe_patch_member(member)
    await filled_tournament.unregister_participant(member, send_dm=dm)


@pytest.mark.asyncio
@pytest.mark.parametrize("dm", ([False, True]))
async def test_check(
    filled_tournament: "Tournament",
    dm: bool,
    maybe_patch_member,
):
    participant = random.choice(filled_tournament.participants)
    participant = maybe_patch_member(participant)
    await participant.check(send_dm=dm)
