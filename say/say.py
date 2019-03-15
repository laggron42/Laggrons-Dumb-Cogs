# Say by retke, aka El Laggron

import discord
import asyncio
import os
import logging

from redbot.core import checks, commands
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.tunnel import Tunnel

log = logging.getLogger("laggron.say")
log.setLevel(logging.DEBUG)

_ = Translator("Say", __file__)
BaseCog = getattr(commands, "Cog", object)


@cog_i18n(_)
class Say(BaseCog):
    """
    Speak as if you were the bot

    Report a bug or ask a question: https://discord.gg/AVzjfpR
    Full documentation and FAQ: http://laggrons-dumb-cogs.readthedocs.io/say.html
    """

    def __init__(self, bot):
        self.bot = bot
        self.interaction = []
        self._init_logger()

    __author__ = ["retke (El Laggron)"]
    __version__ = "1.4.8"
    __info__ = {
        "bot_version": [3, 0, 0],
        "description": (
            "Speak as the bot through multiple options.\n"
            "Allow file upload, rift in DM and specific destinations."
        ),
        "hidden": False,
        "install_msg": (
            "Thank you for installing the say cog. Please check the wiki "
            "for all informations about the cog.\n"
            "https://laggrons-dumb-cogs.readthedocs.io/say.html\n\n"
            "Type `[p]help Say` for a quick overview of the commands."
        ),
        "required_cogs": [],
        "requirements": [],
        "short": "Speak as the bot through multiple options.",
        "tags": ["rift", "upload", "interact"],
    }

    def _init_logger(self):
        log_format = logging.Formatter(
            f"%(asctime)s %(levelname)s {self.__class__.__name__}: %(message)s",
            datefmt="[%d/%m/%Y %H:%M]",
        )
        # logging to a log file
        # file is automatically created by the module, if the parent foler exists
        cog_path = cog_data_path(self)
        if cog_path.exists():
            log_path = cog_path / f"{os.path.basename(__file__)[:-3]}.log"
            file_handler = logging.FileHandler(log_path)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(log_format)
            log.addHandler(file_handler)

        # stdout stuff
        stdout_handler = logging.StreamHandler()
        stdout_handler.setFormatter(log_format)
        # if --debug flag is passed, we also set our debugger on debug mode
        if logging.getLogger("red").isEnabledFor(logging.DEBUG):
            stdout_handler.setLevel(logging.DEBUG)
        else:
            stdout_handler.setLevel(logging.INFO)
        log.addHandler(stdout_handler)
        self.stdout_handler = stdout_handler

    async def say(self, ctx, text, files):

        if text == "":  # no text, maybe attachment
            potential_channel = ""
        else:
            potential_channel = text.split()[0]  # first word of the text

        if files == [] and text == "":
            # no text, no attachment, nothing to send
            await ctx.send_help()
            return

        # we try to get a channel object
        try:
            channel = await commands.TextChannelConverter().convert(ctx, potential_channel)
        except (commands.BadArgument, IndexError):
            # no channel was given or text is empty (attachment)
            channel = ctx.channel
        else:
            text = text.replace(potential_channel, "")  # we remove the channel from the text

        # preparing context info in case of an error
        if files != []:
            error_message = (
                "Has files: yes\n"
                f"Number of files: {len(files)}\n"
                f"Files URL: " + ", ".join([x.url for x in ctx.message.attachments])
            )
        else:
            error_message = "Has files: no"

        # sending the message
        try:
            await channel.send(text, files=files)
        except discord.errors.Forbidden as e:
            if not ctx.guild.me.permissions_in(channel).send_messages:
                author = ctx.author
                try:
                    await ctx.send(
                        _("I am not allowed to send messages in ") + channel.mention,
                        delete_after=2,
                    )
                except discord.errors.Forbidden:
                    await author.send(
                        _("I am not allowed to send messages in ") + channel.mention,
                        delete_after=15,
                    )
                    # If this fails then fuck the command author
            elif not ctx.guild.me.permissions_in(channel).attach_files:
                try:
                    await ctx.send(
                        _("I am not allowed to upload files in ") + channel.mention, delete_after=2
                    )
                except discord.errors.Forbidden:
                    await author.send(
                        _("I am not allowed to upload files in ") + channel.mention,
                        delete_after=15,
                    )
            else:
                log.error(
                    f"Unknown permissions error when sending a message.\n{error_message}",
                    exc_info=e,
                )

    @commands.command(name="say")
    @checks.guildowner()
    async def _say(self, ctx, *, text: str = ""):
        """
        Make the bot say what you want in the desired channel.

        If no channel is specified, the message will be send in the current channel.
        You can attach some files to upload them to Discord.

        Example usage :
        - `!say #general hello there`
        - `!say owo I have a file` (a file is attached to the command message)
        """

        files = await Tunnel.files_from_attatch(ctx.message)
        await self.say(ctx, text, files)

    @commands.command(name="sayd", aliases=["sd"])
    @checks.guildowner()
    async def _saydelete(self, ctx, *, text: str = ""):
        """
        Same as say command, except it deletes your message.

        If the message wasn't removed, then I don't have enough permissions.
        """

        # download the files BEFORE deleting the message
        author = ctx.author
        files = await Tunnel.files_from_attatch(ctx.message)

        try:
            await ctx.message.delete()
        except discord.errors.Forbidden:
            try:
                await ctx.send(_("Not enough permissions to delete messages."), delete_after=2)
            except discord.errors.Forbidden:
                await author.send(_("Not enough permissions to delete messages."), delete_after=15)

        await self.say(ctx, text, files)

    @commands.command(name="interact")
    @checks.guildowner()
    async def _interact(self, ctx, channel: discord.TextChannel = None):
        """Start receiving and sending messages as the bot through DM"""

        u = ctx.author
        if channel is None:
            if isinstance(ctx.channel, discord.DMChannel):
                await ctx.send(
                    _(
                        "You need to give a channel to enable this in DM. You can "
                        "give the channel ID too."
                    )
                )
                return
            else:
                channel = ctx.channel

        if u in self.interaction:
            await ctx.send(_("A session is already running."))
            return

        message = await u.send(
            _(
                "I will start sending you messages from {0}.\n"
                "Just send me any message and I will send it in that channel.\n"
                "React with ❌ on this message to end the session.\n"
                "If no message was send or received in the last 5 minutes, "
                "the request will time out and stop."
            ).format(channel.mention)
        )
        await message.add_reaction("❌")
        self.interaction.append(u)

        while True:

            if u not in self.interaction:
                return

            try:
                message = await self.bot.wait_for("message", timeout=300)
            except asyncio.TimeoutError:
                await u.send(_("Request timed out. Session closed"))
                self.interaction.remove(u)
                return

            if message.author == u and isinstance(message.channel, discord.DMChannel):
                files = await Tunnel.files_from_attatch(message)
                await channel.send(message.content, files=files)
            elif (
                message.channel != channel
                or message.author == channel.guild.me
                or message.author == u
            ):
                pass

            else:
                embed = discord.Embed()
                embed.set_author(
                    name="{} | {}".format(str(message.author), message.author.id),
                    icon_url=message.author.avatar_url,
                )
                embed.set_footer(text=message.created_at.strftime("%d %b %Y %H:%M"))
                embed.description = message.content
                embed.colour = message.author.color

                if message.attachments != []:
                    embed.set_image(url=message.attachments[0].url)

                await u.send(embed=embed)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def sayinfo(self, ctx):
        """
        Get informations about the cog.
        """
        await ctx.send(
            _(
                "Laggron's Dumb Cogs V3 - say\n\n"
                "Version: {0.__version__}\n"
                "Author: {0.__author__}\n"
                "Github repository: https://github.com/retke/Laggrons-Dumb-Cogs/tree/v3\n"
                "Discord server: https://discord.gg/AVzjfpR\n"
                "Documentation: http://laggrons-dumb-cogs.readthedocs.io/\n\n"
                "Support my work on Patreon: https://www.patreon.com/retke"
            ).format(self)
        )

    async def on_reaction_add(self, reaction, user):
        if user in self.interaction:
            channel = reaction.message.channel
            if isinstance(channel, discord.DMChannel):
                await self.stop_interaction(user)

    async def on_command_error(self, ctx, error):
        if not isinstance(error, commands.CommandInvokeError):
            return
        if not ctx.command.cog_name == self.__class__.__name__:
            # That error doesn't belong to the cog
            return
        log.removeHandler(self.stdout_handler)  # remove console output since red also handle this
        log.error(
            f"Exception in command '{ctx.command.qualified_name}'.\n\n", exc_info=error.original
        )
        log.addHandler(self.stdout_handler)  # re-enable console output for warnings

    async def stop_interaction(self, user):
        self.interaction.remove(user)
        await user.send(_("Session closed"))

    def __unload(self):
        log.debug("Unloading cog...")
        for user in self.interaction:
            self.bot.loop.create_task(self.stop_interaction(user))
        log.handlers = []
