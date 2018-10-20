from .roleinvite import RoleInvite


async def setup(bot):
    n = RoleInvite(bot)
    if await n.data.rename():
        n.roleset.name = "inviteset"
    bot.add_cog(n)
