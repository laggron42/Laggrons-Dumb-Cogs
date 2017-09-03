import discord
from discord.ext import commands

class Avatar:

    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True, no_pm=True)
    async def avatar(self, ctx, user: discord.Member=None):
        """User Avatar"""
        author = ctx.message.author
    
        if user is None:
            avatar = str(author.avatar_url)
        else:
            avatar = str(user.avatar_url)
    
        data = discord.Embed(description="**Avatar:**", color=discord.Color.blue())
        data.set_image(url=avatar)
        await self.bot.say(embed=data)

def setup(bot):
    bot.add_cog(Avatar(bot))
