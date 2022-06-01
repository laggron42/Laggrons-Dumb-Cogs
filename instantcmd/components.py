import discord
import logging

from typing import TYPE_CHECKING, Optional, TypeVar, Type, List
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


class OwnerOnlyView(View):
    """
    A view where only bot owners are allowed to interact.
    """

    def __init__(self, bot: "Red", *, timeout: Optional[float] = 180):
        self.bot = bot
        super().__init__(timeout=timeout)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.bot.is_owner(interaction.user)


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
        super().__init__()
        self.code_snippet = code_snippet
        self.set_style()

    def set_style(self):
        if self.code_snippet.enabled:
            self.style = discord.ButtonStyle.secondary
            self.label = "Disable"
            self.emoji = "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"
        else:
            self.style = discord.ButtonStyle.success
            self.label = "Enable"
            self.emoji = "\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        # interaction = self.view.og_interaction
        if self.code_snippet.enabled:
            log.info(f"Code snippet {self.code_snippet} disabled.")
            self.code_snippet.enabled = False
            await self.code_snippet.save()
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
                self.set_style()
                await interaction.response.send_message(
                    "The object was successfully unregistered and will not be loaded again."
                )
                await self.view.edit()
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
                self.code_snippet.enabled = True
                await self.code_snippet.save()
                self.set_style()
                await interaction.response.send_message(
                    "The object was successfully registered and will be loaded on cog load."
                )
                await self.view.edit()


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
        await self.code_snippet.delete()
        try:
            self.code_snippet.unregister()
        except Exception:
            log.error(
                f"Failed to unregister {self.code_snippet} when deletion requested",
                exc_info=True,
            )
            await interaction.response.send_message(
                "An error occured when trying to unregister this object, you can check for "
                "details in your logs.\n"
                "It was still removed and will not be loaded on next cog load."
            )
        else:
            await interaction.response.send_message("Object successfully removed.")
        finally:
            self.view.stop()


class CodeSnippetView(OwnerOnlyView):
    """
    List of buttons for a single code snippet.
    """

    def __init__(self, bot: "Red", interaction: discord.Interaction, code_snippet: T):
        self.code_snippet = code_snippet
        self.og_interaction = interaction
        super().__init__(bot)
        self.add_item(DownloadButton(code_snippet))
        self.add_item(ActivateDeactivateButton(code_snippet))
        self.add_item(DeleteButton(code_snippet))

    async def edit(self):
        # refresh activate/deactivate button
        await self.og_interaction.followup.edit_message("@original", view=self)


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
        await interaction.response.send_message(
            message, view=CodeSnippetView(self.bot, interaction, selected)
        )
