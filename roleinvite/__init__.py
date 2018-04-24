from .roleinvite import RoleInvite

def setup(bot):
    n = RoleInvite(bot)
    bot.add_cog(n)
