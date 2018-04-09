import discord
import datetime
import os
import asyncio

from redbot.core import checks
from discord.ext import commands

class Say:
    """Speak as if you were the bot"""

    def __init__(self, bot):
        self.bot = bot
        self.interaction = []

    
    async def on_reaction_add(self, reaction, user):
        if user.id in self.interaction:
            channel = reaction.message.channel
            if isinstance(channel, discord.DMChannel):
                self.interaction.remove(user.id)
                await channel.send("Session closed")

    async def say(self, ctx, text):

        text = [x for x in text]
        if ctx.message.attachments != []:
            os.system('wget ' + ctx.message.attachments[0].url)
            file = discord.File(ctx.message.attachments[0].filename)
        else:
            file = None

        try: # we try to get a channel object
            channel = await commands.TextChannelConverter().convert(ctx, text[0])
        except commands.BadArgument: # no channel was given
            channel = ctx.channel
        else:
            text.remove(text[0])

        text = " ".join(text)

        try:
            await channel.send(text, file=file)

        except discord.errors.Forbidden:
            if not ctx.guild.me.permissions_for(channel).send_messages:
                await ctx.send("I am not allowed to send messages in "+channel.mention)
            elif not ctx.guild.me.permissions_for(channel).attach_files:
                await ctx.send("I am not allowed to upload files in "+channel.mention)

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
    async def _interact(self, ctx, channel: discord.TextChannel = None):
        """Start receiving and sending messages as the bot through DM"""

        u = ctx.author
        if channel is None:
            if isinstance(ctx.channel, discord.DMChannel):
                await ctx.send("You need to give a channel to enable this in DM. You can give the channel ID too.")
                return
            else:
                channel = ctx.channel

        message = await u.send("I will start sending you messages from {}.\n"
        "Just send me any message and I will send it in that channel.\n"
        "React with ❌ on this message to end the session.\n"
        "If no message was send or received in the last 5 minutes, the request will time out and stop.".format(channel.mention))
        await message.add_reaction('❌')
        self.interaction.append(u.id)

        while True:

            #print("=== New loop ===\n"
            #    "self.interaction = {}".format(self.interaction))

            if u.id not in self.interaction:
                return

            try:
                message = await self.bot.wait_for("message", timeout=300)
            except asyncio.TimeoutError:
                await u.send("Request timed out. Session closed")
                self.interaction.remove(u.id)
                return

            #print("\nmessage :\n"
            #    "   author = {}\n"
            #    "   content = {}\n"
            #    "   channel = {}\n"
            #    "   guild = {}\n\n".format(
            #        str(message.author), message.content[20:], str(message.channel), str(message.guild)
            #    ))

            #print(message.channel is discord.DMChannel)
            if message.author == u and isinstance(message.channel, discord.DMChannel):
                print("Message from ctx author and in DM")

                if message.attachments != []:
                    os.system("wget " + message.attachments[0].url)
                    await channel.send(message.content, file=discord.File(message.attachments[0].filename))
                    os.remove(message.attachments[0].filename)

                else:
                    await channel.send(message.content)
                

            elif message.channel != channel or message.author == channel.guild.me or message.author == u:
                #print("Message blocked:\n"
                #    "   message.channel != channel : {}\n"
                #    "   message.author == ctx.guild.me : {}\n"
                #    "   message.author == u : {}\n".format(
                #        message.channel != channel, message.author == channel.guild.me, message.author == u
                #    ))
                pass
            
            else:
                
                #print("Message good !")

                embed = discord.Embed()
                embed.set_author(name="{} | {}".format(
                    str(message.author) , message.author.id), icon_url=message.author.avatar_url)
                embed.set_footer(text=message.created_at.strftime("%d %b %Y %H:%M"))
                embed.description = message.content
                embed.color = message.author.color

                if message.attachments != []:
                    embed.set_image(url=message.attachments[0].url)

                await u.send(embed=embed)

            #print("\n\n")

