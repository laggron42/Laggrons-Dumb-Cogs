"""
Custom error handling used for the cog and the API.

If you need to prevent and exception, do it like this:

.. code-block:: python

    bettermod = bot.get_cog('BetterMod')
    api = cog.api
    errors = cog.errors

    try:
        await api.warn(5, user, "my random reason")
    except discord.errors.Forbidden:
        print("Missing permissions")
    except errors.InvalidLevel:
        print("Wrong warning level")
    except:
        # occurs for any exception
        print("Fatal error")
    else:
        # executed if the try succeeded
        print("All good")
    finally:
        # always executed
        print("End of function")
"""

import logging

log = logging.getLogger("laggron.bettermod")
if logging.getLogger("red").isEnabledFor(logging.DEBUG):
    # debug mode enabled
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.WARNING)

__all__ = ["InvalidLevel", "NotFound"]


class InvalidLevel(Exception):
    """
    The level argument for :func:`~bettermod.api.warn` is wrong.
    It must be between 1 and 5.
    """

    def __init__(self, exception):
        log.debug(f"API error: InvalidLevel\n{exception}\n")


class NotFound(Exception):
    """
    Something was not found in the BetterMod data. The meaning of this exception
    depends of what you called, it may be a missing BetterMod channel.
    """

    def __init__(self, exception):
        log.debug(f"API error: NotFound\n{exception}\n")


class MissingMuteRole(Exception):
    """
    You requested a mute warn but the mute role doesn't exist. Call
    :func:`~bettermod.api.API.maybe_create_role` to fix this.
    """

    def __init__(self, exception):
        log.debug(f"API error: MissingMuteRole\n{exception}\n")


class BadArgument(Exception):
    """
    The arguments provided for your request are wrong, check the types.
    """

    def __init__(self, exception):
        log.debug(f"API error: NotFound\n{exception}\n")


class MissingPermissions(Exception):
    """
    The bot lacks a permission to do an action.

    This is raised instead of :class:`discord.errors.Forbidden` to prevent a useless
    API call, we check the bot's permissions before calling.
    """

    def __init__(self, exception):
        log.debug(f"API error: MissingPermissions\n{exception}\n")


class MemberTooHigh(Exception):
    """
    The member to take action on is above the bot in the guild's role hierarchy.

    To fix this, set the bot's top role **above** the member's top role.
    For more informations about Discord Permissions, read this:\
    `https://support.discordapp.com/hc/en-us/articles/206029707`_

    This is raised instead of :class:`discord.errors.Forbidden` to prevent a useless
    API call, we check the bot's permissions before calling.
    """

    def __init__(self, exception):
        log.debug(f"API error: MemberTooHigh\n{exception}\n")
