import discord

from redbot.core import commands, Config, checks
from redbot.core.translator import Translator, cog_i18n

_ = Translator("Say", __file__)


@cog_i18n(_)
class BetterMod:
    """
    An alternative to the Red core moderation system, providing a different system of moderation\
    similar to Dyno.

    Report a bug or ask a question: https://discord.gg/AVzjfpR
    Full documentation and FAQ: http://laggron.red/bettermod.html
    """

    def __init__(self, bot):
        self.bot = bot
        self.data = Config.get_conf(self, 260, force_registration=True)
