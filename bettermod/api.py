import discord
import logging
import inspect

# import yaml

# from datetime import timedelta
from typing import Union, Optional

from redbot.core.modlog import get_modlog_channel as get_red_modlog_channel

# from redbot.core.data_manager import cog_data_path

from . import errors

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

    def _log_call(self, stack):
        """Create a debug log for each BMod API call."""
        try:
            caller = (
                stack[0][3],
                stack[1][0].f_locals["self"].__class__,
                stack[1][0].f_code.co_name,
            )
            if caller[1] != self:
                log.debug(f"API.{caller[0]} called by {caller[1].__name__}.{caller[2]}")
        except Exception:
            # this should not block the action
            pass

    async def get_modlog_channel(
        self, guild: discord.Guild, level: Optional[Union[int, str]] = None
    ):
        """
        Get the BetterMod's modlog channel on the current guild.

        When you call this, the channel is get with the following order:

        #.  Get the modlog channel associated to the type, if provided
        #.  Get the defult modlog channel set with BetterMod
        #.  Get the Red's modlog channel associated to the server

        Arguments
        ---------
        guild: discord.Guild
            The guild you want to get the modlog from.
        level: Optional[Union[int, str]]
            Can be an :py:class:`int` between 1 and 5, a :py:class:`str` (``"all"``
            or ``"report"``) or :py:obj:`None`.

            *   If the argument is omitted (or :py:obj:`None` is provided), the default modlog
                channel will be returned.

            *   If an :py:class:`int` is given, the modlog channel associated to this warning
                level will be returned. If a specific channel was not set for this level, the
                default modlog channel will be returned instead.

            *   If ``"report"`` is given, the channel associated to the reports will be returned.
                If a specific channel was not set for reports, the default modlog channel will
                be returned instead.

            *   If ``"all"`` is returned, a :py:class:`dict` will be returned. It should be built
                like this:

                .. code-block:: JSON

                    {
                        "main"      : 012345678987654321,
                        "report"    : 579084368900053345,
                        "1"         : null,
                        "2"         : null,
                        "3"         : null,
                        "4"         : 478065433996537900,
                        "5"         : 567943553912O46428,
                    }

                A dict with the possible channels is returned, associated with a :py:class:`int`
                corresponding to the channel ID set, or :py:obj:`None` if it was not set.

                For technical reasons, the default channel is actually named ``"main"`` in the dict.

        Returns
        -------
        channel: discord.TextChannel
            The channel requested.
            
            .. note:: It can be :py:obj:`None` if the channel doesn't exist anymore.

        Raises
        ------
        NotFound
            There is no modlog channel set with BetterMod or Red, ask the user to set one.
        """
        self._log_call(inspect.stack())

        # raise errors if the arguments are wrong
        if level:
            msg = (
                "The level must be an int between 1 and 5 ; or a string that "
                'should be "all" or "report"'
            )
            if not isinstance(level, int) and all([x != level for x in ["all", "report"]]):
                raise errors.InvalidLevel(msg)
            elif isinstance(level, int) and not 1 <= level <= 5:
                raise errors.InvalidLevel(msg)

        default_channel = await self.data.guild(guild).channels.main()
        if level:
            channel = await self.data.guild(guild).channels.get_raw(str(level))
        else:
            return default_channel

        if not default_channel and not channel:
            # bettermod default channel doesn't exist, let's try to get Red's one
            try:
                return await get_red_modlog_channel(guild)
            except RuntimeError:
                raise errors.NotFound("No modlog found from BetterMod or Red")

        return self.bot.get_channel(channel if channel else default_channel)
