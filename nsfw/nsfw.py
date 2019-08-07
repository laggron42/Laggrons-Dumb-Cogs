# Rule34 by retke, aka El Laggron

import discord
import aiohttp
import os
import logging

from redbot import __version__ as red_version
from redbot.core import checks, commands
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import menus

from . import errors
from .rule34 import Rule34
from .e621 import e621

log = logging.getLogger("laggron.nsfw")
log.setLevel(logging.DEBUG)

_ = Translator("Say", __file__)
BaseCog = getattr(commands, "Cog", object)

# Red 3.0 backwards compatibility, thanks Sinbad
listener = getattr(commands.Cog, "listener", None)
if listener is None:

    def listener(name=None):
        return lambda x: x


class NSFW(BaseCog):
    """
    Multiple NSFW commands looking over https://rule34.paheal.net/, https://rule34.xxx/ and\
    https://e621.net/
    """

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(
            headers={
                "User-Agent": f"Red-DiscordBot/{red_version} NSFW cog from Laggrons-Dumb-Cogs"
            },
            loop=bot.loop,
        )
        self.rule34 = Rule34(self.session)
        self.e621 = e621(self.session)
        self._init_logger()

    def _init_logger(self):
        log_format = logging.Formatter(
            f"%(asctime)s %(levelname)s {self.__class__.__name__}: %(message)s",
            datefmt="[%d/%m/%Y %H:%M]",
        )
        # logging to a log file
        # file is automatically created by the module, if the parent foler exists
        cog_path = cog_data_path(self)
        if cog_path.exists():
            log_path = cog_path / f"{os.path.basename(__file__)[:-3]}.log"
            file_handler = logging.FileHandler(log_path)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(log_format)
            log.addHandler(file_handler)

        # stdout stuff
        stdout_handler = logging.StreamHandler()
        stdout_handler.setFormatter(log_format)
        # if --debug flag is passed, we also set our debugger on debug mode
        if logging.getLogger("red").isEnabledFor(logging.DEBUG):
            stdout_handler.setLevel(logging.DEBUG)
        else:
            stdout_handler.setLevel(logging.INFO)
        log.addHandler(stdout_handler)
        self.stdout_handler = stdout_handler

    @commands.command()
    @commands.cooldown(5, 10, commands.BucketType.channel)
    @commands.is_nsfw()
    async def r34(self, ctx, *, search: str = None):
        """
        Search on https://rule34.xxx/
        """
        try:
            results = await self.rule34.get_images(search.split() if search else None)
        except errors.NotFound:
            await ctx.send("No result.")
            return
        embeds = []
        total = len(results)
        for i, post in enumerate(results):
            embed = discord.Embed()
            embed.title = post.source
            embed.url = post.source
            embed.set_footer(text="Page {page}/{total}".format(page=i + 1, total=total))
            embed.set_image(url=post.file_url)
            embeds.append(embed)
        await menus.menu(ctx, embeds, menus.DEFAULT_CONTROLS, timeout=60)

    @commands.command()
    @commands.cooldown(1, 2, commands.BucketType.channel)
    @commands.is_nsfw()
    async def e621(self, ctx, *, search: str = "order:random"):
        """
        Search on https://e621.net/
        """
        try:
            results = await self.e621.get_images(search.split())
        except errors.NotFound:
            await ctx.send("No result.")
            return
        embeds = []
        total = len(results)
        for i, post in enumerate(results):
            embed = discord.Embed()
            embed.title = post.source
            embed.url = post.file_url
            embed.description = post.description[:1024]
            embed.set_footer(text="Page {page}/{total}".format(page=i + 1, total=total))
            embed.set_image(url=post.file_url)
            embeds.append(embed)
        await menus.menu(ctx, embeds, menus.DEFAULT_CONTROLS, timeout=60)
