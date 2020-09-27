import discord
import logging

from redbot.core import commands
from redbot.core import checks
from redbot.core.i18n import Translator

from .abc import MixinMeta

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)


class Registration(MixinMeta):

    @commands.command(name="in")
    @commands.guild_only()
    @commands.check()  # TODO : Rajouter les vérifs
    async def auto_inscription(self, ctx: commands.Context):
        pass

    @commands.command()
    @commands.guild_only()
    @commands.check()  # TODO : Rajouter les vérifs
    async def out(self, ctx: commands.Context):
        pass
