from typing import TYPE_CHECKING

from redbot.core import commands
from redbot.core import audio

from .session import Session

if TYPE_CHECKING:
    from redbot.core.bot import Red


class BlindTest(commands.Cog):
    """
    A blind test manager interacting with the Audio cog.
    """

    def __init__(self, bot: "Red"):
        self.bot = bot
        self.session = None

    async def initialize(self):
        await self.bot.wait_until_red_ready()  # needed to ensure `bot` is fully initialized
        await audio.initialize(self.bot, "BlindTest", 260)

    async def shutdown(self):
        if self.session:
            self.session.update_message_loop.stop()
        await audio.shutdown("BlindTest", 260)

    def cog_unload(self):
        self.bot.loop.create_task(self.shutdown())

    @commands.group()
    @commands.guild_only()
    async def bt(self, ctx: commands.Context):
        """
        Gestionnaire de Blind Test.
        """
        pass

    @bt.command(name="start")
    async def bt_start(self, ctx: commands.Context, *, query: str):
        """
        Démarre une session.
        """
        if self.session is not None:
            await ctx.send("Il y a déjà une session en cours.")
            return
        if await audio.dj_enabled(ctx.guild) and not await audio.is_dj(ctx.author):
            await ctx.send("Vous devez avoir le rôle DJ pour faire cela.")
            return
        player = audio.get_player(ctx.guild.id)
        if not player:  # not currently connected to a voice channel
            if not ctx.author.voice:
                await ctx.send("Vous devez être dans un channel vocal.")
                return
            player = await audio.connect(self.bot, ctx.author.voice.channel)
        else:
            await player.stop()
        player.repeat = True
        self.session = Session(self.bot, ctx.guild, ctx.author.voice.channel, ctx.channel)
        self.session.player = player
        tracks, playlist = await player.get_tracks(query)
        self.session.queue = list(tracks)
        # await player.stop()  # clear its own queue
        await self.session.update_message()

    @bt.command(name="skip")
    async def bt_skip(self, ctx: commands.Context, tracks_to_skip: int):
        """
        Passe un certain nombre de musiques de la playlist.

        Le bot sera mis en pause une fois positionné.
        """
        if self.session is None:
            await ctx.send("Il n'y a pas de session en cours.")
            return
        if await audio.dj_enabled(ctx.guild) and not await audio.is_dj(ctx.author):
            await ctx.send("Vous devez avoir le rôle DJ pour faire cela.")
            return
        if self.session.position + tracks_to_skip > len(self.session.queue) - 1:
            await ctx.send("Vous dépassez la taille de la liste d'attente !")
            return
        if self.session.player:
            await self.session.player.stop()
        self.session.position += tracks_to_skip
        message = "La position a été modifiée. Cliquez sur play pour reprendre."
        if self.session.message:
            await self.session.message.reply(message)
        else:
            await ctx.send(message)

    @bt.command(name="clear")
    async def bt_clear(self, ctx: commands.Context):
        """
        Annule la session en cours.
        """
        if self.session is None:
            await ctx.send("Aucune session en cours.")
            return
        if await audio.dj_enabled(ctx.guild) and not await audio.is_dj(ctx.author):
            await ctx.send("Vous devez avoir le rôle DJ pour faire cela.")
            return
        await self.session.end()
        self.session = None
        await ctx.tick()

    @bt.command(name="postmsg")
    async def bt_postmsg(self, ctx: commands.Context):
        """
        Renvoie le message de contrôle du blind test.

        Utile si le message est parti trop haut ou ne s'actualise plus.
        """
        if self.session is None:
            await ctx.send("Aucune session en cours.")
            return
        if await audio.dj_enabled(ctx.guild) and not await audio.is_dj(ctx.author):
            await ctx.send("Vous devez avoir le rôle DJ pour faire cela.")
            return
        if self.session.message:
            try:
                await self.session.message.delete()
            except Exception:
                pass
        self.session.update_message_loop.stop()
        self.session.message = None
        self.session.update_message_loop.start()
        await ctx.tick()
