import discord
import datetime
import os
import asyncio

from redbot.core import checks
from discord.ext import commands


class Say:
    """
    Speak as if you were the bot
    
    Report a bug or ask a question: https://discord.gg/WsTGeQ
    Full documentation and FAQ: https://github.com/retke/Laggrons-Dumb-Cogs/wiki
    """

    def __init__(self, bot):
        self.bot = bot
        self.interaction = []

    __author__ = "retke (El Laggron)"
    __version__ = "Laggrons-Dumb-Cogs/say release 1.1b"
    __info__ = {
        "bot_version": "3.0.0b9",
        "description": (
            "Speak as if you were the bot.\n"
            "Allow file upload, rift with DM and specific destinations."
        ),
        "hidden": False,
        "install_msg": (
            "Thanks for installing the cog. Please check the wiki "
            "for all informations about the cog.\n"
            "https://github.com/retke/Laggrons-Dumb-Cogs/wiki\n"
            "Join the discord server for questions or suggestions."
            "https://discord.gg/WsTGeQ"
        ),
        "required_cogs": [],
        "requirements": [],
        "short": "Speak as if you were the bot",
        "tags": ["rift", "upload", "interact"],
    }

    async def stop_interaction(self, user):
        self.interaction.remove(user)
        await user.send("Session closed")

    async def on_reaction_add(self, reaction, user):
        if user in self.interaction:
            channel = reaction.message.channel
            if isinstance(channel, discord.DMChannel):
                await self.stop_interaction(user.id)

    async def say(self, ctx, text):

        text = [x for x in text]
        if ctx.message.attachments != []:
            os.system("wget " + ctx.message.attachments[0].url)
            file = discord.File(ctx.message.attachments[0].filename)
        else:
            file = None

        if file is None and text == []:  # no text, no attachment
            await ctx.send_help()
            return

        try:  # we try to get a channel object
            channel = await commands.TextChannelConverter().convert(ctx, text[0])
        except (
            commands.BadArgument,
            IndexError,
        ):  # no channel was given or text is empty (attachment)
            channel = ctx.channel
        else:
            text.remove(text[0])  # we remove the channel from the text

        text = " ".join(text)

        try:
            await channel.send(text, file=file)

        except discord.errors.Forbidden:
            if not ctx.guild.me.permissions_in(channel).send_messages:
                await ctx.send("I am not allowed to send messages in " + channel.mention)
            elif not ctx.guild.me.permissions_in(channel).attach_files:
                await ctx.send("I am not allowed to upload files in " + channel.mention)

        if file is not None:
            os.remove(file.filename)

    @commands.command(name="say")
    @checks.guildowner()
    async def _say(self, ctx, *text: str):
        """Make the bot say what you want.
        If no channel is specified, the message will be send in the current channel."""

        await self.say(ctx, text)

    @commands.command(name="sayd", aliases=["sd"])
    @checks.guildowner()
    async def _saydelete(self, ctx, *text: str):
        """Same as say command, except it deletes your message
        If the message wasn't removed, then I don't have enough permissions"""

        message = None

        try:
            await ctx.message.delete()
        except discord.errors.Forbidden:
            message = await ctx.send("Not enough permissions to delete message")

        await self.say(ctx, text)

        if message is not None:
            await asyncio.sleep(1)
            await message.delete()

    @commands.command(name="interact")
    @checks.guildowner()
    async def _interact(self, ctx, channel: discord.TextChannel = None):
        """Start receiving and sending messages as the bot through DM"""

        u = ctx.author
        if channel is None:
            if isinstance(ctx.channel, discord.DMChannel):
                await ctx.send(
                    "You need to give a channel to enable this in DM. You can give the channel ID too."
                )
                return
            else:
                channel = ctx.channel

        message = await u.send(
            "I will start sending you messages from {}.\n"
            "Just send me any message and I will send it in that channel.\n"
            "React with ❌ on this message to end the session.\n"
            "If no message was send or received in the last 5 minutes, the request will time out and stop.".format(
                channel.mention
            )
        )
        await message.add_reaction("❌")
        self.interaction.append(u)

        while True:

            if u not in self.interaction:
                return

            try:
                message = await self.bot.wait_for("message", timeout=300)
            except asyncio.TimeoutError:
                await u.send("Request timed out. Session closed")
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
                embed.color = message.author.color

                if message.attachments != []:
                    embed.set_image(url=message.attachments[0].url)

                await u.send(embed=embed)

    def __unload(self):
        for user in self.interaction:
            self.bot.loop.create_task(self.stop_interaction(user))
