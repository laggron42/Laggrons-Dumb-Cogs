# Say by retke, aka El Laggron

import discord
import datetime
import os
import asyncio

from redbot.core import checks
from redbot.core.data_manager import cog_data_path
from discord.ext import commands


class Say:
    """
    Speak as if you were the bot
    
    Report a bug or ask a question: https://discord.gg/WsTGeQ
    Full documentation and FAQ: http://laggrons-dumb-cogs.readthedocs.io/say.html
    """

    def __init__(self, bot):
        self.bot = bot
        self.interaction = []
        self.cache = cog_data_path(self) / "cache"

    __author__ = "retke (El Laggron)"
    __version__ = "Laggrons-Dumb-Cogs/say release 1.3"
    __info__ = {
        "bot_version": "3.0.0b9",
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

    async def stop_interaction(self, user):
        self.interaction.remove(user)
        await user.send("Session closed")

    async def say(self, ctx, text):
        """
        Send text in a channel with the attachments.
        If a channel is found as the first word, it will be send
        in that channel. This needs a context.

        Arguments
        ---------
        text: str
            The text to send.
        ctx: ~commands.Context
            The context got from a command. Can be generated with
            `~commands.Bot.get_context`.
        """

        self.clear_cache()  # let's make sure cache is clear
        if text == '':  # no text, maybe attachment
            potential_channel = ''
        else:
            potential_channel = text.split()[0]  # first word of the text

        if ctx.message.attachments != []:
            # there is an attachment

            exit_code = os.system(
                "wget --quiet --directory-prefix " + str(self.cache)
                + " --output-file " + str(self.cache / "wget_log.txt")
                + " "
                + " ".join([x.url for x in ctx.message.attachments])
            )
            files = [discord.File(str(self.cache / x.filename)) for x in ctx.message.attachments]
            if exit_code != 0:
                # the file wasn't downloaded correctly
                # let's tell the user what's wrong
                error_message = "An error occured while downloading the file.\n" "Error code "
                if exit_code == 3:
                    error_message += "3: File I/O error (write permission)"
                elif exit_code == 4:
                    error_message += "4: Network failure"
                elif exit_code == 5:
                    error_message += "5: SSL verification failure"
                elif exit_code == 7:
                    error_message += "7: Protocol error"
                elif exit_code == 8:
                    error_message += "8: Server issued an error response"
                else:
                    error_message += "unknown."
                # source: https://gist.github.com/cosimo/5747881

                await ctx.author.send(error_message)
                files = None
        else:
            files = None

        if files is None and text == '':
            # no text, no attachment, nothing to send
            await ctx.send_help()
            return

        try:  # we try to get a channel object
            channel = await commands.TextChannelConverter().convert(ctx, potential_channel)
        except (commands.BadArgument, IndexError):
            # no channel was given or text is empty (attachment)
            channel = ctx.channel
        else:
            text = text.replace(potential_channel, '')  # we remove the channel from the text

        try:
            await channel.send(text, files=files)
        except discord.errors.Forbidden:
            if not ctx.guild.me.permissions_in(channel).send_messages:
                await ctx.send("I am not allowed to send messages in " + channel.mention)
            elif not ctx.guild.me.permissions_in(channel).attach_files:
                await ctx.send("I am not allowed to upload files in " + channel.mention)

        self.clear_cache()

    @commands.command(name="say")
    @checks.guildowner()
    async def _say(self, ctx, *, text: str = ''):
        """
        Make the bot say what you want in the desired channel.

        If no channel is specified, the message will be send in the current channel.
        You can attach some files to upload them to Discord.

        Example usage :
        - `!say #general hello there`
        - `!say owo I have a file` (a file is attached to the command message)
        """

        await self.say(ctx, text)

    @commands.command(name="sayd", aliases=["sd"])
    @checks.guildowner()
    async def _saydelete(self, ctx, *, text: str = ''):
        """
        Same as say command, except it deletes your message.
        
        If the message wasn't removed, then I don't have enough permissions.
        """

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

        if u in self.interaction:
            await ctx.send("A session is already running.")
            return

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
        self.clear_cache()
