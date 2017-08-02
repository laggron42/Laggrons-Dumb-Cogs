import discord
import os
import os.path
from discord.ext import commands

class Say:
    """Make your bot say or upload something in the channel you want."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(pass_context=True)
    async def send(self, ctx): # Had to choose something else than say :c have a better idea ?
        if ctx.invoked_subcommand is None:
            pages = self.bot.formatter.format_help_for(ctx, ctx.command)
            for page in pages:
                await self.bot.send_message(ctx.message.channel, page)

    @send.command(pass_context=True)
    async def here(self, ctx, *, text):
        """Say a message in the actual channel and auto delete"""
        
        message = ctx.message
        await self.bot.say(text)
        await self.bot.delete_message(message)

    @send.command(pass_context=True)
    async def channel(self, ctx, channel : discord.Channel, *, text):
        """Say a message in the chosen channel and auto delete"""

        message = ctx.message
        await self.bot.send_message(channel, text)
        await self.bot.delete_message(message)

    @send.command(pass_context=True)
    async def upload(self, ctx, file, *, comment = None):
        """Upload a file from your local folder"""

        message = ctx.message
        path = os.path.join(os.getcwd(), "data", "Say", file)
        
        if os.path.isfile(path) is True:

            await self.bot.delete_message(message)

            if comment is not None:
                await self.bot.upload(fp = path, content = comment)

            else:
                await self.bot.upload(fp = path)
        else:
            await self.bot.say("That file doesn't seems to exist. Make sure it is the good name, that you added the extention (.png/.gif/...) and if you just added a new file, make sure to reload the cog by typing `[p]reload say`")

    @send.command(pass_context=True)
    async def dm(self, ctx, user : discord.Member, *, text):
        """Send a message to the user in direct message. No author mark"""

        await self.bot.send_message(user, text)

def check_folders():
    if not os.path.exists("data/Say"):
        print("Creating data/Say folder...")
        os.makedirs("data/Say")

def setup(bot):
    check_folders()
    bot.add_cog(Say(bot))
