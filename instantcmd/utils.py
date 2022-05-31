"""
This modules contains utility functions designed to be used within custom commands and listeners.

The instantcmd folder is added to sys.path only when executing the code on load.
"""

from typing import Callable

from instantcmd.core.listener import Listener


def listener(name: str = None):
    """
    A decorator that represents a discord.py listener.
    """

    def decorator(func):
        nonlocal name
        if name is None:
            name = func.__name__
        result = Listener(func, name)
        return result

    return decorator
