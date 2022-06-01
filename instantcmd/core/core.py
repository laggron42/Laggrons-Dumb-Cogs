from typing import TYPE_CHECKING, Generic, TypeVar, Iterator

from redbot.core.utils.chat_formatting import box, pagify

if TYPE_CHECKING:
    from redbot.core.bot import Red
    from redbot.core import Config

T = TypeVar("T")
MAX_CHARS_PER_PAGE = 1900


class CodeSnippet(Generic[T]):
    """
    Represents a code snippet sent from Discord.
    This class should be subclassed to represent an actual object to implement.

    Attributes
    ----------
    enbaled: bool
        If this code is enabled or not.
    registered: bool
        If this code is currently registered on the bot.
    name: str
        The verbose name of the current subclass.

    Parameters
    ----------
    bot: ~redbot.core.bot.Red
        The bot object. Used for many functions that require the bot object to register stuff.
    value: T
        The value contained by an instance of this class.
    source: str
        Actual source code of this function.
    """

    name: str = "command"

    def __init__(self, bot: "Red", config: "Config", value: T, source: str):
        self.bot = bot
        self.data = config
        self.value = value
        self.source = source
        self.enabled: bool = True
        self.registered: bool = False

    @classmethod
    def from_saved_data(cls, bot: "Red", config: "Config", value: T, data: dict):
        code_snippet = cls(bot, config, value, data["code"])
        code_snippet.enabled = data["enabled"]
        return code_snippet

    async def save(self):
        await self.data.custom("CODE_SNIPPET", self.name, str(self)).set_raw(
            value={"code": self.source, "enabled": self.enabled}
        )

    async def delete(self):
        await self.data.custom("CODE_SNIPPET", self.name).clear_raw(str(self))

    def get_formatted_code(self) -> Iterator[str]:
        """
        Get a string representing the code, formatted for Discord and pagified.
        """
        for page in pagify(
            text=self.source,
            delims=["\n\n", "\n"],
            priority=True,
            page_length=MAX_CHARS_PER_PAGE,
        ):
            yield box(page, lang="py")

    def __str__(self) -> str:
        """
        Return the instance's function name.
        """
        raise NotImplementedError

    @property
    def verbose_name(self) -> str:
        """
        Return the instance's display name.
        """
        raise NotImplementedError

    @property
    def description(self) -> str:
        """
        Return a more detailed description of this object.
        """
        return str(self)

    def register(self):
        """
        Register the object to the bot.

        Varies on the implementation.
        """
        raise NotImplementedError

    def unregister(self):
        """
        Removes the object from the bot.

        Varies on the implementation.
        """
        raise NotImplementedError
