import pathlib
import os
from .say import Say
from redbot.core.data_manager import cog_data_path

def create_cache(path: pathlib.Path):
    if not path.exists():
        return
    directories = [x for x in path.iterdir() if x.is_dir()]
    if (path / 'cache') not in directories:
        (path / 'cache').mkdir()

def setup(bot):
    n = Say(bot)
    create_cache(cog_data_path(n))
    bot.add_cog(n)
