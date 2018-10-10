import discord
import logging
import yaml

from datetime import timedelta
from typing import Union, Optional

from redbot.core.modlog import get_modlog_channel
from redbot.core.data_manager import cog_data_path

from .errors import *

log = logging.getLogger("laggron.bettermod")
if logging.getLogger("red").isEnabledFor(logging.DEBUG):
    # debug mode enabled
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.WARNING)


class API:
    """
    Interact with BetterMod from your cog.

    To import the cog and use the functions, type this in your code:

    .. code-block:: python

        bettermod = bot.get_cog('BetterMod').api

    .. warning:: If ``bettermod`` is :py:obj:`None`, the cog is
      not loaded/installed. You won't be able to interact with
      the API at this point.

    .. tip:: You can get the cog version by doing this

        .. code-block:: python

            version = bot.get_cog('BetterMod').__version__
    """

    def __init__(self, bot, config):
        self.bot = bot
        self.data = config
