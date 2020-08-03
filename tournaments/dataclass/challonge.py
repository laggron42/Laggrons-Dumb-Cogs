import achallonge
import discord

from typing import Optional

from ..utils import async_http_retry
from .base import Tournament, Match, Participant


class ChallongeTournament(Tournament):
    def __init__(self, guild: discord.Guild, prefix: str, data: dict, config_data: dict):
        super().__init__(
            guild=guild,
            name=data["name"],
            game=data["game"].title(),
            url=data["full_challonge_url"],
            id=data["id"],
            limit=data["signup_cap"],
            status=data["state"],
            tournament_start=data["start_at"],
            bot_prefix=prefix,
            data=config_data,
        )
        self.participant_object = ChallongeParticipant
        self.match_object = ChallongeMatch

    async def start(self):
        await async_http_retry(achallonge.tournaments.start(self.id))

    async def stop(self):
        await async_http_retry(achallonge.tournaments.finalize(self.id))

    async def add_participant(self, name: str, seed: int):
        await async_http_retry(achallonge.participants.create(self.id, name, seed=seed))

    async def add_participants(self, *participants: str):
        raise NotImplementedError
        # idk how bulk_add works with seeds

    async def list_participants(self):
        return await async_http_retry(
            achallonge.tournaments.index, self.tournaments[self.guild.id].id
        )

    async def list_matches(self):
        return await async_http_retry(
            achallonge.matches.index, self.tournaments[self.guild.id].id, state="open"
        )


class ChallongeParticipant(Participant):
    def __init__(self, member: discord.Member, player_id: int, tournament: Tournament):
        super().__init__(member, tournament)
        self._player_id = player_id

    @property
    def player_id(self):
        return self._player_id

    async def destroy(self):
        await async_http_retry(achallonge.participants.destroy(self.tournament.id, self.player_id))


class ChallongeMatch(Match):
    def __init__(self, tournament: Tournament, data: dict):
        super().__init__(
            tournament=tournament,
            round=data["round"],
            set=str(data["suggested_play_order"]),
            id=data["id"],
            underway=bool(data["underwat_at"]),
            player1=next(
                filter(lambda x: x.challonge_id == data["player1_id"], tournament.participants)
            ),
            player2=next(
                filter(lambda x: x.challonge_id == data["player2_id"], tournament.participants)
            ),
        )

    async def set_scores(
        self, player1_score: int, player2_score: int, winner: Optional[Participant]
    ):
        score = f"{player1_score}-{player2_score}"
        if winner is None:
            if player1_score > player2_score:
                winner = self.player1
            else:
                winner = self.player2
        await async_http_retry(
            achallonge.matches.update(self.tournament.id, self.id, score, winner.player_id)
        )

    async def mark_as_underway(self):
        await async_http_retry(achallonge.matches.mark_as_underway(self.tournament.id, self.id))

    async def unmark_as_underway(self):
        await async_http_retry(achallonge.matches.unmark_as_underway(self.tournament.id, self.id))
