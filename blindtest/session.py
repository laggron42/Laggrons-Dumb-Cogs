import discord
import lavalink

from typing import TYPE_CHECKING, List, Optional

from redbot.core import audio
from discord.ext import tasks

from .components import PlayerView
from .utils import draw_time, format_time

if TYPE_CHECKING:
    from redbot.core.bot import Red


class Session:
    """
    Represents a blind test session.
    """

    def __init__(
        self,
        bot: "Red",
        guild: discord.Guild,
        channel: discord.VoiceChannel,
        context_channel: discord.TextChannel,
    ):
        self.bot = bot
        self.guild = guild
        self.channel = channel
        self.context_channel = context_channel
        self.player = audio.get_player(guild.id)
        if self.player:
            self.player.repeat = True

        self.queue: List[lavalink.Track] = []
        self.position = 0
        self.message: Optional[discord.Message] = None
        self.view = PlayerView(self)

    @tasks.loop(seconds=1, reconnect=True)
    async def update_message_loop(self):
        await self.update_message()

    @property
    def current_track(self) -> lavalink.Track:
        return self.queue[self.position]

    async def connect(self):
        self.player = await audio.connect(self.bot, self.channel)
        self.player.repeat = True

    async def update_message(self):
        track = self.current_track
        embed = discord.Embed()

        embed.title = track.title
        embed.url = track.uri
        embed.set_thumbnail(url=track.thumbnail)

        position = format_time((self.player or track).position)
        duration = (
            "LIVE" if track.is_stream else format_time(track.length)
        )
        embed.description = draw_time(self.player) + f"`{position}`/`{duration}`"
        embed.set_footer(text=f"Musique {self.position + 1}/{len(self.queue)}")

        if self.position != len(self.queue) - 1:
            next_track = self.queue[self.position + 1]
            embed.add_field(
                name="Musique suivante", value=f"[{next_track.title}]({next_track.uri})"
            )

        if self.message:
            await self.message.edit(embed=embed, view=self.view)
        else:
            self.message = await self.context_channel.send(embed=embed, view=self.view)
            self.update_message_loop.start()

    async def start(
        self, track_index: Optional[int] = None, requester: Optional[discord.Member] = None
    ):
        if self.player is None:
            raise RuntimeError("Player is not connected")
        if track_index:
            self.position = track_index
        requester = requester or self.guild.me
        await self.player.play(requester=requester, track=self.current_track)
        self.player.repeat = True

    async def next(self):
        if self.position == len(self.queue) - 1:
            raise RuntimeError("No next track.")
        if self.player is None:
            raise RuntimeError("Player is not connected")
        paused = self.player.paused
        await self.player.stop()
        self.position += 1
        if not paused:
            await self.start()

    async def prev(self):
        if self.position == 0:
            raise RuntimeError("No previous track.")
        if self.player is None:
            raise RuntimeError("Player is not connected")
        paused = self.player.paused
        await self.player.stop()
        self.position -= 1
        if not paused:
            await self.start()

    async def end(self):
        self.update_message_loop.stop()
        if self.message:
            await self.message.delete()
        self.bot.get_cog("BlindTest").session = None
