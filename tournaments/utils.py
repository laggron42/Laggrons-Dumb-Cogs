import asyncio
import logging

from achallonge import ChallongeException

from redbot.core import commands
from redbot.core.i18n import Translator

from .objects import Tournament

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)

COG_NAME = "Tournaments"


def credentials_check(command: commands.Command) -> commands.Command:
    """
    Verifies if context guild has challonge username and API key setup.
    """

    async def hook(cog, ctx: commands.Context):
        credentials = await cog.data.guild(ctx.guild).credentials()
        if any([x is None for x in credentials.values()]):
            raise commands.UserFeedbackCheckFailure(
                _(
                    "You need to set your Challonge credentials before using this "
                    "command! Use `{prefix}help challongeset` for more info."
                ).format(prefix=ctx.clean_prefix)
            )

    command.before_invoke(hook)
    return command


def only_phase(*allowed_phases):
    """
    Verifies if the current phrase of the tournament on the guild is in the list.
    """

    def wrapper(command: commands.Command) -> commands.Command:
        async def hook(cog, ctx: commands.Context):
            try:
                tournament = cog.tournaments[ctx.guild.id]
            except KeyError:
                raise commands.UserFeedbackCheckFailure(_("There's no ongoing tournament."))
            if tournament.phase not in allowed_phases:
                raise commands.UserFeedbackCheckFailure(
                    _("This command cannot be executed right now.")
                )

        command.before_invoke(hook)
        return command

    return wrapper


def mod_or_to():
    async def check(ctx: commands.Context):
        if ctx.author.id == ctx.guild.owner.id:
            return True
        if ctx.author.guild_permissions.administrator:
            return True
        if await ctx.bot.is_mod(ctx.author):
            return True
        if await ctx.bot.is_owner(ctx.author):
            return True
        try:
            tournament: Tournament = ctx.cog.tournaments[ctx.guild.id]
        except KeyError:
            return False
        if tournament.to_role in ctx.author.roles:
            return True
        return False

    return commands.check(check)


async def async_http_retry(coro):
    """
    Retries the operation in case of a timeout.

    This function is made by Wonderfall.
    https://github.com/Wonderfall/ATOS/blob/cac2c561c8f1ce23277765bcb43cd6421129d8a1/utils/http_retry.py#L6
    """
    for retry in range(1):
        try:
            return await coro
        except ChallongeException as e:
            log.error(f"Challonge exception. coro: {coro.__name__}", exc_info=e)
            if "504" in str(e):
                await asyncio.sleep(1 + retry)
            else:
                raise
        except asyncio.exceptions.TimeoutError as e:
            log.warn(f"Challonge timeout. coro: {coro}", exc_info=e)
            continue
    else:
        raise ChallongeException(f"Tried '{coro.__name__}' several times without success")
