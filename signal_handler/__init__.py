import asyncio
import signal

from .signal_handler import SignalHandler


def setup(bot):
    n = SignalHandler(bot)
    bot.add_cog(n)
    bot.loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.ensure_future(n.sigterm_handler()))
