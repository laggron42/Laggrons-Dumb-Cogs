"""
This modules contains utility functions designed to be used within custom commands and listeners.

The instantcmd folder is added to sys.path only when executing the code on load.
"""

from typing import Callable


class Listener:
    """
    A class representing a discord.py listener.
    """

    def __init__(self, function: Callable, name: str):
        self.func = function
        self.name = name
        self.id = id(function)


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
