import discord
import logging
import re
import asyncio
import achallonge

from datetime import datetime
from typing import Optional

from redbot.core import commands
from redbot.core import checks
from redbot.core import Config
from redbot.core.i18n import Translator
from redbot.core.utils import menus
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate
from redbot.core.utils.chat_formatting import pagify

from .abc import MixinMeta
from .dataclass import ChallongeTournament
from .utils import credentials_check, async_http_retry

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)

CHALLONGE_URL_RE = re.compile(r"(?:https?://challonge\.com/)(?P<id>\S+)")


class ChallongeURLConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        result = CHALLONGE_URL_RE.match(argument)
        link_id = result.group("id")
        if not link_id:
            raise commands.BadArgument(_("URL Challonge invalide."))
        return link_id


class GameSetting(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        config = Config.get_conf(None, identifier=260, cog_name="Tournaments")
        games = await config.custom("GAME", ctx.guild.id).all()
        if argument not in games:
            raise commands.BadArgument(
                _(
                    "Ce jeu n'existe pas. Vérifiez le nom, et utilisez des "
                    "guillmets s'il y a des espaces."
                )
            )
        return argument


class Settings(MixinMeta):
    async def _verify_settings(self, ctx: commands.Context) -> str:
        """
        Check if all settings are correctly filled and the roles/channels still exist.
        """
        guild = ctx.guild
        not_set = {"channels": [], "roles": []}
        lost = {"channels": [], "roles": []}
        required_channels = ["announcements", "queue", "to"]
        required_roles = ["participant"]
        data = await self.data.guild(guild).all()
        for name, channel_id in data["channels"].items():
            if name not in required_channels:
                continue
            if channel_id is None:
                not_set["channels"].append(name)
                continue
            channel = guild.get_channel(channel_id)
            if channel is None:
                lost["channels"].append(name)
        for name, role_id in data["roles"].items():
            if name not in required_roles:
                continue
            if role_id is None:
                not_set["roles"].append(name)
                continue
            role = guild.get_role(role_id)
            if role is None:
                lost["roles"].append(name)
        if all([not x for x in not_set.values()]) and all([not x for x in lost.values()]):
            return
        text = ""
        if not_set["channels"]:
            text += (
                _("Les channels suivants ne sont pas configurés:\n")
                + "".join([f"- {x}\n" for x in not_set["channels"]])
                + "\n"
            )
        if not_set["roles"]:
            text += (
                _("Les roles suivants ne sont pas configurés:\n")
                + "".join([f"- {x}\n" for x in not_set["roles"]])
                + "\n"
            )
        if lost["channels"]:
            text += (
                _("Les channels suivants ont été perdus:\n")
                + "".join([f"- {x}\n" for x in not_set["channels"]])
                + "\n"
            )
        if lost["roles"]:
            text += (
                _("Les roles suivants ont été perdus:\n")
                + "".join([f"- {x}\n" for x in not_set["roles"]])
                + "\n"
            )
        text += _(
            "Merci de configurer les paramètres manquants avec les commandes "
            "`{prefix}tournamentset channels` et `{prefix}tournamentset roles`."
        ).format(prefix=ctx.clean_prefix)
        return text

    @commands.group()
    @checks.admin_or_permissions(administrator=True)
    async def challongeset(self, ctx: commands.Context):
        """
        Règle les informations Challonge pour ce serveur.

        Vous allez devoir utiliser le même compte Challonge que celui qui crée les tournois.

        Vous avez besoin d'un nom d'utilisateur et d'une clé API, obtenable dans les paramètres \
de votre compte (Developer API).
        https://challonge.com/settings/developer

        Utilisez `[p]challongeset username` et `[p]challongeset api`.

        :warning: **Attention, votre clé d'API est secrète ! Soyez sûr de ne pas envoyer cette \
clé à n'importe qui.** La commande `[p]challongeset api` vous demandera votre clé en MP, pas \
besoin de la fournir directement.
        """
        pass

    @challongeset.command(name="api")
    async def challongeset_api(self, ctx: commands.Context, api_key: Optional[str]):
        """
        Réglage de la clé API Challonge.

        Vous pouvez l'obtenir dans les paramètres de votre compte challonge, catégorie "Developer\
API".
        **https://challonge.com/settings/developer**

        :warning: **Attention, cette clé est secrète !**
        """
        guild = ctx.guild
        if api_key is not None:
            if ctx.channel.has_permissions(guild.me).manage_messages:
                await ctx.message.delete()
            await self.data.guild(guild).credentials.username.set(api_key)
            await ctx.send(_("La clé API a bien été réglée."))
            return
        try:
            await ctx.author.send(
                _(
                    "Veuillez envoyer la clé API Challonge ici.\n"
                    "Ouvrez ce site, ou aller dans vos paramètres d'utilisateur Challonge, "
                    'catégorie "Developer API", pour obtenir votre clé.\n'
                    "**https://challonge.com/settings/developer**"
                )
            )
        except discord.HTTPException:
            await ctx.send(
                _(
                    "Je n'ai pas pu vous envoyer de message privé. Activez les messages sur ce "
                    "serveur, ou utilisez la commande comme ceci: `{prefix}challongeset api <clé "
                    "API>`.\nAttention cependant à ne pas utiliser cette commande n'importe où, "
                    "votre clé doit rester secrète !"
                ).format(prefix=ctx.clean_prefix)
            )
            return
        pred = MessagePredicate.same_context(user=ctx.author)
        try:
            message = await self.bot.wait_for("message", check=pred, timeout=300)
        except asyncio.TimeoutError:
            await ctx.author.send(_("Requête expirée."))
            return
        await self.data.guild(guild).credentials.api.set(message.content)
        await ctx.author.send(_("La clé API a bien été réglée."))

    @challongeset.command(name="username")
    async def challongeset_username(self, ctx: commands.Context, username: str):
        """
        Réglage du nom d'utilisateur Challonge utilisé sur ce serveur.

        Exemple: `[p]challongeset username laggron42`
        """
        guild = ctx.guild
        await self.data.guild(guild).credentials.username.set(username)
        await ctx.send(_("Le nouveau nom d'utilisateur a bien été réglé."))

    @commands.group()
    @checks.admin_or_permissions(administrator=True)
    async def tournamentset(self, ctx: commands.Context):
        """
        Paramètres des tournois sur ce serveur.

        Note: seul les administrateurs ont accès à ces commandes, pas les T.O.
        Tapez `[p]firstsetup` pour plus d'infos sur les permissions.
        """
        pass

    @tournamentset.group(name="channels")
    async def tournamentset_channels(self, ctx: commands.Context):
        """
        Réglage des différents channels.
        """
        pass

    @tournamentset_channels.command(name="announcements")
    async def tournamentset_channels_announcements(
        self, ctx: commands.Context, *, channel: discord.TextChannel
    ):
        """
        Règle le channel des annonces.

        Les annonces suivantes y seront envoyées :
        - Début des inscriptions
        - Lancement du tournoi
        - Fin du tournoi
        """
        guild = ctx.guild
        if not channel.permissions_for(guild.me).read_messages:
            await ctx.send(_("Je n'ai pas la permission de lire les messages dans ce channel."))
        elif not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("Je n'ai pas la permission d'envoyer de messages dans ce channel."))
        else:
            await self.data.guild(guild).channels.announcements.set(channel.id)
            await ctx.send(_("Le nouveau channel est bien réglé."))

    @tournamentset_channels.command(name="checkin")
    async def tournamentset_channels_checkin(
        self, ctx: commands.Context, *, channel: Optional[discord.TextChannel]
    ):
        """
        Règle le channel du check-in.

        Le début du check-in y sera annoncé, et les gens devront y entrer une commande pour\
valider leur inscription.

        Donnez aucun channel pour ne pas restreindre l'accès à la commande à un channel.
        """
        guild = ctx.guild
        if channel is None:
            await self.data.guild(guild).channels.checkin.set(None)
            await ctx.send(
                _(
                    "Le check-in se fera désormais dans n'importe quel channel. Attention "
                    "cependant, les permissions de Red s'appliquent toujours."
                )
            )
            return
        if not channel.permissions_for(guild.me).read_messages:
            await ctx.send(_("Je n'ai pas la permission de lire les messages dans ce channel."))
        elif not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("Je n'ai pas la permission d'envoyer de messages dans ce channel."))
        else:
            await self.data.guild(guild).channels.checkin.set(channel.id)
            await ctx.send(_("Le nouveau channel est bien réglé."))

    @tournamentset_channels.command(name="register")
    async def tournamentset_channels_register(
        self, ctx: commands.Context, *, channel: Optional[discord.TextChannel]
    ):
        """
        Règle le channel des inscriptions.

        Le début des inscriptions y sera annoncé, et les gens devront y entrer une commande pour\
s'inscrire ou se désinscrire.

        Donnez aucun channel pour ne pas restreindre l'accès à la commande à un channel.
        """
        guild = ctx.guild
        if channel is None:
            await self.data.guild(guild).channels.register.set(None)
            await ctx.send(
                _(
                    "Les inscriptions se feront désormais dans n'importe quel channel. Attention "
                    "cependant, les permissions de Red s'appliquent toujours."
                )
            )
            return
        if not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("Je n'ai pas la permission d'envoyer de messages dans ce channel."))
        else:
            await self.data.guild(guild).channels.register.set(channel.id)
            await ctx.send(_("Le nouveau channel est bien réglé."))

    @tournamentset_channels.command(name="scores")
    async def tournamentset_channels_scores(
        self, ctx: commands.Context, *, channel: Optional[discord.TextChannel]
    ):
        """
        Règle le channel d'entrée des scores.

        Les gens devront y entrer une commande pour enregistrer leur résultat.

        Donnez aucun channel pour ne pas restreindre l'accès à la commande à un channel.
        """
        guild = ctx.guild
        if channel is None:
            await self.data.guild(guild).channels.scores.set(None)
            await ctx.send(
                _(
                    "L'entrée des scores se fera désormais dans n'importe quel channel. Attention "
                    "cependant, les permissions de Red s'appliquent toujours."
                )
            )
            return
        if not channel.permissions_for(guild.me).read_messages:
            await ctx.send(_("Je n'ai pas la permission de lire les messages dans ce channel."))
        elif not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("Je n'ai pas la permission d'envoyer de messages dans ce channel."))
        else:
            await self.data.guild(guild).channels.scores.set(channel.id)
            await ctx.send(_("Le nouveau channel est bien réglé."))

    @tournamentset_channels.command(name="queue")
    async def tournamentset_channels_queue(
        self, ctx: commands.Context, *, channel: discord.TextChannel
    ):
        """
        Règle le channel d'annonces des sets.
        """
        guild = ctx.guild
        if not channel.permissions_for(guild.me).read_messages:
            await ctx.send(_("Je n'ai pas la permission de lire les messages dans ce channel."))
        elif not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("Je n'ai pas la permission d'envoyer de messages dans ce channel."))
        else:
            await self.data.guild(guild).channels.queue.set(channel.id)
            await ctx.send(_("Le nouveau channel est bien réglé."))

    @tournamentset_channels.command(name="stream")
    async def tournamentset_channels_stream(
        self, ctx: commands.Context, *, channel: discord.TextChannel
    ):
        """
        Règle le channel d'annonces des streams.

        Il est conseillé de garder ce channel restreint aux T.O. et aux streamers.
        """
        guild = ctx.guild
        if not channel.permissions_for(guild.me).read_messages:
            await ctx.send(_("Je n'ai pas la permission de lire les messages dans ce channel."))
        elif not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("Je n'ai pas la permission d'envoyer de messages dans ce channel."))
        else:
            await self.data.guild(guild).channels.stream.set(channel.id)
            await ctx.send(_("Le nouveau channel est bien réglé."))

    @tournamentset_channels.command(name="to")
    async def tournamentset_channels_to(
        self, ctx: commands.Context, *, channel: discord.TextChannel
    ):
        """
        Règle le channel des T.O.

        Il est conseillé de garder ce channel restreint aux T.O. uniquement.
        Les annonces suivantes y seront envoyées :
        - Lag test demandé avec la commande `[p]lag`
        - Set prenant trop de temps
        - DQ automatique d'un joueur pour inactivité

        Attention, ce réglage ne donne pas de permissions supplémentaires aux personnes ayant
        accès au channel. Les paramètres de Red déterminent ceux ayant accès aux commandes. Tapez
        `[p]firstsetup` pour plus d'infos.
        """
        guild = ctx.guild
        if not channel.permissions_for(guild.me).read_messages:
            await ctx.send(_("Je n'ai pas la permission de lire les messages dans ce channel."))
        elif not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("Je n'ai pas la permission d'envoyer de messages dans ce channel."))
        else:
            await self.data.guild(guild).channels.to.set(channel.id)
            await ctx.send(_("Le nouveau channel est bien réglé."))

    @tournamentset_channels.command(name="category")
    async def tournamentset_channels_category(
        self, ctx: commands.Context, *, category: discord.CategoryChannel
    ):
        """
        Règle la catégorie de vos channels de tournois.

        Cette catégorie sera utilisée pour positionner la création de channels de sets.
        Une ou plusieurs catégories seront créés juste en dessous de la catégorie réglée avec\
cette commande. Ces catégories créées serviront aux channels de sets.

        Vous pouvez donner le nom complet de la catégorie ou son ID.
        """
        guild = ctx.guild
        await self.data.guild(guild).channels.category.set(category.id)
        await ctx.send(_("La nouvelle catégorie est bien réglée."))

    @tournamentset.group(name="roles")
    async def tournamentset_roles(self, ctx: commands.Context):
        """
        Réglage des différents rôles.

        Donnez le nom complet du rôle ou son ID.

        Le rôle de T.O. est optionel si vos T.O. sont également des modérateurs sur votre serveur.
        Dans le cas contraire, privilégiez le système de permissions de Red avec les commande
        `[p]set addadminrole` et `[p]set addmodrole`.
        Pour plus d'infos sur les permissions, tapez `[p]firstsetup`.
        """
        pass

    @tournamentset_roles.command(name="participant")
    async def tournamentset_roles_participant(self, ctx: commands.Context, *, role: discord.Role):
        """
        Règle le rôle de participant au tournoi.

        Ce rôle sera assigné aux membres dès leur inscription, et retiré une fois le tournoi\
terminé.
        """
        guild = ctx.guild
        if role.position >= guild.me.top_role.position:
            await ctx.send(
                _("Ce rôle est trop élevé. Placez le en dessous de mon rôle principal.")
            )
            return
        await self.data.guild(guild).roles.participant.set(role.id)
        await ctx.send(_("Le nouveau rôle est bien réglé."))

    @tournamentset_roles.command(name="streamer")
    async def tournamentset_roles_streamer(self, ctx: commands.Context, *, role: discord.Role):
        """
        Règle le rôle de streamer, ou casteur.

        Ce rôle donnera accès aux channels de sets, ainsi qu'aux commandes de streamer.
        """
        guild = ctx.guild
        if role.position >= guild.me.top_role.position:
            await ctx.send(
                _("Ce rôle est trop élevé. Placez le en dessous de mon rôle principal.")
            )
            return
        await self.data.guild(guild).roles.streamer.set(role.id)
        await ctx.send(_("Le nouveau rôle est bien réglé."))

    @tournamentset_roles.command(name="to")
    async def tournamentset_roles_to(self, ctx: commands.Context, *, role: discord.Role):
        """
        Règle le rôle de T.O. (tournament organizer)

        Ce rôle donnera accès aux commandes de tournois (sauf `[p]challongeset` et
        `[p]tournamentset`).

        :warning: **Utilisez ce rôle uniquement si vous avez besoin de séparer les modérateurs des\
T.O.**
        Dans le cas échéant, il est fortement recommandé d'utiliser les commandes de Red :\
`[p]set addadminrole` et `[p]set addmodrole`. Cela adaptera les permissions de l'intégralité des\
commandes de ce bot à vos modérateurs et administrateurs.
        """
        guild = ctx.guild
        if role.permissions.kick_members or role.permissions.manage_roles:
            # we consider this role is a mod role
            message = await ctx.send(
                _(
                    ":warning: Ce rôle semble avoir des permissions de modérateur ou "
                    "d'administrateur.\n\n"
                    "Il est fortement recommandé d'utiliser les commandes "
                    "de Red, `{prefix}set addadminrole` et `{prefix}set addmodrole`, "
                    "pour configurer vos rôles de modération et d'administration, adaptant les "
                    "permissions de l'intégralité des commandes du bot à votre staff.\n"
                    "Ce réglage est conseillé pour les T.O. n'étant pas modérateurs.\n"
                    "Pour plus d'informations, tapez `{prefix}firstsetup`.\n\n"
                    "Êtes vous sûr de vouloir continuer ?"
                ).format(prefix=ctx.clean_prefix)
            )
            pred = ReactionPredicate.yes_or_no(message, user=ctx.author)
            start_adding_reactions(message, ReactionPredicate.YES_OR_NO_EMOJIS)
            try:
                await self.bot.wait_for("reaction_add", check=pred, timeout=60)
            except asyncio.TimeoutError:
                await ctx.send(_("Requête expirée."))
                if ctx.channel.permissions_for(guild.me).manage_messages:
                    try:
                        await message.clear_reactions()
                    except discord.HTTPException:
                        pass
                return
            if pred.result is False:
                await ctx.send(_("Annulation..."))
                return
        if role.position >= guild.me.top_role.position:
            await ctx.send(
                _("Ce rôle est trop élevé. Placez le en dessous de mon rôle principal.")
            )
            return
        await self.data.guild(guild).roles.to.set(role.id)
        await ctx.send(_("Le nouveau rôle est bien réglé."))

    @tournamentset.group(name="games")
    async def tournamentset_games(self, ctx: commands.Context):
        """
        Configure les différents jeux des tournois.

        Utilisez d'abord `[p]tournamentset games add`, puis une explication vous sera donnée sur\
le reste des commandes.
        """
        pass

    @tournamentset_games.command(name="add")
    async def tournamentset_games_add(self, ctx: commands.Context, *, name: str):
        """
        Ajoute un nouveau jeu dans la liste.

        Le nom doit être le nom exact tel qu'il est affiché sur Challonge.

        Exemple: "Super Smash Bros. Ultimate"
        """
        guild = ctx.guild
        games = await self.data.custom("GAME", guild.id).all()
        if name in games:
            await ctx.send(
                _(
                    "Ce jeu existe déjà.\n"
                    "Supprimez le avec `{prefix}tournamentset games delete` ou éditez son "
                    "nom avec `{prefix}tournamentset games edit`."
                ).format(prefix=ctx.clean_prefix)
            )
            return
        # doing this ensures the creation of the identifier
        await self.data.custom("GAME", guild.id, name).role.set(None)
        await ctx.send(
            _(
                "Jeu ajouté à la liste !\n\n"
                "Vous pouvez désormais effectuer plusieurs réglages :\n"
                "- `{prefix}tournamentset games ruleset` : Réglage du channel de ruleset\n"
                "- `{prefix}tournamentset games role` : Réglage du rôle de joueur\n"
                "- `{prefix}tournamentset games baninfo` : Infos sur les bans de stage "
                "(ex: 2-3-1)\n"
                "- `{prefix}tournamentset games stages` : Liste des stages autorisés\n"
                "- `{prefix}tournamentset games counters` : Liste des counters autorisés\n"
                "- `{prefix}tournamentset games ranking` : Réglage du ranking Braacket\n\n"
                "- `{prefix}tournamentset games edit` : Editez le nom de ce jeu\n"
                "- `{prefix}tournamentset games delete` : Supprimez ce jeu de la liste\n\n"
                "Tous ces réglages sont optionels, mais apporteront plus de détails aux joueurs, "
                "ainsi que des nouvelles commandes (comme `{prefix}stages` ou `{prefix}rules`).\n"
                "Attention, si le rôle n'est pas réglé, le rôle @everyone sera utilisé par "
                "défaut pour les permissions et la mention à l'ouverture des inscriptions."
            ).format(prefix=ctx.clean_prefix)
        )

    @tournamentset_games.command(name="edit")
    async def tournamentset_games_edit(
        self, ctx: commands.Context, old_name: GameSetting, new_name: str
    ):
        """
        Edite le nom d'un jeu dans la liste.

        Donnez le nom de l'ancien jeu, puis son nouveau nom.
        Utilisez des guillmets s'il y a des espaces.

        Exemple: [p]tournamentset games edit "Super Smqsh Bros. Ultimate"\
"Super Smash Bros Ultimate"
        """
        guild = ctx.guild
        async with self.data.custom("GAME", guild.id).all() as games:
            content = games[old_name]
            games[new_name] = content
            del games[old_name]
        await ctx.send(_("Le nom a bien été édité !"))

    @tournamentset_games.command(name="delete", aliases=["del", "remove"])
    async def tournamentset_games_delete(self, ctx: commands.Context, game: GameSetting):
        """
        Supprime un jeu de la liste.
        """
        guild = ctx.guild
        async with self.data.custom("GAME", guild.id).all() as games:
            del games[game]
        await ctx.send(_("Le jeu a bien été supprimé de la liste."))

    @tournamentset_games.command(name="list")
    async def tournamentset_games_list(self, ctx: commands.Context):
        """
        Affiche tous les jeux enregistrés.
        """
        guild = ctx.guild
        async with self.data.custom("GAME", guild.id).all() as games:
            if not games:
                await ctx.send(_("Aucun jeu enregistré."))
                return
            text = _("Liste des jeux enregistrés :\n\n")
            for game in games.keys():
                text += f"- {game}\n"
        for page in pagify(text):
            await ctx.send(page)

    @tournamentset_games.command(name="show")
    async def tournamentset_games_show(self, ctx: commands.Context, *, game: GameSetting):
        """
        Affiche les réglages d'un jeu.
        """
        guild = ctx.guild
        if not ctx.channel.permissions_for(guild.me).embed_links:
            await ctx.send(_("J'ai besoin de la permission d'intégrer des liens dans ce channel."))
            return
        data = await self.data.custom("GAME", guild.id, game).all()
        role_id = data["role"]
        if role_id is None:
            role = "@everyone"
        else:
            role = guild.get_role(role_id)
            role = role.name if role else _("Rôle perdu.")
        ruleset = guild.get_channel(data["ruleset"])
        ruleset = ruleset.mention if ruleset else _("Channel perdu.")
        baninfo = data["baninfo"] if data["baninfo"] else _("Non réglé.")
        embed = discord.Embed(title=_("Réglages du jeu {game}").format(game=game))
        embed.description = _(
            "Rôle de joueur : {role}\n"
            "Channel des règles : {channel}\n"
            "Infos de ban : {baninfo}"
        ).format(role=role, channel=ruleset, baninfo=baninfo)
        if data["stages"]:
            embed.add_field(name=_("Stages"), value="\n".join([f"- {x}" for x in data["stages"]]))
        if data["counterpicks"]:
            embed.add_field(
                name=_("Contres"), value="\n".join([f"- {x}" for x in data["counters"]])
            )
        if data["ranking"]["league_name"]:
            embed.add_field(
                name=_("Ranking league"),
                value=_("Name: {name}\nID: {id}").format(
                    name=data["ranking"]["league_name"], id=data["ranking"]["league_id"]
                ),
            )
        else:
            embed.add_field(name=_("Ranking league"), value=_("Pas configuré."))
        await ctx.send(embed=embed)

    @tournamentset_games.command(name="ruleset")
    async def tournamentset_games_ruleset(
        self, ctx: commands.Context, game: GameSetting, *, channel: discord.TextChannel
    ):
        """
        Définis le channel des règles pour un jeu.

        Exemple: `[p]tournamentset games ruleset "Super Smash Bros. Ultimate" #règles-tournois`
        """
        guild = ctx.guild
        await self.data.custom("GAME", guild.id, game).ruleset.set(channel.id)
        await ctx.send(_("Le nouveau channel est bien réglé."))

    @tournamentset_games.command(name="role")
    async def tournamentset_games_role(
        self, ctx: commands.Context, game: GameSetting, *, role: Optional[discord.Role]
    ):
        """
        Définis le rôle de joueur pour un jeu.

        Ce rôle sera utilisé pour :
        - Régler les permissions du channel d'inscriptions lorsqu'elles sont ouvertes
        - Mentionner les joueurs à l'ouverture des inscriptions

        Donnez le nom complet du rôle ou son ID.

        Si ce rôle n'est pas fourni, le rôle @everyone est utilisé par défaut (sans mention).
        Utilisez la commande sans indiquer de rôle pour le réinitialiser à sa valeur par défaut.
        """
        guild = ctx.guild
        if role is None:
            await self.data.custom("GAME", guild.id, game).role.set(None)
            await ctx.send(_("Le rôle a été réinitialisé à sa valeur par défaut."))
        else:
            await self.data.custom("GAME", guild.id, game).role.set(role.id)
            await ctx.send(_("Le nouveau rôle est bien réglé."))

    @tournamentset_games.command(name="baninfo")
    async def tournamentset_games_baninfo(
        self, ctx: commands.Context, game: GameSetting, *, text: Optional[str]
    ):
        """
        Définis les infos sur les bans (ex: 2-3-1)

        Ces informations seront données à l'ouverture d'un set, et ne demandent pas un format\
particulier.
        Utilisez la commande sans paramètre pour réinitialiser cette valeur.

        Exemple : Si la valeur réglée est "2-3-1", voici ce qui s'affichera :
        ":game_die: **[joueur 1]** est tiré au sort pour commencer le ban des stages *(2-3-1)*"
        """
        guild = ctx.guild
        if text is not None and len(text) > 256:
            await ctx.send(
                _(
                    "Ce texte est trop long (>256 caractères). "
                    "Tapez `{prefix}help tournamentset games baninfo` pour plus de détails."
                ).format(prefix=ctx.clean_prefix)
            )
            return
        await self.data.custom("GAME", guild.id, game).baninfo.set(text)
        if text is not None:
            await ctx.send(_("Le nouveau texte est bien réglé."))
        else:
            await ctx.send(_("Le texte a été supprimé."))

    @tournamentset_games.command(name="stages")
    async def tournamentset_games_stages(
        self, ctx: commands.Context, game: GameSetting, *stages: str
    ):
        """
        Définis la liste des stages autorisés.

        Donnez les stages les uns à la suite des autres, avec des guillmets s'il y a des espaces.

        Exemple : `[p]tournamentset games stages "Super Smash Bros. Ultimate" "Champ de Bataille"\
"Destination Finale" "Stade Pokémon 2"`
        """
        guild = ctx.guild
        await self.data.custom("GAME", guild.id, game).stages.set(stages)
        if stages:
            await ctx.send(_("Les nouveaux stages ont bien été réglés."))
        else:
            await ctx.send(_("La liste des stages a été supprimée."))

    @tournamentset_games.command(name="counters")
    async def tournamentset_games_counters(
        self, ctx: commands.Context, game: GameSetting, *counters: str
    ):
        """
        Définis la liste des stages contres autorisés.

        Donnez les stages les uns à la suite des autres, avec des guillmets s'il y a des espaces.

        Exemple : `[p]tournamentset games counters "Super Smash Bros. Ultimate" "Champ de\
Bataille" "Destination Finale" "Stade Pokémon 2"`
        """
        guild = ctx.guild
        await self.data.custom("GAME", guild.id, game).counters.set(counters)
        if counters:
            await ctx.send(_("Les nouveaux stages ont bien été réglés."))
        else:
            await ctx.send(_("La liste des stages a été supprimée."))

    @tournamentset_games.command(name="ranking")
    async def tournamentset_games_ranking(
        self,
        ctx: commands.Context,
        game: GameSetting,
        league_name: Optional[str],
        league_id: Optional[str],
    ):
        """
        Définis les informations du ranking Braacket pour un jeu.

        Ceci sera utilisé pour le seeding.
        Vous devez donner le nom de la ligue, suivi de son ID.

        Omettez les deux valeurs pour supprimer ces informations.
        """
        guild = ctx.guild
        if league_name is None and league_id is None:
            await self.data.custom("GAME", guild.id, game).ranking.set(
                {"league_name": None, "league_id": None}
            )
            await ctx.send(_("Les informations de ranking ont été supprimées."))
        elif league_name is None or league_id is None:
            # only one value provided
            await ctx.send_help()
        else:
            await self.data.custom("GAME", guild.id, game).ranking.set(
                {"league_name": league_name, "league_id": league_id}
            )
            await ctx.send(_("Les nouvelles informations de ranking ont été configurées."))

    @tournamentset.command(name="delay")
    async def tournamentset_delay(self, ctx: commands.Context, delay: int):
        """
        Règle le délai avant DQ automatique d'un joueur inactif.

        Ce délai est en minutes.
        Donnez 0 minutes pour désactiver.
        """
        guild = ctx.guild
        if delay < 0:
            await ctx.send(_("Un délai ne peut pas être négatif !"))
            return
        await self.data.guild(guild).delay.set(delay)
        if delay == 0:
            await ctx.send(_("Le DQ automatique est désormais désactivé."))
        else:
            await ctx.send(
                _(
                    "Si un joueur ne réponds toujours pas dans son channel {delay} minutes "
                    "après sa création, il sera DQ automatiquement."
                ).format(delay=delay)
            )

    @tournamentset.command(name="register")
    async def tournamentset_register(self, ctx: commands.Context, opening: int, closing: int):
        """
        Règle l'heure d'ouverture et de fermeture des inscriptions.

        Vous devez donner le nombre d'**heures** avant l'ouverture du tournoi pour le début, et le\
nombre de **minutes** avant l'ouverture du tournoi pour la fin des inscriptions.
        D'abord l'heure d'ouverture, puis de fermeture.

        L'heure d'ouverture du tournoi est celle réglée sur votre tournoi Challonge.

        Pour désactiver l'ouverture ou la fermeture automatique des inscriptions, donnez 0 pour\
sa valeur correspondante.

        Exemple: `[p]tournamentset register 48 10` = Ouverture du check-in 45 heures avant\
l'ouverture du tournoi, puis fermeture 10 minutes avant.
        """
        guild = ctx.guild
        await self.data.guild(guild).register.set({"opening": opening, "closing": closing})
        if opening == 0 and closing == 0:
            await ctx.send(_("Les inscriptions automatiques sont désormais désactivées."))
        else:
            await ctx.send(
                _(
                    "Les inscriptions seront ouvertes {opening} heures avant le début et fermées "
                    "{closing} minutes avant le début du tournoi."
                ).format(opening=opening, closing=closing)
            )

    @tournamentset.command(name="checkin")
    async def tournamentset_checkin(self, ctx: commands.Context, opening: int, closing: int):
        """
        Règle l'heure d'ouverture et de fermeture du check-in.

        Vous devez donner le nombre de minutes avant l'ouverture du tournoi pour chaque valeur.
        D'abord l'heure d'ouverture, puis de fermeture.

        L'heure d'ouverture du tournoi est celle réglée sur votre tournoi Challonge.

        Pour désactiver le check-in, donnez 0 pour les deux valeurs

        Exemple: `[p]tournamentset checkin 60 15` = Ouverture du check-in 60 minutes avant\
l'ouverture du tournoi, puis fermeture 15 minutes avant.
        """
        guild = ctx.guild
        await self.data.guild(guild).checkin.set({"opening": opening, "closing": closing})
        if opening == 0 and closing == 0:
            await ctx.send(_("Le check-in est désormais désactivé."))
        else:
            await ctx.send(
                _(
                    "Le check-in sera ouvert {opening} minutes avant le début et fermé "
                    "{closing} minutes avant le début du tournoi."
                ).format(opening=opening, closing=closing)
            )

    @tournamentset.command(name="startbo5")
    async def tournamentset_startbo5(self, ctx: commands.Context, level: int):
        """
        Règle quand les sets passent au format Best of 5 (BO5)

        Vous devez entrer un nombre pour définir le niveau:
        0 = top 7
        1 = top 5
        2 = top 3 (winner + loser final)
        -1 = top 12...
        """
        guild = ctx.guild
        await self.data.guild(guild).start_bo5.set(level)
        await ctx.send(_("Le niveau a bien été réglé."))

    @tournamentset.command(name="settings")
    async def tournamentset_settings(self, ctx: commands.Context):
        """
        Affiche tous les réglages de ce serveur.
        """
        guild = ctx.guild
        if not ctx.channel.permissions_for(guild.me).embed_links:
            await ctx.send(_("J'ai besoin de la permission d'intégrer des liens dans ce channel."))
            return
        data = await self.data.guild(guild).all()
        no_games = len(await self.data.custom("GAME", guild.id).all())
        if data["credentials"]["api"]:
            challonge = _("Configuré")
        else:
            challonge = _("Non configuré. Utilisez `{prefix}challongeset`").format(
                prefix=ctx.clean_prefix
            )
        delay = data["delay"]
        start_bo5 = data["start_bo5"]
        if data["register"]["opening"] != 0:
            register_start = _("{time} heures avant le début du tournoi.").format(
                time=data["register"]["opening"]
            )
        else:
            register_start = _("manuelle.")
        if data["register"]["closing"] != 0:
            register_end = _("{time} minutes avant le début du tournoi.").format(
                time=data["register"]["closing"]
            )
        else:
            register_end = _("manuelle.")
        if data["checkin"]["opening"] != 0:
            checkin_start = _("{time} minutes avant le début du tournoi.").format(
                time=data["checkin"]["opening"]
            )
        else:
            checkin_start = _("manuelle.")
        if data["checkin"]["closing"] != 0:
            checkin_end = _("{time} minutes avant le début du tournoi.").format(
                time=data["checkin"]["closing"]
            )
        else:
            checkin_end = _("manuelle.")
        channels = {}
        for k, v in data["channels"].items():
            if not v:
                channels[k] = _("Non réglé")
                continue
            channel = guild.get_channel(v)
            if not channel:
                channels[k] = _("Perdu")
            else:
                if isinstance(channel, discord.TextChannel):
                    channels[k] = channel.mention
                else:
                    # category
                    channels[k] = channel.name
        channels = _(
            "Catégorie : {category}\n\n"
            "Annonces : {announcements}\n"
            "Inscriptions : {register}\n"
            "Check-in : {checkin}\n"
            "Queue : {queue}\n"
            "Scores : {scores}\n"
            "Stream : {stream}\n"
            "T.O. : {to}"
        ).format(**channels)
        roles = {}
        for k, v in data["roles"].items():
            if not v:
                roles[k] = _("Non réglé")
            role = guild.get_role(v)
            if not role:
                roles[k] = _("Perdu")
            else:
                roles[k] = role.name
        roles = _(
            "Participant : {participant}\n" "Streamer : {streamer}\n" "T.O. : {to}\n"
        ).format(**roles)
        embeds = []
        embed = discord.Embed(title=_("Paramètres"))
        embed.description = _(
            "Identifiants Challonge : {challonge}\n"
            "Nombre de jeux configurés : {games}\n"
            "Délai avant DQ : {delay} minutes\n"
            "Début du BO5 : {bo5} *(utilisez `{prefix}help tournamentset delay`)*"
        ).format(
            challonge=challonge,
            games=no_games,
            delay=delay,
            bo5=start_bo5,
            prefix=ctx.clean_prefix,
        )
        embed.add_field(
            name=_("Inscriptions"),
            value=_("Ouverture : {opening}\nFermeture : {closing}").format(
                opening=register_start, closing=register_end
            ),
        )
        embed.add_field(
            name=_("Check-in"),
            value=_("Ouverture : {opening}\nFermeture : {closing}").format(
                opening=checkin_start, closing=checkin_end
            ),
        )
        embeds.append(embed)
        embed = discord.Embed(title=_("Paramètres"))
        embed.add_field(name=_("Channels"), value=channels)
        embed.add_field(name=_("Rôles"), value=roles)
        embeds.append(embed)
        await menus.menu(ctx, embeds, controls=menus.DEFAULT_CONTROLS)

    @credentials_check
    @commands.command()
    @checks.mod_or_permissions(administrator=True)
    @commands.cooldown(1, 30, commands.BucketType.guild)
    async def setup(self, ctx: commands.Context, url: ChallongeURLConverter):
        """
        Setup le tournoi actuel du serveur.

        Vous devez donner un URL Challonge valide.
        """
        guild = ctx.guild
        message = await self._verify_settings(ctx)
        if message:
            await ctx.send(message)
            return
        del message
        if self.tournament is not None:
            await ctx.send(
                _("Un tournoi semble déjà être configuré. Utilisez `{prefix}reset`.").format(
                    prefix=ctx.clean_prefix
                )
            )
            return
        register_time = await self.data.guild(guild).register()
        checkin_time = await self.data.guild(guild).checkin()
        credentials = await self.data.guild(guild).credentials()
        achallonge.set_credentials(credentials["username"], credentials["api"])
        async with ctx.typing():
            data = await async_http_retry(achallonge.tournaments.show, url, loop=self.bot.loop)
            tournament: ChallongeTournament = ChallongeTournament.from_challonge_data(
                data,
                register_time["opening"],
                register_time["closing"],
                checkin_time["opening"],
                checkin_time["closing"],
            )
        del register_time, checkin_time
        games = await self.data.custom("GAME", guild.id).all()
        if tournament.game not in games:
            message = await ctx.send(
                _(
                    ":warning: **Le jeu {game} n'est pas enregistré sur le bot !**\n\n"
                    "Vous pouvez configurer les différents réglages de ce jeu en tapant la "
                    "commande `{prefix}tournamentset games add {game}`.\n"
                    "Sinon, vous pouvez continuer sans configuration, mais les fonctions "
                    "suivantes ne seront pas disponibles :\n"
                    "- Indication d'un channel de règles\n"
                    "- Utilisation d'un rôle pour les permissions des inscriptions (le rôle "
                    "@everyone sera utilisé)\n"
                    "- Précision du mode de ban\n"
                    "- Liste des stages starters/counters\n"
                    "- Ranking et seeding avec Braacket\n\n"
                    "Souhaitez vous continuer ou annuler ?"
                ).format(game=tournament.game, prefix=ctx.clean_prefix)
            )
            pred = ReactionPredicate.yes_or_no(message, user=ctx.author)
            start_adding_reactions(message, ReactionPredicate.YES_OR_NO_EMOJIS)
            try:
                await self.bot.wait_for("reaction_add", check=pred, timeout=30)
            except asyncio.TimeoutError:
                await ctx.send(_("Requête expirée."))
                return
            if pred.result is False:
                await ctx.send(_("Annulation."))
                return
            await message.delete()
        del games
        game = await self.data.custom("GAME", guild.id, tournament.game).all()

        def format_datetime(datetime: Optional[datetime]):
            if datetime:
                return datetime.strftime("%a %d %b %H:%M")
            else:
                return _("Manuelle")

        embed = discord.Embed(title=f"{tournament.name} • *{tournament.game}*")
        embed.url = tournament.url
        if tournament.limit is not None:
            embed.description = _("Tournoi de {limit} joueurs.").format(limit=tournament.limit)
        else:
            embed.description = _("Tournoi sans limite de joueurs.")
        embed.description += _("\nDébut du tournoi: {date}").format(
            date=format_datetime(tournament.tournament_start)
        )
        embed.add_field(
            name=_("Inscriptions"),
            value=_("Ouverture : {opening}\nFermeture : {closing}").format(
                opening=format_datetime(tournament.register_start),
                closing=format_datetime(tournament.register_stop),
            ),
        )
        embed.add_field(
            name=_("Check-in"),
            value=_("Ouverture : {opening}\nFermeture : {closing}").format(
                opening=format_datetime(tournament.checkin_start),
                closing=format_datetime(tournament.checkin_stop),
            ),
        )
        ruleset = guild.get_channel(game["ruleset"])
        ruleset = ruleset.mention if ruleset else _("Non défini")
        role = guild.get_role(game["role"]) or guild.default_role
        baninfo = game["baninfo"] or _("Non défini")
        embed.add_field(
            name=_("Options du jeu"),
            value=_("Règles : {rules}\nRôle de joueur : {role}\nMode de ban : {ban}").format(
                rules=ruleset, role=role, ban=baninfo,
            ),
        )
        if game["stages"]:
            embed.add_field(name=("Stages"), value="".join([f"- {x}\n" for x in game["stages"]]))
        if game["counterpicks"]:
            embed.add_field(
                name=("Counterpicks"), value="".join([f"- {x}\n" for x in game["counterpicks"]])
            )
        embed.set_footer(
            text=_("Fuseau horaire : {tz}").format(tz=tournament.tournament_start.tzname())
        )
        message = await ctx.send(_("Les informations sont-elles correctes ?"), embed=embed)
        pred = ReactionPredicate.yes_or_no(message, user=ctx.author)
        start_adding_reactions(message, ReactionPredicate.YES_OR_NO_EMOJIS)
        try:
            await self.bot.wait_for("reaction_add", check=pred, timeout=30)
        except asyncio.TimeoutError:
            await ctx.send(_("Requête expirée."))
            return
        if pred.result is False:
            await ctx.send(_("Annulation."))
            return
        self.tournament = tournament
        await self.data.guild(guild).tournament.set(tournament.to_dict())
        await ctx.send(_("Le tournoi est bien réglé !"))
