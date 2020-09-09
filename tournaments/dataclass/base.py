from __future__ import annotations

import discord
import logging
import asyncio
from random import choice

from discord.ext import tasks
from datetime import datetime, timedelta
from typing import Optional

from redbot.core import Config
from redbot.core.i18n import Translator

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)

MAX_ERRORS = 5
TIME_UNTIL_CHANNEL_DELETION = 300
TIME_UNTIL_TIMEOUT_DQ = 300


class Participant(discord.Member):
    def __init__(self, member: discord.Member, tournament: Tournament):
        # code from discord.Member._copy
        self._roles = discord.utils.SnowflakeList(member._roles, is_sorted=True)
        self.joined_at = member.joined_at
        self.premium_since = member.premium_since
        self._client_status = member._client_status.copy()
        self.guild = member.guild
        self.nick = member.nick
        self.activities = member.activities
        self._state = member._state
        # Reference will not be copied unless necessary by PRESENCE_UPDATE
        self._user = member._user
        # now our own stuff
        self.tournament = tournament
        self.match: Optional[Match] = None
        self.spoke = False  # True as soon as the participant sent a message in his channel
        # used to detect inactivity after the launch of a set
        self.unavailable = False  # if the member is not found in the guild, this is true

    @classmethod
    def from_saved_data(cls, tournament: Tournament, data: dict):
        member = tournament.guild.get_member(data["discord_id"])
        participant = cls(member, tournament)
        participant._player_id = data["player_id"]
        participant.spoke = data["spoke"]
        return participant

    def to_dict(self) -> dict:
        return {
            "discord_id": self.id,
            "player_id": self.player_id,
            "spoke": self.spoke,
        }

    def reset(self):
        self.match = None
        self.spoke = False

    def __eq__(self, other):
        raise NotImplementedError

    def __hash__(self):
        return NotImplementedError

    @property
    def player_id(self):
        raise NotImplementedError

    async def destroy(self):
        """
        Removes the participant from the tournament.
        """
        raise NotImplementedError


class Match:
    def __init__(
        self,
        tournament: Tournament,
        round: int,
        set: str,
        id: int,
        underway: bool,
        player1: Participant,
        player2: Participant,
    ):
        self.guild: discord.Guild = tournament.guild
        self.tournament = tournament
        self.round = round
        self.set = set
        self.id = id
        self.underway = underway
        self.player1 = player1
        self.player2 = player2
        self.channel: Optional[discord.TextChannel] = None
        self.start_time: Optional[datetime] = None
        self.status = "pending"  # can be "pending" "ongoing" "finished"
        self.last_message: Optional[datetime] = None
        self.checked_dq = False
        player1.match = self
        player2.match = self

    @classmethod
    def from_saved_data(cls, tournament: Tournament, player1, player2, data: dict):
        match = cls(
            tournament, data["round"], data["set"], data["id"], data["underway"], player1, player2
        )
        match.channel = tournament.guild.get_channel(data["channel"])
        if match.channel is None:
            match.status = "pending"
        else:
            match.status = data["status"]
            match.start_time = (
                datetime.fromtimestamp(data["start_time"]) if data["start_time"] else None
            )
            match.last_message = (
                datetime.fromtimestamp(data["last_message"]) if data["last_message"] else None
            )
        return match

    def to_dict(self) -> dict:
        return {
            "round": self.round,
            "set": self.set,
            "id": self.id,
            "underway": self.underway,
            "player1": self.player1.player_id,
            "player2": self.player2.player_id,
            "channel": self.channel.id if self.channel else None,
            "start_time": self.start_time.timestamp() if self.start_time else None,
            "status": self.status,
            "last_message": self.last_message.timestamp() if self.last_message else None,
        }

    def __eq__(self, other):
        raise NotImplementedError

    def __hash__(self):
        raise NotImplementedError

    async def send_message(self, channel: Optional[discord.TextChannel] = None) -> bool:
        """
        Send a message in the created channel.

        Parameters
        ----------
        channel: Optional[discord.TextChannel]
            The channel where the message needs to be send. If this is ``None``, the message will
            be sent in DM instead.

        Returns
        -------
        bool
            ``False`` if the message couldn't be sent, and was sent in DM instead.
        """
        message = _(
            ":arrow_forward: **{0.set}** : {0.player1.mention} vs {0.player2.mention}\n"
        ).format(self)
        if self.tournament.ruleset_channel:
            message += _(
                ":white_small_square: Les règles du set doivent "
                "suivre celles énoncées dans {channel}.\n"
            ).format(channel=self.tournament.ruleset_channel.mention)
        if self.tournament.stages:
            message += _(
                ":white_small_square: La liste des stages légaux à l'heure "
                "actuelle est disponible avec la commande `{prefix}stages`"
            ).format(prefix=self.tournament.bot_prefix)
        if self.tournament.counterpicks:
            message += _(
                ":white_small_square: La liste des counterpicks "
                "est disponible avec la commande `{prefix}counters`"
            ).format(prefix=self.tournament.bot_prefix)
        message += _(
            ":white_small_square: En cas de lag qui rend la partie injouable, utilisez la "
            "commande `{prefix}lag` pour appeler les T.O. et résoudre la situation.\n"
            ":white_small_square: **Dès que le set est terminé**, le gagnant envoie le "
            "score dans {score_channel} avec la commande `{prefix}win`.\n\n"
        ).format(
            prefix=self.tournament.bot_prefix, score_channel=self.tournament.scores_channel.mention
        )
        if self.tournament.baninfo:
            chosen_player = choice([self.player1, self.player2])
            message += _(
                ":game_die: **{player}** est tiré au sort pour "
                "commencer le ban des stages *({baninfo})*."
            ).format(player=chosen_player.mention, baninfo=self.tournament.baninfo)

        async def send_in_dm():
            nonlocal message
            message += _(
                "\n\n**Votre channel n'a pas pu être créé en raison d'un problème. Effectuez "
                "votre set en MP puis rapportez les résultats.**"
            )
            players = (self.player1, self.player2)
            for player in players:
                try:
                    await player.send(message)
                except discord.HTTPException as e:
                    log.warning(f"Can't send a DM to {str(player)} for his set.", exc_info=e)

        if channel is None:
            await send_in_dm()
            return False
        try:
            await channel.send(message)
        except discord.HTTPException as e:
            log.error(
                f"[Guild {self.guild.id}] Can't create a channel for the set {self.set}",
                exc_info=e,
            )
            # await send_in_dm()
            print("j'aurais du envoyer un message là mais je fais pas chier")
            return False
        else:
            return True

    async def create_channel(
        self, category: discord.CategoryChannel, *allowed_roles: list
    ) -> discord.TextChannel:
        """
        Creates a channel for the match and returns its object.

        Returns
        -------
        discord.TextChannel
            The created text channel
        """
        overwrites = {
            self.guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True
            ),
            self.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            self.player1: discord.PermissionOverwrite(read_messages=True),
            self.player2: discord.PermissionOverwrite(read_messages=True),
        }
        for role in allowed_roles:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True)
        return await self.guild.create_text_channel(
            self.set, category=category, overwrites=overwrites, reason=_("Lancement du set")
        )

    async def launch(self, category: discord.CategoryChannel, *allowed_roles: list):
        """
        Launches the set.

        This does the following:

        *   Try to create a text channel with permissions for the two players and the given roles
        *   Send a DM to both members
        *   Mark the set as ongoing

        Parameters
        ----------
        category: discord.CategoryChannel
            The category where to put the new text channel.
        allowed_roles: List[discord.Role]
            A list of roles with read_messages permission in the text channel.
        """
        stop = False
        if self.player1.unavailable is True:
            log.info(f"[Guild {self.guild.id}] DQing player 1, set {self.set}")
            await self.player1.destroy()
            stop = True
        if self.player2.unavailable is True:
            log.info(f"[Guild {self.guild.id}] DQing player 2, set {self.set}")
            await self.player2.destroy()
            stop = True
        if stop:
            self.status = "finished"
            return
        self.status = "ongoing"
        try:
            channel = await self.create_channel(category, *allowed_roles)
        except discord.HTTPException as e:
            log.error(
                f"[Guild {self.guild.id}] Couldn't create a channel for the set {self.set}.",
                exc_info=e,
            )
            await self.send_message()
        else:
            await self.send_message(channel)
            self.channel = channel
        finally:
            await self.mark_as_underway()
            self.underway = True

    async def check_inactive_and_delete(self):
        players = (self.player1, self.player2)
        if all((x.spoke is False for x in players)):
            log.debug(
                f"[Guild {self.guild.id}] Both players inactive, DQing "
                f"both and cancelling set #{self.set}."
            )
            # support for more than 2 players
            players_str = (
                ", ".join([x.mention for x in players][:-1]) + _(" et ") + players[-1].mention
            )
            await self.player1.destroy()
            await self.player2.destroy()
            await self.channel.delete()
            await self.tournament.to_channel.send(
                _(
                    ":timer: **DQ automatique de {players} pour inactivité** : "
                    "aucune manifestation à temps des joueurs, le set #{set} est annulé."
                ).format(players=players_str, set=self.set)
            )
            self.channel = None
            self.cancel()
            return
        for player in players:
            if player.spoke is False:
                log.debug(
                    f"[Guild {self.guild.id}] DQing player {player} "
                    f"for inactivity (set #{self.set})"
                )
                await player.destroy()
                await self.channel.send(
                    _(
                        ":timer: **DQ automatique de {player} pour inactivité** : "
                        "aucune manifestation à temps du joueur."
                    ).format(player=player.mention)
                )
                await self.tournament.to_channel.send(
                    _(
                        ":information_source: **DQ automatique** de {player} "
                        "pour inactivité, set #{set}."
                    ).format(player=player.mention, set=self.set)
                )
                try:
                    await player.send(
                        _(
                            "Désolé, tu as été DQ automatiquement car tu "
                            "n'as pas été actif sur ton channel de set dans "
                            "les premières minutes qui ont suivi son lancement."
                        )
                    )
                except discord.HTTPException:
                    # blocked or DMs not allowed
                    pass
                self.cancel()

    async def end(self, player1_score: int, player2_score: int):
        """
        Set the score and end the match.
        """
        await self.set_scores(player1_score, player2_score)
        winner = self.player1 if player1_score > player2_score else self.player2
        score = (
            f"{player1_score}-{player2_score}"
            if player1_score > player2_score
            else f"{player2_score}-{player1_score}"
        )
        if self.channel is not None:
            await self.channel.send(
                _(
                    ":bell: __Score rapporté__ : **{winner}** gagne **{score}** !\n"
                    "*En cas d'erreur, appelez un TO ! Un mauvais score intentionnel "
                    "est passable de DQ et ban du tournoi.*\n"
                    "*Note : ce channel sera automatiquement supprimé 5 "
                    "minutes à partir de la dernière activité.*"
                ).format(winner=winner.mention, score=score)
            )
        self.cancel()

    def cancel(self):
        self.player1.reset()
        self.player2.reset()
        self.status = "finished"
        if self.channel is not None:
            loop = asyncio.get_event_loop()
            self.deletion_task = loop.create_task(self._end_deletion_task())

    async def set_scores(
        self, player1_score: int, player2_score: int, winner: Optional[Participant] = None
    ):
        """
        Set the score for the set.

        Parameters
        ----------
        player1_score: int
            The score of the first player.
        player2_score: int
            The score of the second player.
        winner: Optional[Participant]
            The winner of the set. If not provided, the player with the highest score will be
            selected.
        """
        raise NotImplementedError

    async def mark_as_underway(self):
        """
        Marks the match as underway.
        """
        raise NotImplementedError

    async def unmark_as_underway(self):
        """
        Unmarks the match as underway.

        This shouldn't ever be needed, just here in case of.
        """
        raise NotImplementedError


class Tournament:
    def __init__(
        self,
        guild: discord.Guild,
        config: Config,
        name: str,
        game: str,
        url: str,
        id: str,
        limit: Optional[int],
        status: str,
        tournament_start: datetime,
        bot_prefix: str,
        data: dict,
    ):
        self.guild = guild
        self.data = config
        self.name = name
        self.game = game
        self.url = url
        self.id = id
        self.limit = limit
        self.status = status
        self.tournament_start = tournament_start
        self.bot_prefix = bot_prefix
        self.participants = []
        self.matches = []
        self.winner_categories = []
        self.loser_categories = []
        self.category: discord.CategoryChannel = guild.get_channel(
            data["channels"].get("category")
        )
        self.announcements_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("announcements")
        )
        self.checkin_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("checkin")
        )
        self.queue_channel: discord.TextChannel = guild.get_channel(data["channels"].get("queue"))
        self.register_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("register")
        )
        self.scores_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("scores")
        )
        self.stream_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("stream")
        )
        self.to_channel: discord.TextChannel = guild.get_channel(data["channels"].get("to"))
        self.participant_role: discord.Role = guild.get_role(data["roles"].get("participant"))
        self.streamer_role: discord.Role = guild.get_role(data["roles"].get("streamer"))
        self.to_role: discord.Role = guild.get_role(data["roles"].get("to"))
        self.delay: int = data["delay"]
        self.register: dict = data["register"]
        self.checkin: dict = data["checkin"]
        self.start_bo5: int = data["start_bo5"]
        if data["register"]["opening"] != 0:
            self.register_start: datetime = tournament_start - timedelta(
                hours=data["register"]["opening"]
            )
        else:
            self.register_start = None
        if data["register"]["closing"] != 0:
            self.register_stop: datetime = tournament_start - timedelta(
                minutes=data["register"]["closing"]
            )
        else:
            self.register_stop = None
        if data["checkin"]["opening"] != 0:
            self.checkin_start: datetime = tournament_start - timedelta(
                minutes=data["checkin"]["opening"]
            )
        else:
            self.checkin_start = None
        if data["checkin"]["closing"] != 0:
            self.checkin_stop: datetime = tournament_start - timedelta(
                minutes=data["checkin"]["closing"]
            )
        else:
            self.checkin_stop = None
        self.ruleset_channel: discord.TextChannel = guild.get_channel(data["ruleset"])
        self.game_role = guild.get_role(data["role"])  # this is the role assigned to the game
        self.baninfo: str = data["baninfo"]
        self.ranking: dict = data["ranking"]
        self.stages: list = data["stages"]
        self.counterpicks: list = data["counterpicks"]
        self.phase = "pending"  # can be "pending" "register" "checkout" "ongoing" "finished"
        # loop task things
        self.task: Optional[asyncio.Task] = None
        self.task_errors = 0

    participant_object = Participant
    match_object = Match
    tournament_type = "base"  # should be "challonge", or "smash.gg"...

    @classmethod
    def from_saved_data(
        cls, guild: discord.Guild, config: Config, data: dict, config_data: dict,
    ):
        tournament_start = datetime.fromtimestamp(int(data["tournament_start"]))
        participants = data["participants"]
        matches = data["matches"]
        winner_categories = data["winner_categories"]
        loser_categories = data["loser_categories"]
        phase = data["phase"]
        del data["tournament_start"], data["participants"], data["matches"]
        del data["winner_categories"], data["loser_categories"], data["phase"]
        del data["tournament_type"]
        tournament = cls(
            guild, config, **data, tournament_start=tournament_start, data=config_data
        )
        if type:
            tournament.type = type
        tournament.participants = [
            tournament.participant_object.from_saved_data(tournament, data)
            for data in participants
        ]
        for data in matches:
            player1 = tournament.find_participant(player_id=data["player1"])
            player2 = tournament.find_participant(player_id=data["player2"])
            tournament.matches.append(
                tournament.match_object.from_saved_data(tournament, player1, player2, data)
            )
        tournament.winner_categories = list(
            filter(None, [guild.get_channel(x) for x in winner_categories])
        )
        tournament.loser_categories = list(
            filter(None, [guild.get_channel(x) for x in loser_categories])
        )
        tournament.phase = phase
        return tournament

    def to_dict(self) -> dict:
        """Returns a dict ready for Config."""
        data = {
            "name": self.name,
            "game": self.game,
            "url": self.url,
            "id": self.id,
            "limit": self.limit,
            "status": self.status,
            "tournament_start": int(self.tournament_start.timestamp()),
            "bot_prefix": self.bot_prefix,
            "participants": [x.to_dict() for x in self.participants],
            "matches": [x.to_dict() for x in self.matches],
            "winner_categories": [x.id for x in self.winner_categories],
            "loser_categories": [x.id for x in self.loser_categories],
            "phase": self.phase,
            "tournament_type": self.tournament_type,
        }
        return data

    async def save(self):
        data = self.to_dict()
        await self.data.guild(self.guild).tournament.set(data)

    async def _update_participants_list(self):
        raw_participants = await self.list_participants()
        for participant in raw_participants:
            if participant not in self.participants:
                self.participants.append(self.participant_object.build_from_api(self, participant))

    async def _update_match_list(self):
        raw_matches = await self.list_matches()
        for match in raw_matches:
            if match not in self.matches:
                self.matches.append(self.match_object.build_from_api(self, match))

    def find_participant(
        self, *, player_id: Optional[str] = None, discord_id: Optional[int] = None
    ):
        if player_id:
            try:
                return next(filter(lambda x: x.player_id == player_id, self.participants))
            except StopIteration:
                return None
        elif discord_id:
            try:
                return next(filter(lambda x: x.id == discord_id, self.participants))
            except StopIteration:
                return None
        raise RuntimeError("Provide either player_id or discord_id")

    def find_match(self, match_id: str):
        try:
            return next(filter(lambda x: x.id == match_id, self.matches))
        except StopIteration:
            return None

    async def send_start_messages(self):
        messages = {
            self.announcements_channel: _(
                "Le tournoi **{tournament}** est officiellement lancé ! Bracket : {bracket}\n"
                ":white_small_square: Vous pouvez y accéder "
                "à tout moment avec la commande `{prefix}bracket`.\n"
                ":white_small_square: Vous pouvez consulter les liens de "
                "stream avec la commande `{prefix}stream`.\n\n"
                "{participant} On arrête le freeplay ! Le tournoi est sur le "
                "point de commencer. Veuillez lire les consignes :\n"
                ":white_small_square: Vos sets sont annoncés dès que disponibles dans "
                "{queue_channel} : **ne lancez rien sans consulter ce channel**.\n"
                ":white_small_square: Le ruleset ainsi que les informations pour le "
                "bannissement des stages sont dispo dans {rules_channel}.\n"
                ":white_small_square: Le gagnant d'un set doit rapporter le score **dès "
                "que possible** dans {scores_channel} avec la commande `{prefix}win`.\n"
                ":white_small_square: Vous pouvez DQ du tournoi avec la commande "
                "`{prefix}dq`, ou juste abandonner votre set en cours avec `{prefix}ff`.\n"
                ":white_small_square: En cas de lag qui rend votre set injouable, utilisez "
                "la commande `{prefix}lag` pour appeler les T.O.\n"
                ":timer: Vous serez **DQ automatiquement** si vous n'avez pas été actif "
                "sur votre channel __dans les {delay} minutes qui suivent sa création__."
            ).format(
                tournament=self.name,
                bracket=self.url,
                participant=self.participant_role.mention,
                queue_channel=self.queue_channel.mention,
                rules_channel=self.ruleset_channel.mention,
                scores_channel=self.scores_channel.mention,
                delay=self.delay,
                prefix=self.bot_prefix,
            ),
            self.scores_channel: _(
                ":information_source: La prise en charge des scores "
                "pour le tournoi **{tournament}** est automatisée :\n"
                ":white_small_square: Seul **le gagnant du set** envoie "
                "le score de son set, précédé par la **commande** `{prefix}win`.\n"
                ":white_small_square: Le message du score doit contenir le "
                "**format suivant** : `{prefix}win 2-0, 3-2, 3-1, ...`.\n"
                ":white_small_square: Un mauvais score intentionnel, perturbant le "
                "déroulement du tournoi, est **passable de DQ et ban**.\n"
                ":white_small_square: Consultez le bracket afin de "
                "**vérifier** les informations : {url}\n"
                ":white_small_square: En cas de mauvais score : "
                "contactez un TO pour une correction manuelle.\n\n"
                ":satellite_orbital: Chaque score étant **transmis un par "
                "un**, il est probable que la communication prenne jusqu'à 30 secondes."
            ).format(tournament=self.name, url=self.url, prefix=self.bot_prefix),
            self.queue_channel: _(
                ":information_source: **Le lancement des sets est automatisé.** "
                "Veuillez suivre les consignes de ce channel, que ce soit par le bot ou les TOs.\n"
                ":white_small_square: Tout passage on stream sera notifié à "
                "l'avance, ici, dans votre channel (ou par DM).\n"
                ":white_small_square: Tout set devant se jouer en BO5 "
                "est indiqué ici, et également dans votre channel.\n"
                ":white_small_square: La personne qui commence les bans "
                "est indiquée dans votre channel (en cas de besoin : `{prefix}flip`).\n\n"
                ":timer: Vous serez **DQ automatiquement** si vous n'avez pas été actif "
                "sur votre channel __dans les {delay} minutes qui suivent sa création__."
            ).format(delay=self.delay, prefix=self.bot_prefix),
        }
        for channel, message in messages.items():
            try:
                await channel.send(message)
            except discord.HTTPException as e:
                log.error(f"[Guild {self.guild.id}] Can't send message in {channel}.", exc_info=e)

    async def launch_sets(self):
        async def _get_available_category(dest: str, position: int):
            if dest == "winner":
                categories = self.winner_categories
            else:
                categories = self.loser_categories
            try:
                return next(filter(lambda x: len(x.channels) < 50, categories))
            except StopIteration:
                if categories:
                    position = categories[-1].position + 1
                else:
                    position += 1
                if dest == "winner":
                    name = "Winner bracket"
                else:
                    name = "Loser bracket"
                channel = await self.guild.create_category(
                    name, reason=_("Nouvelle catégorie de sets.")
                )
                categories.append(channel)
                return channel

        position = self.category.position + 1 if self.category else len(self.guild.categories)
        allowed_roles = []
        if self.to_role is not None:
            allowed_roles.append(self.to_role)
        if self.streamer_role is not None:
            allowed_roles.append(self.streamer_role)
        coros = []
        await self._update_participants_list()
        await self._update_match_list()
        for match in filter(lambda x: x.status == "pending", self.matches):
            match: Match
            if match.round > 0:
                category = await _get_available_category("winner", position)
            else:
                category = await _get_available_category("winner", position)
            coros.append(match.launch(category, *allowed_roles))
        results = await asyncio.gather(*coros, return_exceptions=True)
        for result in filter(None, results):
            log.error(f"[Guild {self.guild.id}] Can't launch a set.", exc_info=result)

    @tasks.loop(seconds=15)
    async def loop_task(self):
        coros = [self.launch_sets()]
        results = await asyncio.gather(*coros, return_exceptions=True)
        for i, result in enumerate(results):
            if result is None:
                continue
            log.warning(f"[Guild {self.guild.id}] Failed with coro {coros[i]}.", exc_info=result)
        # saving is done after all of our jobs, so the data shouldn't move too much
        await self.save()

    @loop_task.error
    async def on_loop_task_error(self, exception):
        self.task_errors += 1
        if self.task_errors >= MAX_ERRORS:
            log.critical(
                f"[Guild {self.guild.id}] Error in loop task. 3rd error, cancelling the task",
                exc_info=exception,
            )
        else:
            log.error(
                f"[Guild {self.guild.id}] Error in loop task. Resuming...", exc_info=exception
            )
            self.task = self.loop_task.start()

    def start_loop_task(self):
        self.task = self.loop_task.start()

    def stop_loop_task(self):
        self.loop_task.cancel()

    async def start(self):
        """
        Starts the tournament.

        Raises
        ------
        RuntimeError
            The tournament is already started.
        """
        raise NotImplementedError

    async def stop(self):
        """
        Stops the tournament.

        Raises
        ------
        RuntimeError
            The tournament is already stopped or not started.
        """
        raise NotImplementedError

    async def add_participant(self, name: str, seed: Optional[int] = None):
        """
        Adds a participant to the tournament.

        Parameters
        ----------
        name: str
            The name of the participant
        seed: int
            The participant's new seed. Must be between 1 and the current number of participants
            (including the new record). Omit to place at the bottom.
        """
        raise NotImplementedError

    async def add_participants(self, *participants: str):
        """
        Adds a list of participants to the tournament, ordered as you want them to be seeded.

        Parameters
        ----------
        participants: List[str]
            The list of participants. The first element will be seeded 1.
        """
        raise NotImplementedError

    async def list_participants(self):
        """
        Returns the list of participants from the tournament host.

        Returns
        -------
        List[str]
            The list of participants.
        """
        raise NotImplementedError

    async def list_matches(self):
        """
        Returns the list of matches from the tournament host.

        Returns
        -------
        List[str]
            The list of matches.
        """
        raise NotImplementedError
