__all__ = (
    "InstantcmdException",
    "ExecutionException",
    "UnknownType",
    "InvalidType",
)


class InstantcmdException(Exception):
    """
    Base error for commands raised within a command snippet.
    """

    pass


class ExecutionException(InstantcmdException):
    """
    Failed to execute the code.
    """

    pass


class UnknownType(InstantcmdException):
    """
    The return value's type was not recognized.
    """

    pass


class InvalidType(InstantcmdException):
    """
    The object does not match the associated implementation.
    """

    pass
