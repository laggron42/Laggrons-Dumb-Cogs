import discord
from discord.ext import commands

class Avatar:

    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True)
    async def avatar(self, ctx, user : discord.Member = None):
        author = ctx.message.author
        
        if user is None:
            url = str(author.avatar_url)
        else:
            url = str(user.avatar_url)

        await self.bot.say(url)

def setup(bot):
    bot.add_cog(Avatar(bot))
