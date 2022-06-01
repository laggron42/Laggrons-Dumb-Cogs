"""
This modules contains utility functions designed to be used within custom commands and listeners.

The instantcmd folder is added to sys.path only when executing the code on load.
"""

from instantcmd.core.listener import Listener
from instantcmd.core.dev_env_value import DevEnv


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


def dev_env_value(name: str = None):
    """
    A decorator that represents a dev env value for Red.
    """

    def decorator(func):
        nonlocal name
        if name is None:
            name = func.__name__
        return DevEnv(func, name)

    return decorator
