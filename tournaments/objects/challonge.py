import achallonge
import discord
import logging

from typing import Optional

from redbot.core import Config
from redbot.core.i18n import Translator

from ..utils import async_http_retry
from .base import Tournament, Match, Participant

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)


class ChallongeParticipant(Participant):
    @classmethod
    def build_from_api(cls, tournament: Tournament, data: dict):
        member = tournament.guild.get_member_named(data["name"])
        if member is None:
            raise RuntimeError("Participant not found in guild.")
        cls = cls(member, tournament)
        cls._player_id = data["id"]
        return cls

    @property
    def player_id(self):
        return self._player_id

    async def destroy(self):
        await async_http_retry(achallonge.participants.destroy(self.tournament.id, self.player_id))
        log.debug(f"Destroyed player {self.player_id} (tournament {self.tournament.id})")

    async def send(self, content):
        # THIS IS USED FOR TESTING AND SHOULD BE REMOVED
        log.info(f"DM {str(self)}: {content}")

    @property
    def mention(self):
        # THIS IS USED FOR TESTING AND SHOULD BE REMOVED
        return str(self)


class ChallongeMatch(Match):
    @classmethod
    async def build_from_api(cls, tournament: Tournament, data: dict):
        player1 = tournament.find_participant(player_id=data["player1_id"])[1]
        player2 = tournament.find_participant(player_id=data["player2_id"])[1]
        # here we will be looking for a very special case where the match and
        # its players exists but one of the players isn't in our cache
        # I got this exact case when resetting a match with a disqualified player.
        # player is disqualified, so not loaded in our cache, but challonge somehow still
        # considers this match as open and playable, so we'll try to fix this...
        for i, player in enumerate((player1, player2)):
            if player is None:
                if i == 0:
                    i = 2
                    score = "-1-0"
                else:
                    i = 1
                    score = "0--1"
                await async_http_retry(
                    achallonge.matches.update(
                        tournament.id,
                        data["id"],
                        scores_csv=score,
                        winner_id=data[f"player{i}_id"],
                    )
                )
                log.info(
                    f"[Guild {tournament.guild.id}] Forced Challonge player with ID "
                    f"{data[f'player{i}_id']} losing match {data['suggested_play_order']} (ID: "
                    f"{data['id']}), the player is already disqualified (Challonge bug for "
                    "listing this match as open and pending)."
                )
                await tournament.to_channel.send(
                    _(
                        ":warning: A bug occured on set {set} (one player disqualified but "
                        "still listed in an open match, Challonge bug). The bot attempted "
                        "a fix by forcing a winner, but you might want to check the bracket "
                        "and make sure everything is fine."
                    ).format(set=data["suggested_play_order"])
                )
                return
        # if both players are disqualified, we set only the first one as the winner, but
        # the second one will be immediatly disqualified because of the update on bracket.
        # yes all of this mess is to blame on Challonge
        cls = cls(
            tournament=tournament,
            round=data["round"],
            set=str(data["suggested_play_order"]),
            id=data["id"],
            underway=bool(data["underway_at"]),
            player1=player1,
            player2=player2,
        )
        if data["state"] == "complete":
            cls.status = "finished"
        return cls

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
        return super().from_saved_data(guild, config, data, config_data)

    async def _get_all_rounds(self):
        return [x["round"] for x in await self.list_matches()]

    async def _update_participants_list(self):
        raw_participants = await self.list_participants()
        participants = []
        for participant in raw_participants:
            cached: Participant
            # yeah, discord.py tools works with that
            cached = discord.utils.get(self.participants, player_id=participant["id"])
            if cached is None:
                if participant["active"] is False:
                    continue  # disqualified player
                try:
                    participants.append(self.participant_object.build_from_api(self, participant))
                except RuntimeError:
                    await async_http_retry(
                        achallonge.participants.destroy(self.id, participant["id"])
                    )
                    await self.to_channel.send(
                        _(
                            ':warning: Challonge participant with name "{name}" can\'t be found '
                            "in this server. This can be due to a name change, or the "
                            "member left.\nPlayer is disqualified from this tournament."
                        ).format(name=participant["name"])
                    )
            else:
                participants.append(cached)
        self.participants = participants

    async def _update_match_list(self):
        raw_matches = await self.list_matches()
        matches = []
        remote_changes = []
        for match in raw_matches:
            cached: Match
            # yeah, discord.py tools works with that
            cached = discord.utils.get(self.matches, id=match["id"])
            if cached is None:
                if match["state"] != "open":
                    # still empty, or finished (and we don't want to load finished sets into cache)
                    continue
                match_object = await self.match_object.build_from_api(self, match)
                if match_object:
                    matches.append(match_object)
                continue
            # we check for upstream bracket changes compared to our cache
            if cached.status == "ongoing" and match["state"] == "complete":
                # score was set manually
                try:
                    winner_score, loser_score = match["scores_csv"].split("-")
                except ValueError:
                    winner_score, loser_score = 0, -1
                winner = discord.utils.get(self.participants, player_id=match["winner_id"])
                # Challonge always give the winner score first
                # need to know the actual player1/2 score, and swap if needed
                if winner == cached.player1:
                    await cached.end(winner_score, loser_score, upload=False)
                else:
                    await cached.end(loser_score, winner_score, upload=False)
                log.info(
                    f"[Guild {self.guild.id}] Ended set {cached.set} because of remote score "
                    f"update (score {match['scores_csv']} winner {str(winner)})"
                )
                remote_changes.append(cached.set)
            elif cached.status == "ongoing" and match["state"] == "pending":
                # the previously open match is now pending, this means the bracket changed
                # mostl likely due to a score change on a parent match
                await cached.force_end()
                log.info(
                    f"[Guild {self.guild.id}] Ended set {cached.set} because of bracket "
                    "changes (now marked as pending by Challonge)."
                )
                remote_changes.append(cached.set)
                continue
            elif cached.status == "finished" and match["state"] == "open":
                # the previously finished match is now open, this means a TO manually
                # removed the score set previously. we are therefore relaunching
                await cached.relaunch()
                log.info(
                    f"[Guild {self.guild.id}] Reopening set {cached.set} because of bracket "
                    "changes (now marked as open by Challonge)."
                )
                remote_changes.append(cached.set)
            # there is one last case where a finished match can be listed as pending
            # unlike the above case, we don't have to immediatly do something, the updated
            # sets will be automatically created when the time comes. we'll just leave the timer
            # do its job and delete the channel.
            matches.append(cached)
        difference = list(set(self.matches).difference(matches))
        if difference:
            log.debug(
                f"[Guild {self.guild.id}] Removing these matches from cache:\n"
                + "\n".join([repr(x) for x in difference])
            )
        self.matches = matches
        if remote_changes:
            await self.warn_bracket_change(*remote_changes)

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

    async def destroy_player(self, player_id: str):
        await async_http_retry(achallonge.participants.destroy(self.id, player_id))
        log.debug(f"Destroyed player {player_id} (tournament {self.id})")

    async def list_participants(self):
        return await async_http_retry(achallonge.participants.index(self.id))

    async def list_matches(self):
        return await async_http_retry(achallonge.matches.index(self.id))

    async def reset(self):
        await async_http_retry(achallonge.tournaments.reset(self.id))

    @staticmethod
    async def show(_id):
        result = await async_http_retry(achallonge.tournaments.show(_id))
        return {
            "name": result["name"],
            "game": result["game_name"].title(),
            "url": result["full_challonge_url"],
            "id": result["id"],
            "limit": result["signup_cap"],
            "status": result["state"],
            "tournament_start": result["start_at"],
        }
