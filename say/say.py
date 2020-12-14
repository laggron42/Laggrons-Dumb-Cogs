# Say by retke, aka El Laggron

import discord
import asyncio
import logging

from typing import Optional
from laggron_utils.logging import close_logger, DisabledConsoleOutput

from redbot.core import checks, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.tunnel import Tunnel

log = logging.getLogger("red.laggron.say")
_ = Translator("Say", __file__)
BaseCog = getattr(commands, "Cog", object)

# Red 3.0 backwards compatibility, thanks Sinbad
listener = getattr(commands.Cog, "listener", None)
if listener is None:

    def listener(name=None):
        return lambda x: x


@cog_i18n(_)
class Say(BaseCog):
    """
    Speak as if you were the bot

    Documentation: http://laggron.red/say.html
    """

    def __init__(self, bot):
        self.bot = bot
        self.interaction = []

    __author__ = ["retke (El Laggron)"]
    __version__ = "1.5.0"

    async def say(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel],
        text: str,
        files: list,
        mentions: discord.AllowedMentions = None,
    ):
        if not channel:
            channel = ctx.channel
        if not text and not files:
            await ctx.send_help()
            return

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
            await channel.send(text, files=files, allowed_mentions=mentions)
        except discord.errors.HTTPException as e:
            author = ctx.author
            if not ctx.guild.me.permissions_in(channel).send_messages:
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
    @checks.admin_or_permissions(administrator=True)
    async def _say(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel], *, text: str = ""
    ):
        """
        Make the bot say what you want in the desired channel.

        If no channel is specified, the message will be send in the current channel.
        You can attach some files to upload them to Discord.

        Example usage :
        - `!say #general hello there`
        - `!say owo I have a file` (a file is attached to the command message)
        """

        files = await Tunnel.files_from_attatch(ctx.message)
        await self.say(ctx, channel, text, files)

    @commands.command(name="sayd", aliases=["sd"])
    @checks.admin_or_permissions(administrator=True)
    async def _saydelete(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel], *, text: str = ""
    ):
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

        await self.say(ctx, channel, text, files)

    @commands.command(name="saym", aliases=["sm"])
    @checks.admin_or_permissions(administrator=True)
    async def _saymention(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel], *, text: str = ""
    ):
        """
        Same as say command, except role and mass mentions are enabled.
        """
        message = ctx.message
        channel = channel or ctx.channel
        guild = channel.guild
        files = await Tunnel.files_from_attach(message)
        role_mentions = message.role_mentions
        if not role_mentions and not message.mention_everyone:
            # no mentions, nothing to check
            return await self.say(ctx, channel, text, files)
        no_mention = [x for x in role_mentions if x.mentionable is False]
        if guild.me.guild_permissions.administrator is False:
            if no_mention:
                await ctx.send(
                    _(
                        "I can't mention the following roles: {roles}\nTurn on "
                        "mentions or make me an admin on the server.\n"
                    ).format(roles=", ".join([x.name for x in no_mention]))
                )
                return
            if (
                message.mention_everyone
                and channel.permissions_for(guild.me).mention_everyone is False
            ):
                await ctx.send(_("I don't have the permission to mention everyone."))
                return
        if (
            message.mention_everyone
            and channel.permissions_for(ctx.author).mention_everyone is False
        ):
            await ctx.send(_("You don't have the permission yourself to do mass mentions."))
            return
        if ctx.author.guild_permissions.administrator is False and no_mention:
            await ctx.send(
                _(
                    "You're not allowed to mention the following roles: {roles}\nTurn on "
                    "mentions for that role or be an admin in the server.\n"
                ).format(roles=", ".join([x.name for x in no_mention]))
            )
            return
        await self.say(
            ctx, channel, text, files, mentions=discord.AllowedMentions(everyone=True, roles=True)
        )

    @commands.command(name="interact")
    @checks.admin_or_permissions(administrator=True)
    async def _interact(self, ctx: commands.Context, channel: discord.TextChannel = None):
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
                if message.content.startswith(tuple(await self.bot.get_valid_prefixes())):
                    return
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
                "Documentation: http://laggrons-dumb-cogs.readthedocs.io/\n"
                "Help translating the cog: https://crowdin.com/project/laggrons-dumb-cogs/\n\n"
                "Support my work on Patreon: https://www.patreon.com/retke"
            ).format(self)
        )

    @listener()
    async def on_reaction_add(self, reaction, user):
        if user in self.interaction:
            channel = reaction.message.channel
            if isinstance(channel, discord.DMChannel):
                await self.stop_interaction(user)

    @listener()
    async def on_command_error(self, ctx, error):
        if not isinstance(error, commands.CommandInvokeError):
            return
        if not ctx.command.cog_name == self.__class__.__name__:
            # That error doesn't belong to the cog
            return
        with DisabledConsoleOutput(log):
            log.error(
                f"Exception in command '{ctx.command.qualified_name}'.\n\n",
                exc_info=error.original,
            )

    async def stop_interaction(self, user):
        self.interaction.remove(user)
        await user.send(_("Session closed"))

    def __unload(self):
        self.cog_unload()

    def cog_unload(self):
        log.debug("Unloading cog...")
        for user in self.interaction:
            self.bot.loop.create_task(self.stop_interaction(user))
        close_logger(log)
