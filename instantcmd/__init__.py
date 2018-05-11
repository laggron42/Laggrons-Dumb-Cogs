from .instantcmd import InstantCommands

def setup(bot):
    bot.add_cog(InstantCommands(bot))