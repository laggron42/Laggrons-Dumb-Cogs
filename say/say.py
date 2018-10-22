# Say by retke, aka El Laggron

import discord
import os
import asyncio
import sys
import logging

from redbot.core import checks
from redbot.core import Config
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.data_manager import cog_data_path
from redbot.core import commands

from .sentry import Sentry

log = logging.getLogger("laggron.say")
if logging.getLogger("red").isEnabledFor(logging.DEBUG):
    # debug mode enabled
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.WARNING)
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
        self.data = Config.get_conf(self, 260)
        self.data.register_global(enable_sentry=None)
        self.translator = _
        self.sentry = Sentry(log, self.__version__, bot)
        self.interaction = []
        self.cache = cog_data_path(self) / "cache"

    __author__ = "retke (El Laggron)"
    __version__ = "1.4.6"
    __info__ = {
        "bot_version": "3.0.0b14",
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

    def _set_context(self, data: dict):
        """
        Set any extra context information before logging something.
        This is an alias of ``self.sentry.client.extra_context()``

        Arguments
        ---------
        data: dict
            The dictionnary that must appear on Sentry panel
        """
        self.sentry.client.extra_context(data)

    async def download_files(self, message: discord.Message, author: discord.User = None):
        """
        Download all of the attachments linked to a message.

        Arguments
        ---------
        message: discord.Message
            The message to get the attachments.
        author: discord.User
            The user to send a message to in case of a downloading error.
        
        Returns
        -------
        files: list
            Return a :py:class:`list` of :class:`discord.File`
            downloaded in the cog's cache.
        """

        if message.attachments == []:
            return []

        total_bytes = 0
        for attachment in message.attachments:
            total_bytes += attachment.size
        if total_bytes > 8000000:
            await author.send(
                _("The files got removed because they were too big. " "The limit for bots is 8mb.")
            )
            return []

        exit_code = os.system(
            f"wget --verbose --directory-prefix {str(self.cache)} "
            + f"--output-file {str(self.cache)}/wget_log.txt "
            + " ".join([x.url for x in message.attachments])
        )
        files = [discord.File(str(self.cache / x.filename)) for x in message.attachments]
        if exit_code != 0:
            # the file wasn't downloaded correctly
            # let's tell the user what's wrong
            error_message = _("An error occured while downloading the file.\n" "Error code ")
            if exit_code == 1:
                error_message += _("1: `wget` program not found, install it on your machine")
            if exit_code == 3:
                error_message += _("3: File I/O error (write permission)")
            elif exit_code == 4:
                error_message += _("4: Network failure")
            elif exit_code == 5:
                error_message += _("5: SSL verification failure")
            elif exit_code == 7:
                error_message += _("7: Protocol error")
            elif exit_code == 8:
                error_message += _("8: Server issued an error response")
            elif exit_code == 2048:
                error_message += _("2048: Image not found")
            else:
                error_message += _("unknown.")
            # source: https://gist.github.com/cosimo/5747881

            await author.send(error_message)
            with open(str(self.cache / "wget_log.txt"), "r") as log_file:
                log.warning(
                    f"Exception in downloading files. Exit code {exit_code}.\n"
                    f"Full output: {log_file.read()}"
                )
            return []
        return files

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
                except discord.errors.Forbidden as e:
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
                except discord.errors.Forbidden as e:
                    await author.send(
                        _("I am not allowed to upload files in ") + channel.mention,
                        delete_after=15,
                    )
            else:
                log.error(
                    f"Unknown permissions error when sending a message.\n{error_message}",
                    exc_info=e,
                )
        self.clear_cache()

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

        files = await self.download_files(ctx.message, ctx.author)
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
        files = await self.download_files(ctx.message, author)

        try:
            await ctx.message.delete()
        except discord.errors.Forbidden:
            try:
                await ctx.send(_("Not enough permissions to delete messages."), delete_after=2)
            except discord.errors.Forbidden as e:
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
                        "You need to give a channel to enable this in DM. You can give the channel ID too."
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
                if message.attachments != []:
                    os.system("wget " + message.attachments[0].url)
                    await channel.send(
                        message.content, file=discord.File(message.attachments[0].filename)
                    )
                    os.remove(message.attachments[0].filename)

                else:
                    await channel.send(message.content)

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
    async def sayinfo(self, ctx, sentry: str = None):
        """
        Get informations about the cog.

        Type `sentry` after your command to modify its status.
        """
        current_status = await self.data.enable_sentry()
        status = lambda x: _("enable") if x else _("disable")

        if sentry is not None and "sentry" in sentry:

            def check(message):
                return message.author == ctx.author and message.channel == ctx.author.dm_channel

            await ctx.send(
                _(
                    "You're about to {} error logging. Are you sure you want to do this? Type `yes` to confirm."
                ).format(not current_status)
            )
            try:
                response = await self.bot.wait_for("message", timeout=60, check=check)
            except asyncio.TimeoutError:
                await ctx.send(_("Request timed out."))
            else:
                if "yes" in response.content.lower():
                    await self.data.enable_sentry.set(not current_status)
                    if not current_status:
                        # now enabled
                        await ctx.send(
                            _(
                                "Upcoming errors will be reported automatically for a faster fix. "
                                "Thank you for helping me with the development process!"
                            )
                        )
                        await self.sentry.enable()
                    else:
                        # disabled
                        await ctx.send(_("Error logging has been disabled."))
                        await self.sentry.disable()
                    return

        message = _(
            "Laggron's Dumb Cogs V3 - say\n\n"
            "Version: {0.__version__}\n"
            "Author: {0.__author__}\n"
            "Sentry error reporting: {1}d (type `{2}sayinfo sentry` to change this)\n\n"
            "Github repository: https://github.com/retke/Laggrons-Dumb-Cogs/tree/v3\n"
            "Discord server: https://discord.gg/AVzjfpR\n"
            "Documentation: http://laggrons-dumb-cogs.readthedocs.io/"
        ).format(self, status(current_status), ctx.prefix)
        await ctx.send(message)

    async def on_reaction_add(self, reaction, user):
        if user in self.interaction:
            channel = reaction.message.channel
            if isinstance(channel, discord.DMChannel):
                await self.stop_interaction(user)

    async def on_error(self, event, *args, **kwargs):
        error = sys.exc_info()
        log.error(f"Exception in {event}.\nArgs: {args}\nKwargs: {kwargs}\n\n", exc_info=error)

    async def on_command_error(self, ctx, error):
        if not isinstance(error, commands.CommandInvokeError):
            return
        if not ctx.command.cog_name == self.__class__.__name__:
            # That error doesn't belong to the cog
            return
        messages = "\n".join(
            [
                f"{x.author} %bot%: {x.content}".replace("%bot%", "(Bot)" if x.author.bot else "")
                for x in await ctx.history(limit=5, reverse=True).flatten()
            ]
        )
        log.propagate = False  # let's remove console output for this since Red already handle this
        context = {
            "command": {
                "invoked": f"{ctx.author} (ID: {ctx.author.id})",
                "command": f"{ctx.command.name} (cog: {ctx.cog})",
            }
        }
        if ctx.guild:
            context["guild"] = f"{ctx.guild.name} (ID: {ctx.guild.id})"
        self._set_context(context)
        log.error(
            f"Exception in command '{ctx.command.qualified_name}'.\n\n"
            f"Myself: {ctx.me}\n"
            f"Last 5 messages:\n\n{messages}\n\n",
            exc_info=error.original,
        )
        log.propagate = True  # re-enable console output for warnings
        self._set_context({})  # remove context for future logs

    async def stop_interaction(self, user):
        self.interaction.remove(user)
        await user.send(_("Session closed"))

    def clear_cache(self):
        for file in self.cache.iterdir():
            os.remove(str(file.absolute()))

    def __unload(self):
        for user in self.interaction:
            self.bot.loop.create_task(self.stop_interaction(user))
        self.clear_cache()
        self.sentry.disable()
