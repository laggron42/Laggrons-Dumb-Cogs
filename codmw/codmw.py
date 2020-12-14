import discord
import logging
import os

from datetime import datetime, timedelta
from laggron_utils.logging import init_logger, close_logger, DisabledConsoleOutput

from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.data_manager import cog_data_path

from .api_wrapper import Client, Forbidden, NotFound

log = logging.getLogger("red.laggron.codmw")
_ = Translator("CODMW", __file__)

GAMEMODES_MAPPING = {
    "dom": "Domination",
    "war": "Team Deathmatch",
    "hq": "Headquarters",
    "koth": "King of the Hill",
    "conf": "Kill Confirmed",
    # "br_dmz": "",
    "br": "Battle Royale",
    "sd": "Search and Destroy",
    "cyber": "Cyber Attack",
    "br_all": "Battle Royale (all)",
    "dd": "Demolition",
}


def pretty_date(time: datetime):
    """
    Get a datetime object and return a pretty string like 'an hour ago',
    'Yesterday', '3 months ago', 'just now', etc
    This is based on this answer, modified for i18n compatibility:
    https://stackoverflow.com/questions/1551382/user-friendly-time-format-in-python
    """

    def text(amount: float, unit: tuple):
        amount = round(amount)
        if amount > 1:
            unit = unit[1]
        else:
            unit = unit[0]
        return _("{amount} {unit} ago.").format(amount=amount, unit=unit)

    units_name = {
        0: (_("year"), _("years")),
        1: (_("month"), _("months")),
        2: (_("week"), _("weeks")),
        3: (_("day"), _("days")),
        4: (_("hour"), _("hours")),
        5: (_("minute"), _("minutes")),
        6: (_("second"), _("seconds")),
    }
    now = datetime.now()
    diff = now - time
    second_diff = diff.seconds
    day_diff = diff.days
    if day_diff < 0:
        return ""
    if day_diff == 0:
        if second_diff < 10:
            return _("just now")
        if second_diff < 60:
            return text(second_diff, units_name[6])
        if second_diff < 120:
            return _("a minute ago")
        if second_diff < 3600:
            return text(second_diff / 60, units_name[5])
        if second_diff < 7200:
            return _("an hour ago")
        if second_diff < 86400:
            return text(second_diff / 3600, units_name[4])
    if day_diff == 1:
        return _("yesterday")
    if day_diff < 7:
        return text(day_diff, units_name[3])
    if day_diff < 31:
        return text(day_diff / 7, units_name[2])
    if day_diff < 365:
        return text(day_diff / 30, units_name[1])
    return text(day_diff / 365, units_name[0])


@cog_i18n(_)
class CODMW(commands.Cog):
    """
    Shows infos and stats about Call of Duty: Modern Warfare.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.cod_client: Client = None

    __author__ = ["retke (El Laggron)"]
    __version__ = "1.0.2"

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if not isinstance(error, commands.CommandInvokeError):
            return
        if not ctx.command.cog_name == self.__class__.__name__:
            # That error doesn't belong to the cog
            return
        log.removeHandler(self.stdout_handler)  # remove console output since red also handle this
        log.error(
            f"Exception in command '{ctx.command.qualified_name}'.\n\n", exc_info=error.original
        )
        log.addHandler(self.stdout_handler)  # re-enable console output for warnings

    async def _clear_client(self):
        """
        This is called on cog unload, it will close the aiohttp session.
        """
        await self.cod_client.session.close()

    def cog_unload(self):
        log.debug("Unloading cog...")
        if self.cod_client is not None:
            self.bot.loop.create_task(self._clear_client())
        close_logger(log)

    async def call_api(self, ctx: commands.Context, coro, *args, **kwargs):
        retried = False
        while True:
            try:
                response = await coro(*args, **kwargs)
            except Forbidden as e:
                if retried is False:
                    retried = True
                    await self.cod_client._get_tokens()
                    continue
                else:
                    log.error("Bot isn't logged in.", exc_info=e)
                    await ctx.send(
                        _(
                            "The bot encountered issues logging in to <https://callofduty.com>.\n"
                            "Please try again later."
                        )
                    )
                    return
            except NotFound:
                await ctx.send(_("This user cannot be found. Check the username and platform."))
                return
            except Exception as e:
                log.error("Unexpected API error.", exc_info=e)
                await ctx.send(_("The bot encountered an unexpected error."))
                return
            else:
                return response

    async def _check_for_tokens(self, ctx: commands.Context):
        if self.cod_client is not None:
            return True
        tokens = await self.bot.get_shared_api_tokens("cod")
        if any(x not in tokens for x in ("username", "password")):
            await ctx.send(
                _(
                    "Credentials are not set. You have to use your email and password with the "
                    "following command: `{prefix}set api cod username,your_username password,"
                    "your_password`"
                ).format(prefix=ctx.clean_prefix)
            )
            return False
        self.cod_client = Client("v1", "mw", tokens["username"], tokens["password"])

    def _format_timedelta(self, time: timedelta):
        """Format a timedelta object into a string"""
        # source: warnsystem from laggrons-dumb-cogs
        # blame python for not creating a strftime attribute
        plural = lambda name, amount: name[1] if amount > 1 else name[0]
        strings = []

        seconds = time.total_seconds()
        years, seconds = divmod(seconds, 31622400)
        months, seconds = divmod(seconds, 2635200)
        weeks, seconds = divmod(seconds, 604800)
        days, seconds = divmod(seconds, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        units = [years, months, weeks, days, hours, minutes, seconds]

        # tuples inspired from mikeshardmind
        # https://github.com/mikeshardmind/SinbadCogs/blob/v3/scheduler/time_utils.py#L29
        units_name = {
            0: (_("year"), _("years")),
            1: (_("month"), _("months")),
            2: (_("week"), _("weeks")),
            3: (_("day"), _("days")),
            4: (_("hour"), _("hours")),
            5: (_("minute"), _("minutes")),
            6: (_("second"), _("seconds")),
        }
        for i, value in enumerate(units):
            if value < 1:
                continue
            unit_name = plural(units_name.get(i), value)
            strings.append(f"{round(value)} {unit_name}")
        string = ", ".join(strings[:-1])
        if len(strings) > 1:
            string += _(" and ") + strings[-1]
        elif len(strings) == 1:
            string = strings[0]
        else:
            string = _("None.")
        return string

    def _get_progress_bar(self, progress, limit):
        # https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/audio/audio.py#L3920
        sections = 20
        try:
            progress = round((progress / limit) * sections)
        except ZeroDivisionError:
            return "==>"
        bar = "="
        seek = ">"
        empty = " "
        text = ""
        for i in range(sections):
            if i < progress:
                text += bar
            elif i == progress:
                text += seek
            else:
                text += empty
        return f"`[{text}]`"

    def _get_gamemode(self, gamemode):
        """br -> Battle Royale"""
        game_list = gamemode.split("_")
        if "hc" in game_list:
            game_list.remove("hc")
            gamemode = game_list[0]
            hardcore = True
        else:
            hardcore = False
        try:
            mode = GAMEMODES_MAPPING[gamemode]
        except KeyError:
            return gamemode
        else:
            if hardcore:
                mode = "Hardcore " + mode
            return mode

    @commands.group()
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def cod(self, ctx: commands.Context):
        """
        Show stats of your Call of Duty account.
        """
        pass

    @cod.command(name="mw")
    async def cod_mw(self, ctx: commands.Context, platform: str, username: str):
        """
        Show global stats of your Call of Duty account.

        `platform` is the platform you play on. Use the following values:
        `psn` = Playstation Network
        `xbl` = Xbox Live
        `battle` = Battle.net
        `steam` = Steam

        `username` is your username on the said platform (tag included if it exists)
        """
        if await self._check_for_tokens(ctx) is False:
            return
        async with ctx.typing():
            data = await self.call_api(ctx, self.cod_client.fetch_player_info, platform, username)
        if data is None:
            return
        game_data = data["lifetime"]["all"]["properties"]
        try:
            favorite_gamemode = sorted(
                [(k, v) for k, v in data["lifetime"]["mode"].items()],
                key=lambda x: x[1]["properties"]["timePlayed"],
            )[0][
                0
            ]  # first result, then we only keep the key, not the value
        except IndexError:
            favorite_gamemode = None
        embed = discord.Embed()
        embed.set_thumbnail(url="https://i.imgur.com/9xaOL9M.png")
        embed.title = _("{username}'s stats").format(username=data["username"])
        embed.color = ctx.author.color if ctx.guild else discord.Embed.Empty
        embed.description = "Multiplayer (all)"
        embed.add_field(
            name=_("Level"),
            value=_("**{level}** {bar} {next_level}").format(
                level=round(data["level"]),
                bar=self._get_progress_bar(
                    data["levelXpGained"], data["levelXpGained"] + data["levelXpRemainder"]
                ),
                next_level=round(data["level"]) + 1,
            ),
            inline=False,
        )
        time = timedelta(seconds=game_data["timePlayedTotal"])
        time -= timedelta(seconds=time.seconds % 60)
        embed.add_field(name=_("Time played"), value=self._format_timedelta(time), inline=False)
        games_played = round(game_data["gamesPlayed"])
        embed.add_field(name=_("Games played"), value=f"{games_played:,}", inline=False)
        wins = round(game_data["wins"])
        losses = round(game_data["losses"])
        embed.add_field(name=_("Wins/Losses"), value=f"{wins:,}/{losses:,}", inline=True)
        embed.add_field(
            name=_("Winrate"), value=f"{round((wins/games_played)*100, 1)}%", inline=True
        )
        embed.add_field(
            name=_("Win streak"),
            value=_("Current: {current}\nBest: {best}").format(
                current=f"{round(game_data['currentWinStreak']):,}",
                best=f"{round(game_data['recordLongestWinStreak']):,}",
            ),
            inline=True,
        )
        embed.add_field(
            name=_("Kills/Deaths/Assists"),
            value=_(
                "{kills}/{deaths}/{assists}\n"
                "Best number of kills: {best_kills}\n"
                "Best number of assists: {best_assists}\n"
            ).format(
                kills=f"{round(game_data['kills']):,}",
                deaths=f"{round(game_data['deaths']):,}",
                assists=f"{round(game_data['assists']):,}",
                best_kills=f"{round(game_data['bestKills']):,}",
                best_assists=f"{round(game_data['bestAssists']):,}",
            ),
            inline=True,
        )
        embed.add_field(
            name=_("K/D Ratio"),
            value=_("Average: {avg}\nBest: {best}").format(
                avg=f"{round(game_data['kdRatio'], 3):,}",
                best=f"{round(game_data['bestKD'], 3):,}",
            ),
            inline=True,
        )
        embed.add_field(
            name=_("Kill streak"),
            value=_("Current: {current}\nBest: {best}").format(
                current=f"{round(game_data['recordKillStreak']):,}",
                best=f"{round(game_data['bestKillStreak']):,}",
            ),
            inline=True,
        )
        embed.add_field(
            name=_("Accuracy"), value=f"{round(game_data['accuracy']*100, 2)}%", inline=True
        )
        embed.add_field(
            name=_("Score per game"), value=f"{round(game_data['scorePerGame']):,}", inline=True
        )
        embed.add_field(
            name=_("Best score per minute"), value=f"{round(game_data['bestSPM']):,}", inline=True
        )
        if favorite_gamemode:
            embed.set_footer(text=f"Favorite gamemode: {self._get_gamemode(favorite_gamemode)}")
        await ctx.send(embed=embed)

    @cod.command(name="wz")
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def cod_wz(self, ctx: commands.Context, platform: str, username: str):
        """
        Show Warzone stats on your Call of Duty account.

        `platform` is the platform you play on. Use the following values:
        `psn` = Playstation Network
        `xbl` = Xbox Live
        `battle` = Battle.net
        `steam` = Steam

        `username` is your username on the said platform (tag included if it exists)
        """
        if await self._check_for_tokens(ctx) is False:
            return
        async with ctx.typing():
            data = await self.call_api(ctx, self.cod_client.fetch_player_info, platform, username)
        if data is None:
            return
        game_data = data["lifetime"]["mode"]["br"]["properties"]
        embed = discord.Embed()
        embed.set_thumbnail(url="https://i.imgur.com/9xaOL9M.png")
        embed.title = _("{username}'s stats").format(username=data["username"])
        embed.color = ctx.author.color if ctx.guild else discord.Embed.Empty
        embed.description = "Warzone (Battle Royale)"
        embed.add_field(
            name=_("Time played"),
            value=self._format_timedelta(timedelta(seconds=game_data["timePlayed"])),
            inline=False,
        )
        games_played = round(game_data["gamesPlayed"])
        embed.add_field(name=_("Games played"), value=f"{games_played:,}", inline=True)
        wins = round(game_data["wins"])
        embed.add_field(name=_("Wins"), value=f"{wins:,}", inline=True)
        embed.add_field(
            name=_("Winrate"), value=f"{round((wins/games_played)*100, 1)}%", inline=True
        )
        embed.add_field(
            name=_("Kills/Deaths"),
            value=f"{round(game_data['kills']):,}/{round(game_data['deaths']):,}",
            inline=True,
        )
        embed.add_field(
            name=_("K/D Ratio"), value=f"{round(game_data['kdRatio'], 3):,}", inline=True
        )
        embed.add_field(
            name=_("Contracts"), value=f"{round(game_data['contracts']):,}", inline=True
        )
        embed.add_field(name=_("Revives"), value=f"{round(game_data['revives']):,}", inline=True)
        embed.add_field(name=_("Downs"), value=f"{round(game_data['downs']):,}", inline=True)
        embed.add_field(
            name=_("Number of tops"),
            value=_("Top 25: {top_25}\n" "Top 10: {top_10}\n" "Top 5: {top_5}").format(
                top_25=round(game_data["topTwentyFive"]),
                top_10=round(game_data["topTen"]),
                top_5=round(game_data["topFive"]),
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @cod.command(name="recent")
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def cod_recent(self, ctx: commands.Context, platform: str, username: str):
        """
        Show your 5 last Call of Duty matches.

        `platform` is the platform you play on. Use the following values:
        `psn` = Playstation Network
        `xbl` = Xbox Live
        `battle` = Battle.net
        `steam` = Steam

        `username` is your username on the said platform (tag included if it exists)
        """
        if await self._check_for_tokens(ctx) is False:
            return
        async with ctx.typing():
            data = await self.call_api(
                ctx, self.cod_client.fetch_player_recent_matches, platform, username
            )
        if data is None:
            return
        embed = discord.Embed(title=username, description=_("5 most recent matches."))
        embed.color = ctx.author.color if ctx.guild else discord.Embed.Empty
        embed.set_thumbnail(url="https://i.imgur.com/sv9WhEv.png")
        for match in data["matches"][:5]:
            # original design made by iShot#5449
            result = ("🟩 " + _("Won")) if match["result"] == "win" else ("🟥 " + _("Lost"))
            gamemode = self._get_gamemode(match["mode"])
            time = pretty_date(datetime.fromtimestamp(match["utcEndSeconds"]).replace(second=0))
            map = match["map"].split("_")[1].title()
            title = _("**{result}** a game of **{gamemode}** on **{map}** {time}").format(
                result=result, gamemode=gamemode, map=map, time=time
            )
            duration = self._format_timedelta(timedelta(seconds=match["duration"] / 1000))
            player_stats = match["playerStats"]
            value = _(
                "⏳ Match lasted {duration}\n"
                "Score: `{score}` | XP: `{xp}`\n"
                "Kills: `{kills}` | Deaths: `{deaths}` | KDR: {kdr}%"
            ).format(
                duration=duration,
                score=f"{round(player_stats['score']):,}",
                xp=f"{round(player_stats['matchXp']):,}",
                kills=f"{round(player_stats['kills']):,}",
                deaths=f"{round(player_stats['deaths']):,}",
                kdr=f"{round(player_stats['kdRatio'], 2)}",
            )
            embed.add_field(name=title, value=value, inline=False)
        await ctx.send(embed=embed)
