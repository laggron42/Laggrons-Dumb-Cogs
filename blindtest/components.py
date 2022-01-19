import asyncio
import discord
import lavalink

from discord.ui import View, Button, Select
from discord.components import SelectOption

from redbot.core.utils import predicates

from typing import TYPE_CHECKING, List

from .utils import format_time

if TYPE_CHECKING:
    from .session import Session


# ---------------------------------------------------
#               Track selection view
# ---------------------------------------------------


class PlayNowButton(Button):
    def __init__(self, session: "Session", index: int, interaction: discord.Interaction):
        self.session = session
        self.index = index
        self.interaction = interaction
        super().__init__(
            style=discord.ButtonStyle.green,
            label="Jouer immédiatement",
            emoji="\N{BLACK RIGHT-POINTING TRIANGLE WITH DOUBLE VERTICAL BAR}"
            "\N{VARIATION SELECTOR-16}",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        track = self.session.queue.pop(self.index)
        self.session.queue.insert(self.session.position + 1, track)
        await self.session.next()
        # discord can be weird
        await self.interaction.edit_original_message(content="Lecture...", embed=None, view=None)
        await interaction.response.defer()


class BumpButton(Button):
    def __init__(self, session: "Session", index: int, interaction: discord.Interaction):
        self.session = session
        self.index = index
        self.interaction = interaction
        super().__init__(
            style=discord.ButtonStyle.blurple,
            label="Passer en musique suivante",
            emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}"
            "\N{VARIATION SELECTOR-16}",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        track = self.session.queue.pop(self.index)
        self.session.queue.insert(self.session.position + 1, track)
        # discord can be weird
        await self.interaction.edit_original_message(
            content="La musique sélectionnée est passée en haut de la "
            "file d'attente et sera jouée ensuite.",
            embed=None,
            view=None,
        )
        await interaction.response.defer()


class RemoveFromPlaylistButton(Button):
    def __init__(self, session: "Session", index: int, interaction: discord.Interaction):
        self.session = session
        self.index = index
        self.interaction = interaction
        super().__init__(
            style=discord.ButtonStyle.red,
            label="Retirer de la playlist",
            emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
            row=0,
        )
        if index < self.session.position:
            self.disabled = True

    async def callback(self, interaction: discord.Interaction):
        del self.session.queue[self.index]
        # discord can be weird
        await self.interaction.edit_original_message(
            content="La musique sélectionnée a été retirée.",
            embed=None,
            view=None,
        )
        await interaction.response.defer()


class AddTrackButton(Button):
    def __init__(self, session: "Session", index: int, interaction: discord.Interaction):
        self.session = session
        self.index = index
        self.interaction = interaction
        super().__init__(
            style=discord.ButtonStyle.blurple,
            label="Insérer une nouvelle musique à la suite",
            emoji="\N{SQUARED NEW}",
            row=1,
        )
        if index < self.session.position:
            self.disabled = True

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.interaction.edit_original_message(
            content="Envoyez un lien ou les termes de recherche "
            "YouTube pour ajouter une nouvelle musique.",
            embed=None,
            view=None,
        )
        try:
            response = await self.session.bot.wait_for(
                "message",
                check=predicates.MessagePredicate.same_context(interaction, user=interaction.user),
                timeout=120,
            )
        except asyncio.TimeoutError:
            await self.interaction.delete_original_message()
            return

        try:
            await response.delete()
        except Exception:
            pass

        tracks, playlist = await self.session.player.get_tracks(response.content)
        if not tracks:
            await self.interaction.edit_original_message("Aucune musique trouvée.")
            return
        track: lavalink.Track = tracks[0]
        self.session.queue.insert(self.index + 1, track)

        embed = discord.Embed()
        embed.title = track.title
        embed.url = track.uri
        embed.set_thumbnail(url=track.thumbnail)
        embed.description = f"Position #{self.index + 1}/{len(self.session.queue)}"
        await self.interaction.edit_original_message(content="Musique ajoutée.", embed=embed)


class TrackSelectView(View):
    def __init__(self, session: "Session", index: int, interaction: discord.Interaction):
        super().__init__()
        self.add_item(PlayNowButton(session, index, interaction))
        self.add_item(BumpButton(session, index, interaction))
        self.add_item(RemoveFromPlaylistButton(session, index, interaction))
        self.add_item(AddTrackButton(session, index, interaction))


# ---------------------------------------------------
#            Permanent message view
# ---------------------------------------------------


class PlayPauseButton(Button):
    def __init__(self, session: "Session"):
        self.session = session
        super().__init__(
            emoji="\N{BLACK RIGHT-POINTING TRIANGLE WITH DOUBLE VERTICAL BAR}"
            "\N{VARIATION SELECTOR-16}",
            row=0,
        )

    def to_component_dict(self):
        self.style = self.get_style()
        return super().to_component_dict()

    def get_style(self):
        if self.session.player.current is None:
            return discord.ButtonStyle.gray
        if self.session.player.paused:
            return discord.ButtonStyle.red
        else:
            return discord.ButtonStyle.green

    async def callback(self, interaction: discord.Interaction):
        if self.session.player.current is None:
            await self.session.start()
        else:
            if self.session.player.paused:
                await self.session.player.resume()
            else:
                await self.session.player.pause()
            self.session.player.repeat = True
        await interaction.response.defer()


class PreviousButton(Button):
    def __init__(self, session: "Session"):
        self.session = session
        super().__init__(
            style=discord.ButtonStyle.gray,
            emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}"
            "\N{VARIATION SELECTOR-16}",
            row=0,
        )

    def to_component_dict(self):
        self.disabled = self.get_disabled()
        return super().to_component_dict()

    def get_disabled(self) -> bool:
        if self.session.position == 0:
            return True
        else:
            return False

    async def callback(self, interaction: discord.Interaction):
        await self.session.prev()
        await interaction.response.defer()


class NextButton(Button):
    def __init__(self, session: "Session"):
        self.session = session
        super().__init__(
            style=discord.ButtonStyle.gray,
            emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}"
            "\N{VARIATION SELECTOR-16}",
            row=0,
        )

    def to_component_dict(self):
        self.disabled = self.get_disabled()
        return super().to_component_dict()

    def get_disabled(self) -> bool:
        if self.session.position >= len(self.session.queue) - 1:
            return True
        else:
            return False

    async def callback(self, interaction: discord.Interaction):
        await self.session.next()
        await interaction.response.defer()


class VolumeButton(Button):
    def __init__(self, session: "Session", volume: int, high: bool):
        self.session = session
        self.volume = volume
        super().__init__(
            style=discord.ButtonStyle.gray,
            emoji="\N{SPEAKER WITH THREE SOUND WAVES}"
            if high
            else "\N{SPEAKER WITH ONE SOUND WAVE}",
            row=1,
        )

    def to_component_dict(self):
        self.disabled = self.get_disabled()
        return super().to_component_dict()

    def get_disabled(self) -> bool:
        if self.session.player is None:
            return True
        if self.session.player.volume == self.volume:
            return True
        else:
            return False

    async def callback(self, interaction: discord.Interaction):
        await self.session.player.set_volume(self.volume)
        await interaction.response.defer()


class CancelButton(Button):
    def __init__(self, session: "Session"):
        self.session = session
        super().__init__(
            style=discord.ButtonStyle.red,
            emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        view = discord.ui.View()
        approve_button = discord.ui.Button(
            style=discord.ButtonStyle.green,
            emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}",
            custom_id=f"yes-{interaction.message.id}",
        )
        deny_button = discord.ui.Button(
            style=discord.ButtonStyle.red,
            emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
            custom_id=f"no-{interaction.message.id}",
        )
        view.add_item(approve_button)
        view.add_item(deny_button)
        await interaction.response.send_message(
            "En cliquant sur ce bouton, vous allez déconnecter l'assistant de Blind Test.\n\n"
            "La musique actuelle sera toujours en cours et pourra "
            "être contrôlée avec les commandes audio classiques.",
            view=view,
            ephemeral=True,
        )

        def check_same_user(inter):
            return inter.user.id == interaction.user.id

        try:
            x = await self.session.bot.wait_for("interaction", check=check_same_user, timeout=20)
        except asyncio.TimeoutError:
            await interaction.edit_original_message(content="Demande expirée.", view=None)
            return
        custom_id = x.data.get("custom_id")
        if custom_id == f"no-{interaction.message.id}":
            await interaction.delete_original_message()
            return
        await self.session.end()
        await interaction.edit_original_message(content="Blind test terminé.", view=None)


class PlaylistMenu(Select):
    def __init__(self, session: "Session"):
        self.session = session
        self.page = 0
        super().__init__(
            placeholder="Musiques suivantes",
            row=3,
        )

    def to_component_dict(self):
        # generating options when needed
        self.options = self.generate_options()
        return super().to_component_dict()

    def make_option(self, index: int):
        track = self.session.queue[index]
        if len(track.title) > 50:
            description = track.title[:49] + "..."
        else:
            description = track.title
        label = f"#{index + 1}/{len(self.session.queue)} • Durée: {format_time(track.length)}"
        emoji = "\N{SPEAKER WITH THREE SOUND WAVES}" if index == self.session.position else None
        return SelectOption(label=label, value=index, description=description, emoji=emoji)

    def generate_options(self) -> List[SelectOption]:
        offset = self.page * 25

        if offset == 0:
            options = []
        else:
            options = [SelectOption(label="Page précédente", value=f"page-{self.page-1}")]

        if len(self.session.queue) - offset <= 24:
            for i in range(offset, len(self.session.queue)):
                options.append(self.make_option(i))
            return options

        options = [self.make_option(i) for i in range(offset, 23)]
        options.append(SelectOption(label="Page suivante", value=f"page-{self.page+1}"))
        return options

    async def callback(self, interaction: discord.Interaction):
        data = interaction.data.get("values")[0]
        if data.startswith("page-"):
            page = int(data.replace("page-", ""))
            self.page = page
            self.options = self.generate_options()
            await interaction.edit_original_message(view=self.view)
            return
        index = int(data)
        try:
            track = self.session.queue[index]
        except IndexError:
            await interaction.response.send_message(
                "Erreur : la musique demandée n'existe pas.",
                ephemeral=True,
            )
            return
        view = TrackSelectView(self.session, index, interaction)
        embed = discord.Embed()
        embed.title = track.title
        embed.url = track.uri
        embed.set_thumbnail(url=track.thumbnail)
        length = len(self.session.queue)
        embed.description = (
            f"Musique #{index + 1}/{length} *(encore {index - self.session.position} musiques)*\n"
            f"Durée: {format_time(track.length)}"
        )
        embed.set_footer(text="Cliquez sur les boutons pour faire quelque chose.")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class PlayerView(View):
    def __init__(self, session: "Session"):
        self.session = session
        super().__init__(timeout=3600)
        self.add_item(PreviousButton(session))
        self.add_item(PlayPauseButton(session))
        self.add_item(NextButton(session))
        self.add_item(VolumeButton(session, 20, high=False))
        self.add_item(VolumeButton(session, 70, high=True))
        self.add_item(CancelButton(session))
        self.add_item(PlaylistMenu(session))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.session.player:
            return True
        try:
            await self.session.connect()
        except Exception:
            await interaction.response.send_message("Impossible de se connecter au channel vocal.")
            return False
        else:
            return True
