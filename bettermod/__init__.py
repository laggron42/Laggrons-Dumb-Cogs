from .bettermod import BetterMod


def setup(bot):
    has_core_mod_cogs = [(x in bot.cogs) for x in ["Reports", "Warnings"]]
    if any(has_core_mod_cogs):
        raise TypeError(
            "You need to unload Mod, Reports and Warnings cogs to load this cog. Don't worry, "
            "the commands are replaced and re-used."
        )
    bot.add_cog(BetterMod(bot))
