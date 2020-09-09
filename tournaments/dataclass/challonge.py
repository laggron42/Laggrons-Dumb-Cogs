import achallonge
import discord
import logging

from typing import Optional

from redbot.core import Config

from ..utils import async_http_retry
from .base import Tournament, Match, Participant

log = logging.getLogger("red.laggron.tournaments")


class ChallongeParticipant(Participant):
    @classmethod
    def build_from_api(cls, tournament: Tournament, data: dict):
        member = tournament.guild.get_member_named(data["name"])
        if member is None:
            raise RuntimeError("Participant not found in guild.")
        cls = cls(member, tournament)
        cls._player_id = data["id"]
        return cls

    def __eq__(self, other: dict):
        if isinstance(other, dict):
            return self.player_id == other["id"]
        elif isinstance(other, self):
            return self.player_id == other.player_id
        raise NotImplementedError

    def __hash__(self):
        return self.player_id

    @property
    def player_id(self):
        return self._player_id

    async def destroy(self):
        await async_http_retry(achallonge.participants.destroy(self.tournament.id, self.player_id))
        log.debug(f"Destroyed player {self.player_id} (tournament {self.tournament.id})")


class ChallongeMatch(Match):
    @classmethod
    def build_from_api(cls, tournament: Tournament, data: dict):
        return cls(
            tournament=tournament,
            round=data["round"],
            set=str(data["suggested_play_order"]),
            id=data["id"],
            underway=bool(data["underway_at"]),
            player1=next(
                filter(lambda x: x.player_id == data["player1_id"], tournament.participants)
            ),
            player2=next(
                filter(lambda x: x.player_id == data["player2_id"], tournament.participants)
            ),
        )

    def __eq__(self, other: dict):
        if isinstance(other, dict):
            return self.id == other["id"]
        raise NotImplementedError

    def __hash__(self):
        return self.id

    async def set_scores(
        self, player1_score: int, player2_score: int, winner: Optional[Participant] = None
    ):
        score = f"{player1_score}-{player2_score}"
        if winner is None:
            if player1_score > player2_score:
                winner = self.player1
            else:
                winner = self.player2
        await async_http_retry(
            achallonge.matches.update(
                self.tournament.id, self.id, scores_csv=score, winner_id=winner.player_id
            )
        )
        log.debug(f"Set scores of match {self.id} (tournament {self.tournament.id} to {score}")

    async def mark_as_underway(self):
        await async_http_retry(achallonge.matches.mark_as_underway(self.tournament.id, self.id))
        self.status = "ongoing"
        self.underway = True
        log.debug(f"Marked match {self.id} (tournament {self.tournament.id} as underway")

    async def unmark_as_underway(self):
        await async_http_retry(achallonge.matches.unmark_as_underway(self.tournament.id, self.id))
        self.status = "pending"
        self.underway = False
        log.debug(f"Unmarked match {self.id} (tournament {self.tournament.id} as underway")


class ChallongeTournament(Tournament):
    @classmethod
    def build_from_api(
        cls, guild: discord.Guild, config: Config, prefix: str, data: dict, config_data: dict
    ):
        return cls(
            guild=guild,
            config=config,
            name=data["name"],
            game=data["game_name"].title(),
            url=data["full_challonge_url"],
            id=data["id"],
            limit=data["signup_cap"],
            status=data["state"],
            tournament_start=data["start_at"],
            bot_prefix=prefix,
            data=config_data,
        )

    participant_object = ChallongeParticipant
    match_object = ChallongeMatch
    tournament_type = "challonge"

    @classmethod
    def from_saved_data(cls, guild, config, data, config_data):
        return super().from_saved_data(guild, config, data, config_data,)

    async def start(self):
        self.phase = "ongoing"
        await async_http_retry(achallonge.tournaments.start(self.id))
        log.debug(f"Started Challonge tournament {self.id}")

    async def stop(self):
        self.phase = "finished"
        await async_http_retry(achallonge.tournaments.finalize(self.id))
        log.debug(f"Ended Challonge tournament {self.id}")

    async def add_participant(self, name: str, seed: int):
        await async_http_retry(achallonge.participants.create(self.id, name, seed=seed))
        log.debug(f"Added participant {name} (seed {seed}) to Challonge tournament {self.id}")

    async def add_participants(self, *participants: str):
        raise NotImplementedError
        # idk how bulk_add works with seeds

    async def list_participants(self):
        return await async_http_retry(achallonge.participants.index(self.id))

    async def list_matches(self):
        return await async_http_retry(achallonge.matches.index(self.id, state="open"))
