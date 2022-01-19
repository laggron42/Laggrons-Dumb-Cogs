from typing import TYPE_CHECKING

from .blindtest import BlindTest

if TYPE_CHECKING:
    from redbot.core.bot import Red


async def setup(bot: "Red"):
    n = BlindTest(bot)
    await n.initialize()
    bot.add_cog(n)
