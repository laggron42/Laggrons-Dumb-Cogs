import discord
import logging
from random import choice

from datetime import datetime, timedelta
from typing import Optional, Mapping

from redbot.core.i18n import Translator

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)


class Tournament:
    def __init__(
        self,
        guild: discord.Guild,
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
        self.category: discord.CategoryChannel = guild.get_channel(data["channels"]["category"])
        self.announcements_channel: discord.TextChannel = guild.get_channel(
            data["channels"]["announcements"]
        )
        self.checkin_channel: discord.TextChannel = guild.get_channel(data["channels"]["checkin"])
        self.queue_channel: discord.TextChannel = guild.get_channel(data["channels"]["queue"])
        self.register_channel: discord.TextChannel = guild.get_channel(
            data["channels"]["register"]
        )
        self.scores_channel: discord.TextChannel = guild.get_channel(data["channels"]["scores"])
        self.stream_channel: discord.TextChannel = guild.get_channel(data["channels"]["stream"])
        self.to_channel: discord.TextChannel = guild.get_channel(data["channels"]["to"])
        self.participant_role: discord.Role = guild.get_role(data["roles"]["participant"])
        self.streamer_role: discord.Role = guild.get_role(data["roles"]["streamer"])
        self.to_role: discord.Role = guild.get_role(data["roles"]["to"])
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
        self.ruleset_channel = guild.get_channel(data["ruleset"])
        self.game_role = guild.get_role(data["role"])  # this is the role assigned to the game
        self.baninfo = data["baninfo"]
        self.ranking = data["ranking"]
        self.stages = data["stages"]
        self.counterpicks = data["counterpicks"]

    @classmethod
    def from_saved_data(cls, guild: discord.Guild, data: dict, config_data: dict):
        tournament_start = datetime.fromtimestamp(int(data["tournament_start"]))
        return cls(guild, **data, tournament_start=tournament_start, data=config_data,)

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
        }
        return data

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
            await send_in_dm()
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
            self.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            self.player1: discord.PermissionOverwrite(read_messages=True),
            self.player2: discord.PermissionOverwrite(read_messages=True),
        }
        for role in allowed_roles:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True)
        return await category.create_text_channel(
            self.set, overwrites=overwrites, reason=_("Lancement du set")
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
        try:
            channel = await self.create_channel(category, allowed_roles)
        except discord.HTTPException as e:
            log.error(
                f"[Guild {self.guild.id}] Couldn't create a channel for the set {self.set}.",
                exc_info=e,
            )
            await self.send_message()
        else:
            await self.send_message(channel)

    async def set_scores(
        self, player1_score: int, player2_score: int, winner: Optional[Participant]
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
