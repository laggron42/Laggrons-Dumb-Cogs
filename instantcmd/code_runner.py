import os
import sys
import textwrap

from typing import TypeVar, Type, Dict, Any

from redbot.core import commands

from instantcmd.core import (
    CodeSnippet,
    CommandSnippet,
    ListenerSnippet,
    ExecutionException,
    UnknownType,
)
from instantcmd.core.listener import Listener

T = TypeVar("T")
OBJECT_TYPES_MAPPING = {
    commands.Command: CommandSnippet,
    Listener: ListenerSnippet,
}


# from DEV cog, made by Cog Creators (tekulvw)
def cleanup_code(content):
    """Automatically removes code blocks from the code."""
    # remove ```py\n```
    if content.startswith("```") and content.endswith("```"):
        return "\n".join(content.split("\n")[1:-1])

    # remove `foo`
    return content.strip("` \n")


def get_code_from_str(content: str, env: Dict[str, Any]) -> T:
    """
    Execute a string, and try to get a function from it.
    """
    # The Python code is wrapped inside a function
    to_compile = "def func():\n%s" % textwrap.indent(content, "  ")

    # Setting the instantcmd cog available in path, allowing imports like instantcmd.utils
    sys.path.append(os.path.dirname(__file__))
    try:
        exec(to_compile, env)
    except Exception as e:
        raise ExecutionException("Failed to compile the code") from e
    finally:
        sys.path.remove(os.path.dirname(__file__))

    # Execute and get the return value of the function
    try:
        result = env["func"]()
    except Exception as e:
        raise ExecutionException("Failed to execute the function") from e

    # Function does not have a return value
    if not result:
        raise ExecutionException("Nothing detected. Make sure to return something")
    return result


def find_matching_type(code: T) -> Type[CodeSnippet]:
    for source, dest in OBJECT_TYPES_MAPPING.items():
        if isinstance(code, source):
            return dest
    raise UnknownType(f'The type "{type(code)}" was not recognized. Did you forget a decorator?')
