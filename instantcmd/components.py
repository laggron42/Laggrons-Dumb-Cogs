import discord
import logging

from typing import TYPE_CHECKING, TypeVar, Type, List
from discord.ui import Select, Button, View
from redbot.core.utils.chat_formatting import text_to_file

from instantcmd.core import CodeSnippet

if TYPE_CHECKING:
    from redbot.core.bot import Red

log = logging.getLogger("laggron.instantcmd.components")
T = TypeVar("T", bound=CodeSnippet)


def char_limit(text: str, limit: int) -> str:
    if len(text) > limit:
        return text[: limit - 3] + "..."
    else:
        return text


class DownloadButton(Button):
    """
    A button to download the source file.
    """

    def __init__(self, code_snippet: T):
        self.code_snippet = code_snippet
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Download source file",
            emoji="\N{FLOPPY DISK}",
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.channel.permissions_for(interaction.guild.me).attach_files:
            await interaction.response.send_message("I lack the permission to upload files.")
        else:
            await interaction.response.send_message(
                f"Here is the content of your code snippet.",
                file=text_to_file(self.code_snippet.source, filename=f"{self.code_snippet}.py"),
            )
            log.debug(f"File download of {self.code_snippet} requested and uploaded.")


class ActivateDeactivateButton(Button):
    """
    A button to activate or deactivate the code snippet.
    """

    def __init__(self, code_snippet: T):
        self.code_snippet = code_snippet
        if code_snippet.enabled:
            super().__init__(
                style=discord.ButtonStyle.secondary,
                label="Disable",
                emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
            )
        else:
            super().__init__(
                style=discord.ButtonStyle.success,
                label="Enable",
                emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}",
            )

    async def callback(self, interaction: discord.Interaction):
        if self.code_snippet.enabled:
            log.info(f"Code snippet {self.code_snippet} disabled.")
            self.code_snippet.enabled = False
            # TODO: save
            try:
                self.code_snippet.unregister()
            except Exception:
                log.error(
                    f"Failed to unregister {self.code_snippet} when deactivation requested",
                    exc_info=True,
                )
                await interaction.response.send_message(
                    "An error occured when trying to unregister this object, you can check for "
                    "details in your logs.\n"
                    "It is still deactivated and will not be loaded on next cog load."
                )
            else:
                await interaction.response.send_message(
                    "The object was successfully unregistered and will not be loaded again."
                )
        else:
            try:
                self.code_snippet.register()
            except Exception:
                log.error(
                    f"Failed to register {self.code_snippet} when activation requested",
                    exc_info=True,
                )
                await interaction.response.send_message(
                    "An error occured when trying to register this object, you can check for "
                    "details in your logs.\n"
                    "It is still deactivated, you can try to activate it again."
                )
            else:
                log.info(f"Code snippet {self.code_snippet} enabled.")
                # TODO: save
                self.code_snippet.enabled = True
                await interaction.response.send_message(
                    "The object was successfully registered and will be loaded on cog load."
                )


class DeleteButton(Button):
    """
    A button to completly suppress an object.
    """

    def __init__(self, code_snippet: T):
        self.code_snippet = code_snippet
        super().__init__(
            style=discord.ButtonStyle.danger,
            label="Delete",
            emoji="\N{OCTAGONAL SIGN}",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Hmm nope that's staying")
        # TODO: actually delete lol


class CodeSnippetView(View):
    """
    List of buttons for a single code snippet.
    """

    def __init__(self, bot: "Red", code_snippet: T):
        self.bot = bot
        super().__init__()
        self.add_item(DownloadButton(code_snippet))
        self.add_item(ActivateDeactivateButton(code_snippet))
        self.add_item(DeleteButton(code_snippet))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.bot.is_owner(interaction.user)


class CodeSnippetsList(Select):
    """
    A list of items for a specific type of code snippet.
    """

    def __init__(self, bot: "Red", type: Type[T], code_snippets: List[T]):
        self.bot = bot
        self.snippet_type = type
        self.code_snippets = code_snippets

        placeholder = f"List of {type.name} objects"
        objects: List[discord.SelectOption] = []

        # TODO: Support more than 25 items!
        for i, code_snippet in enumerate(code_snippets[:25]):
            lines = code_snippet.source.count("\n") + 1
            value = f"{lines} lines of code"
            if code_snippet.verbose_name != str(code_snippet):
                value += f" • {code_snippet.description}"
            objects.append(
                discord.SelectOption(
                    label=char_limit(str(code_snippet), 25),
                    description=char_limit(value, 50),
                    value=str(i),
                )
            )
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=objects)

    async def callback(self, interaction: discord.Interaction):
        selected = self.code_snippets[int(self.values[0])]
        message = f"__{selected.name} `{selected}`__"
        if selected.verbose_name != str(selected):
            message += f" ({selected.description})"
        message += "\n\n" + next(selected.get_formatted_code())
        await interaction.response.send_message(message, view=CodeSnippetView(self.bot, selected))
