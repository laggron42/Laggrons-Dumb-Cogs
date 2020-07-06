import discord
import logging

from redbot.core import commands
from redbot.core import checks
from redbot.core.i18n import Translator

from .abc import MixinMeta

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)


class Streams(MixinMeta):
    pass
