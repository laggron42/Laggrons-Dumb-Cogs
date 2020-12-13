import achallonge
import discord
import logging

from copy import copy
from typing import List, Optional

from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.i18n import Translator

from ..utils import async_http_retry
from .base import Tournament, Match, Participant

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)


class ChallongeParticipant(Participant):
    @classmethod
    def build_from_api(cls, tournament: Tournament, data: dict):
        """
        Builds a new member from Challonge raw data.

        Parameters
        ----------
        tournament: Tournament
            The current tournament
        data: dict
            Data as provided by the API.
        """
        member = tournament.guild.get_member_named(data["name"])
        if member is None:
            raise RuntimeError("Participant not found in guild.")
        cls = cls(member, tournament)
        cls._player_id = data["id"]
        return cls

    @property
    def player_id(self):
        """
        Challonge player ID.
        """
        return self._player_id

    async def destroy(self):
        """
        If the tournament has started, disqualifies a player on the bracket, else he's removed
        from the list of participants.
        """
        await self.tournament.destroy_player(self.player_id)


class ChallongeMatch(Match):
    @classmethod
    async def build_from_api(cls, tournament: Tournament, data: dict):
        """
        Builds a new member from Challonge raw data.

        This will also disqualify participants from the match not found in the server.

        Parameters
        ----------
        tournament: Tournament
            The current tournament
        data: dict
            Data as provided by the API.
        """
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
                await tournament.request(
                    achallonge.matches.update,
                    tournament.id,
                    data["id"],
                    scores_csv=score,
                    winner_id=data[f"player{i}_id"],
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
        await self.tournament.request(
            achallonge.matches.update,
            self.tournament.id,
            self.id,
            scores_csv=score,
            winner_id=winner.player_id,
        )
        log.debug(f"Set scores of match {self.id} (tournament {self.tournament.id} to {score}")

    async def mark_as_underway(self):
        await self.tournament.request(
            achallonge.matches.mark_as_underway, self.tournament.id, self.id
        )
        self.status = "ongoing"
        self.underway = True
        log.debug(f"Marked match {self.id} (tournament {self.tournament.id} as underway")

    async def unmark_as_underway(self):
        await self.tournament.request(
            achallonge.matches.unmark_as_underway, self.tournament.id, self.id
        )
        self.status = "pending"
        self.underway = False
        log.debug(f"Unmarked match {self.id} (tournament {self.tournament.id} as underway")


class ChallongeTournament(Tournament):
    @classmethod
    def build_from_api(
        cls,
        bot: Red,
        guild: discord.Guild,
        config: Config,
        prefix: str,
        cog_version: str,
        data: dict,
        config_data: dict,
    ):
        """
        Builds a new Tournament from Challonge raw data.

        Parameters
        ----------
        bot: redbot.core.bot.Red
            The bot object
        guild: discord.Guild
            The current guild for the tournament
        config: redbot.core.Config
            The cog's Config object
        prefix: str
            A prefix to use for displaying commands without context.
        cog_version: str
            Current version of Tournaments
        data: dict
            Data as provided by the API.
        config_data: dict
            A dict with all the config required for the tournament (combines guild and
            game settings)
        """
        return cls(
            bot=bot,
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
            cog_version=cog_version,
            data=config_data,
        )

    participant_object = ChallongeParticipant
    match_object = ChallongeMatch
    tournament_type = "challonge"

    @classmethod
    def from_saved_data(cls, bot, guild, config, cog_version, data, config_data):
        return super().from_saved_data(bot, guild, config, cog_version, data, config_data)

    async def request(self, method, *args, **kwargs):
        """
        An util adding the credentials to the args before sending an API call.

        Also wraps the request in a retry loop (max 3 then raise).
        """
        kwargs.update(credentials=self.credentials)
        return await async_http_retry(method(*args, **kwargs))

    async def _get_all_rounds(self):
        return [x["round"] for x in await self.list_matches()]

    async def _update_participants_list(self):
        raw_participants = await self.list_participants()
        participants = []
        removed = []
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
                    await self.request(achallonge.participants.destroy, self.id, participant["id"])
                    removed.append(participant["name"])
            else:
                participants.append(cached)
        if removed:
            if len(removed) == 1:
                await self.to_channel.send(
                    _(
                        ':warning: Challonge participant with name "{name}" can\'t be found '
                        "in this server. This can be due to a name change, or the "
                        "member left.\nPlayer is disqualified from this tournament."
                    ).format(name=removed[0])
                )
            else:
                startup = None
                if not self.participants:
                    # list is empty, assuming the tournament just started (or mass refresh)
                    startup = _(
                        "\nSince this occured when starting the tournament, there may "
                        "have been an error when uploading participants, or you skipped "
                        "registration, relied on the existing participants in the bracket, and "
                        "the names doesn't match the members' names in this server.\n"
                        "If this is the case, you may want to roll back the tournament's start "
                        "with the `{prefix}resetbracket` command, and retry.\n"
                    ).format(prefix=self.bot_prefix)
                await self.to_channel.send(
                    _(
                        ":warning: Multiple Challonge participants can't be found "
                        "in this server. This can be due to name changes, or the members left.\n"
                        "{startup}\n"
                        "The following players are disqualified from this tournament:\n{names}"
                    ).format(
                        prefix=self.bot_prefix,
                        startup=startup,
                        names=", ".join(removed),
                    )
                )
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
                if match["state"] != "open" or match["winner_id"]:
                    # still empty, or finished (and we don't want to load finished sets into cache)
                    continue
                if match["suggested_play_order"] is None:
                    # the last set, corresponding to a bracket reset (LB winner won in grand final)
                    # somehow returns null for its number, so we assign it ourselves
                    match["suggested_play_order"] = len(raw_matches)
                match_object = await self.match_object.build_from_api(self, match)
                if match_object:
                    matches.append(match_object)
                continue
            # we check for upstream bracket changes compared to our cache
            if cached.status == "ongoing" and match["state"] == "complete":
                # score was set manually
                try:
                    winner_score, loser_score = match["scores_csv"].split("-")
                    winner_score = int(winner_score)
                    loser_score = int(loser_score)
                except ValueError:
                    winner_score, loser_score = 0, -1
                else:
                    if winner_score < loser_score:
                        winner_score, loser_score = loser_score, winner_score
                winner = discord.utils.get(self.participants, player_id=match["winner_id"])
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
        await self.request(achallonge.tournaments.start, self.id)
        self.phase = "ongoing"
        log.debug(f"Started Challonge tournament {self.id}")

    async def stop(self):
        await self.request(achallonge.tournaments.finalize, self.id)
        self.phase = "finished"
        log.debug(f"Ended Challonge tournament {self.id}")

    async def add_participant(self, participant: ChallongeParticipant, seed: int = None):
        kwargs = {"seed": seed} if seed is not None else {}
        data = await self.request(
            achallonge.participants.create, self.id, str(participant), **kwargs
        )
        participant._player_id = data["id"]
        log.debug(
            f"Added participant {participant} (seed {seed}) to Challonge tournament {self.id}"
        )

    async def add_participants(
        self, participants: Optional[List[ChallongeParticipant]] = None, force: bool = False
    ):
        participants = copy(participants or self.participants)
        if not participants:
            raise RuntimeError("No participant provided")
        if force is True:
            # remove previous participants
            await self.request(achallonge.participants.clear, self.id)
        else:
            # only upload what's missing
            raw_participants = await self.list_participants()
            if raw_participants:
                raw_ids = [x.get("id") for x in raw_participants]
                participants = [x for x in participants if x.player_id not in raw_ids]
            if not participants:
                return
                # raise RuntimeError("No new participant to add")
        participants = [str(x) for x in participants]
        size = len(participants)
        # make a composite list (to avoid "414 Request-URI Too Large")
        participants = [participants[x : x + (50)] for x in range(0, size, 50)]
        # Send to Challonge and assign IDs
        for chunk_participants in participants:
            challonge_players = await self.request(
                achallonge.participants.bulk_add, self.id, chunk_participants
            )
            for player in challonge_players:
                participant = self.find_participant(discord_name=player["name"])[1]
                if participant is None:
                    log.warning(
                        f"[Guild {self.guild.id}] Challonge player with name {player['name']} "
                        f"and ID {player['id']} cannot be found in participants after bulk_add. "
                        "If you start the tournament now, expect DQs."
                    )
                    continue
                participant._player_id = player["id"]
        return size

    async def destroy_player(self, player_id: str):
        await self.request(achallonge.participants.destroy, self.id, player_id)
        log.debug(f"Destroyed player {player_id} (tournament {self.id})")

    async def list_participants(self):
        return await self.request(achallonge.participants.index, self.id)

    async def list_matches(self):
        return await self.request(achallonge.matches.index, self.id)

    async def reset(self):
        await self.request(achallonge.tournaments.reset, self.id)

    async def show(self, _id):
        result = await self.request(achallonge.tournaments.show, _id)
        return {
            "name": result["name"],
            "game": result["game_name"].title(),
            "url": result["full_challonge_url"],
            "id": result["id"],
            "limit": result["signup_cap"],
            "status": result["state"],
            "tournament_start": result["start_at"],
        }
