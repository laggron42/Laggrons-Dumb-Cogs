from .say import Say


def setup(bot):
    bot.add_cog(Say(bot))
