# Say by retke, aka El Laggron

import discord
import asyncio
import logging
import re

from discord import app_commands

from typing import TYPE_CHECKING, Optional
from laggron_utils import close_logger

from redbot.core import checks, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.tunnel import Tunnel

if TYPE_CHECKING:
    from redbot.core.bot import Red

log = logging.getLogger("red.laggron.say")
_ = Translator("Say", __file__)


ROLE_MENTION_REGEX = re.compile(r"<@&(?P<id>[0-9]{17,19})>")


@cog_i18n(_)
class Say(commands.Cog):
    """
    Speak as if you were the bot

    Documentation: http://laggron.red/say.html
    """

    def __init__(self, bot: "Red"):
        self.bot = bot
        self.interaction = []

    __author__ = ["retke (El Laggron)"]
    __version__ = "2.0.1"

    async def say(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel],
        text: str,
        files: list,
        mentions: discord.AllowedMentions = None,
        delete: int = None,
    ):
        if not channel:
            channel = ctx.channel
        if not text and not files:
            await ctx.send_help()
            return

        author = ctx.author
        guild = channel.guild

        # checking perms
        if guild and not channel.permissions_for(guild.me).send_messages:
            if channel != ctx.channel:
                await ctx.send(
                    _("I am not allowed to send messages in ") + channel.mention,
                    delete_after=2,
                )
            else:
                await author.send(_("I am not allowed to send messages in ") + channel.mention)
                # If this fails then fuck the command author
            return

        if files and not channel.permissions_for(guild.me).attach_files:
            try:
                await ctx.send(
                    _("I am not allowed to upload files in ") + channel.mention, delete_after=2
                )
            except discord.errors.Forbidden:
                await author.send(
                    _("I am not allowed to upload files in ") + channel.mention,
                    delete_after=15,
                )
            return

        try:
            await channel.send(text, files=files, allowed_mentions=mentions, delete_after=delete)
        except discord.errors.HTTPException:
            try:
                await ctx.send("An error occured when sending the message.")
            except discord.errors.HTTPException:
                pass
            log.error("Failed to send message.", exc_info=True)

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

    @commands.command(name="sayad")
    @checks.admin_or_permissions(administrator=True)
    async def _sayautodelete(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel],
        delete_delay: int,
        *,
        text: str = "",
    ):
        """
        Same as say command, except it deletes the said message after a set number of seconds.
        """

        files = await Tunnel.files_from_attatch(ctx.message)
        await self.say(ctx, channel, text, files, delete=delete_delay)

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

        role_mentions = list(
            filter(
                None,
                (ctx.guild.get_role(int(x)) for x in ROLE_MENTION_REGEX.findall(message.content)),
            )
        )
        mention_everyone = "@everyone" in message.content or "@here" in message.content
        if not role_mentions and not mention_everyone:
            # no mentions, nothing to check
            return await self.say(ctx, channel, text, files)
        non_mentionable_roles = [x for x in role_mentions if x.mentionable is False]

        if not channel.permissions_for(guild.me).mention_everyone:
            if non_mentionable_roles:
                await ctx.send(
                    _(
                        "I can't mention the following roles: {roles}\nTurn on "
                        "mentions or grant me the correct permissions.\n"
                    ).format(roles=", ".join([x.name for x in non_mentionable_roles]))
                )
                return
            if mention_everyone:
                await ctx.send(_("I don't have the permission to mention everyone."))
                return
        if not channel.permissions_for(ctx.author).mention_everyone:
            if non_mentionable_roles:
                await ctx.send(
                    _(
                        "You're not allowed to mention the following roles: {roles}\nTurn on "
                        "mentions for that role or have the correct permissions.\n"
                    ).format(roles=", ".join([x.name for x in non_mentionable_roles]))
                )
                return
            if mention_everyone:
                await ctx.send(_("You don't have the permission yourself to do mass mentions."))
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
                    icon_url=message.author.avatar.url,
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
                "Discord server: https://discord.gg/GET4DVk\n"
                "Documentation: http://laggrons-dumb-cogs.readthedocs.io/\n"
                "Help translating the cog: https://crowdin.com/project/laggrons-dumb-cogs/\n\n"
                "Support my work on Patreon: https://www.patreon.com/retke"
            ).format(self)
        )

    # ----- Slash commands -----
    @app_commands.command(name="say", description="Make the bot send a message")
    @app_commands.describe(
        message="The content of the message you want to send",
        channel="The channel where you want to send the message (default to current)",
        delete_delay="Delete the message sent after X seconds",
        mentions="Allow @everyone, @here and role mentions in your message",
        file="A file you want to attach to the message sent (message content becomes optional)",
    )
    @app_commands.default_permissions()
    @app_commands.guild_only()
    async def slash_say(
        self,
        interaction: discord.Interaction,
        message: Optional[str] = "",
        channel: Optional[discord.TextChannel] = None,
        delete_delay: Optional[int] = None,
        mentions: Optional[bool] = False,
        file: Optional[discord.Attachment] = None,
    ):
        guild = interaction.guild
        channel = channel or interaction.channel

        if not message and not file:
            await interaction.response.send_message(
                _("You cannot send an empty message."), ephemeral=True
            )
            return

        if not channel.permissions_for(guild.me).send_messages:
            await interaction.response.send_message(
                _("I don't have the permission to send messages there."), ephemeral=True
            )
            return
        if file and not channel.permissions_for(guild.me).attach_files:
            await interaction.response.send_message(
                _("I don't have the permission to upload files there."), ephemeral=True
            )
            return

        if mentions:
            mentions = discord.AllowedMentions(
                everyone=interaction.user.guild_permissions.mention_everyone,
                roles=interaction.user.guild_permissions.mention_everyone
                or [x for x in interaction.guild.roles if x.mentionable],
            )
        else:
            mentions = None

        file = await file.to_file(use_cached=True) if file else None
        try:
            await channel.send(message, file=file, delete_after=delete_delay)
        except discord.HTTPException:
            await interaction.response.send_message(
                _("An error occured when sending the message."), ephemeral=True
            )
            log.error(
                f"Cannot send message in {channel.name} ({channel.id}) requested by "
                f"{interaction.user} ({interaction.user.id}). "
                f"Command: {interaction.message.content}",
                exc_info=True,
            )
        else:
            # acknowledge the command, but don't actually send an additional message
            await interaction.response.defer(ephemeral=False)
            await interaction.followup.delete_message("@original")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user in self.interaction:
            channel = reaction.message.channel
            if isinstance(channel, discord.DMChannel):
                await self.stop_interaction(user)

    async def stop_interaction(self, user):
        self.interaction.remove(user)
        await user.send(_("Session closed"))

    async def cog_unload(self):
        log.debug("Unloading cog...")
        for user in self.interaction:
            await self.stop_interaction(user)
        close_logger(log)
