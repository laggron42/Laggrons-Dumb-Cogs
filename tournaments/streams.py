import discord
import logging
import re

from typing import Optional
from copy import deepcopy

from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils import menus
from redbot.core.utils.chat_formatting import pagify

from .abc import MixinMeta
from .utils import only_phase
from .objects import Streamer

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)

TWITCH_CHANNEL_RE = re.compile(r"(https://(www\.)?twitch.tv/)(?P<channel_name>\S[^/]+)(/.*)?")


async def mod_or_streamer(ctx: commands.Context):
    if ctx.author.id == ctx.guild.owner.id:
        return True
    is_mod = await ctx.bot.is_mod(ctx.author)
    if is_mod is True:
        return True
    is_owner = await ctx.bot.is_owner(ctx.author)
    if is_owner is True:
        return True
    tournament = ctx.cog.tournaments[ctx.guild.id]
    if tournament.streamer_role and tournament.streamer_role in ctx.author.roles:
        return True
    return False


class TwitchChannelConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        result = TWITCH_CHANNEL_RE.match(argument)
        if not result.group("channel_name"):
            raise commands.BadArgument(
                _("This is not a valid Twitch channel. Example: <https://twitch.tv/firedragon>")
            )
        return result.group("channel_name")


# You'll notice there are way too many repetitions in the code of these commands.
# I'm nearly at the end of the project while writing this, and I'm *tired*
# I'll use a better solution if I'm not too lazy and need to edit this part
class Streams(MixinMeta):
    @only_phase("ongoing")
    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def stream(self, ctx: commands.Context):
        """
        Display streams, or manage them.
        """
        if ctx.invoked_subcommand is None:
            tournament = self.tournaments[ctx.guild.id]
            if not tournament.streamers:
                await ctx.send(_("No streamers in this tournament for now."))
                return
            if len(tournament.streamers) == 1:
                await ctx.send(tournament.streamers[0].link)
            else:
                await ctx.send("\n".join([x.link for x in tournament.streamers]))

    @stream.command(name="init")
    @commands.check(mod_or_streamer)
    async def stream_init(self, ctx: commands.Context, url: TwitchChannelConverter):
        """
        Initialize your stream.
        """
        tournament = self.tournaments[ctx.guild.id]
        streamer = tournament.find_streamer(channel=url)[0]
        if streamer is not None:
            await ctx.send(_("A streamer with that link is already configured."))
            return
        streamer = Streamer(tournament, ctx.author, url)
        tournament.streamers.append(streamer)
        await ctx.tick()

    @stream.command(name="list")
    @commands.check(mod_or_streamer)
    async def stream_list(self, ctx: commands.Context):
        """
        List streams.
        """
        tournament = self.tournaments[ctx.guild.id]
        streamers = tournament.streamers
        if not streamers:
            await ctx.send(_("No streamers in this tournament for now."))
            return
        text = _("__List of streamers on this tournament__\n\n")
        for streamer in streamers:
            match = streamer.current_match
            text += _("<{s.link}> by {s.member}: {current}").format(
                s=streamer,
                current=_("On set {set}").format(
                    set=match.channel.mention if match.channel else f"#{match.set}"
                )
                if match
                else _("Pending"),
            )
        for page in pagify(text):
            await ctx.send(page)

    @stream.command(name="set")
    @commands.check(mod_or_streamer)
    async def stream_set(
        self,
        ctx: commands.Context,
        channel: Optional[TwitchChannelConverter],
        room_id: str,
        room_code: str,
    ):
        """
        Configure room info for a stream.

        You must pass the room ID followed by its code. (yes this is totally for Smash Bros.)

        If you want to edit someone else's stream, give its channel as the first argument.

        Examples:
        - `[p]stream set 5RF7G 260`
        - `[p]stream set https://twitch.tv/el_laggron 5RF7G 260`
        """
        tournament = self.tournaments[ctx.guild.id]
        if channel is None:
            streamer = tournament.find_streamer(discord_id=ctx.author.id)[1]
            if streamer is None:
                await ctx.send(
                    _(
                        "You don't have any stream. If you want to edit someone else's stream, "
                        "put its channel link as the first argument "
                        "(see `{prefix}help stream set`)."
                    ).format(prefix=ctx.clean_prefix)
                )
                return
        else:
            streamer = tournament.find_streamer(channel=channel)[1]
            if streamer is None:
                await ctx.send(
                    _(
                        "I can't find any existing stream with that link. "
                        "Please check the list with `{prefix}stream list`."
                    )
                )
                return
        streamer.set_room(room_id, room_code)
        await ctx.tick()

    @stream.command(name="transfer")
    @commands.check(mod_or_streamer)
    async def stream_transfer(
        self,
        ctx: commands.Context,
        channel: Optional[TwitchChannelConverter],
        member: discord.Member = None,
    ):
        """
        Transfer a stream's ownership.

        Reminder that ownership of a stream means nothing, \
any streamer/T.O. can edit anyone's stream.
        Use this if you want to setup a stream and then to pass it to the streamer.

        Being owner of a stream will only prevent having to enter a link each time.

        If you want to edit someone else's stream, give its channel as the first argument.
        """
        tournament = self.tournaments[ctx.guild.id]
        if channel is None:
            streamer = tournament.find_streamer(discord_id=ctx.author.id)[1]
            if streamer is None:
                await ctx.send(
                    _(
                        "You don't have any stream. If you want to edit someone else's stream, "
                        "put its channel link as the first argument "
                        "(see `{prefix}help stream set`)."
                    ).format(prefix=ctx.clean_prefix)
                )
                return
        else:
            streamer = tournament.find_streamer(channel=channel)[1]
            if streamer is None:
                await ctx.send(
                    _(
                        "I can't find any existing stream with that link. "
                        "Please check the list with `{prefix}stream list`."
                    )
                )
                return
        streamer.member = member or ctx.author
        await ctx.tick()

    @stream.command(name="add")
    @commands.check(mod_or_streamer)
    async def stream_add(
        self, ctx: commands.Context, channel: Optional[TwitchChannelConverter], *sets: int,
    ):
        """
        Add sets to a stream.

        You can add multiple sets at once.
        The set numbers are directly listed on the bracket.

        If you want to edit someone else's stream, give its channel as the first argument.

        Examples:
        - `[p]stream add 252 253 254 255`
        - `[p]stream add https://twitch.tv/el_laggron 252 253 254 255`
        """
        if not sets:
            await ctx.send_help()
            return
        tournament = self.tournaments[ctx.guild.id]
        if channel is None:
            streamer = tournament.find_streamer(discord_id=ctx.author.id)[1]
            if streamer is None:
                await ctx.send(
                    _(
                        "You don't have any stream. If you want to edit someone else's stream, "
                        "put its channel link as the first argument "
                        "(see `{prefix}help stream set`)."
                    ).format(prefix=ctx.clean_prefix)
                )
                return
        else:
            streamer = tournament.find_streamer(channel=channel)[1]
            if streamer is None:
                await ctx.send(
                    _(
                        "I can't find any existing stream with that link. "
                        "Please check the list with `{prefix}stream list`."
                    )
                )
                return
        errors = await streamer.add_matches(*sets)
        if errors:
            await ctx.send(
                _("Some errors occured:\n\n")
                + "\n".join([f"#{x}: {y}" for x, y in errors.items()])
            )
        else:
            await ctx.tick()

    @stream.command(name="remove", aliases=["del", "delete"])
    @commands.check(mod_or_streamer)
    async def stream_remove(
        self, ctx: commands.Context, channel: Optional[TwitchChannelConverter], *sets: int,
    ):
        """
        Remove sets from your stream.

        You can remove multiple sets at once.
        The set numbers are listed with `[p]stream info`.

        If you want to edit someone else's stream, give its channel as the first argument.

        Examples:
        - `[p]stream remove 252 253 254 255`
        - `[p]stream remove https://twitch.tv/el_laggron 252 253 254 255`
        """
        if not sets:
            await ctx.send_help()
            return
        tournament = self.tournaments[ctx.guild.id]
        if channel is None:
            streamer = tournament.find_streamer(discord_id=ctx.author.id)[1]
            if streamer is None:
                await ctx.send(
                    _(
                        "You don't have any stream. If you want to edit someone else's stream, "
                        "put its channel link as the first argument "
                        "(see `{prefix}help stream set`)."
                    ).format(prefix=ctx.clean_prefix)
                )
                return
        else:
            streamer = tournament.find_streamer(channel=channel)[1]
            if streamer is None:
                await ctx.send(
                    _(
                        "I can't find any existing stream with that link. "
                        "Please check the list with `{prefix}stream list`."
                    )
                )
                return
        try:
            await streamer.remove_matches(*sets)
        except KeyError:
            await ctx.send(_("None of the sets you sent were listed in the stream."))
        else:
            await ctx.tick()

    @stream.command(name="swap")
    @commands.check(mod_or_streamer)
    async def stream_swap(
        self,
        ctx: commands.Context,
        channel: Optional[TwitchChannelConverter],
        set1: int,
        set2: int,
    ):
        """
        Swap two streams in your list.

        If the stream strictly respects order, then this can be useful for modifying the order.
        Else this doesn't marrer.

        If you want to edit someone else's stream, give its channel as the first argument.

        Examples:
        - `[p]stream swap 252 254`
        - `[p]stream swap https://twitch.tv/el_laggron 252 254`
        """
        tournament = self.tournaments[ctx.guild.id]
        if channel is None:
            streamer = tournament.find_streamer(discord_id=ctx.author.id)[1]
            if streamer is None:
                await ctx.send(
                    _(
                        "You don't have any stream. If you want to edit someone else's stream, "
                        "put its channel link as the first argument "
                        "(see `{prefix}help stream set`)."
                    ).format(prefix=ctx.clean_prefix)
                )
                return
        else:
            streamer = tournament.find_streamer(channel=channel)[1]
            if streamer is None:
                await ctx.send(
                    _(
                        "I can't find any existing stream with that link. "
                        "Please check the list with `{prefix}stream list`."
                    )
                )
                return
        try:
            streamer.swap_match(set1, set2)
        except KeyError:
            await ctx.send(_("One of the provided sets cannot be found."))
        else:
            await ctx.tick()

    @stream.command(name="info")
    @commands.check(mod_or_streamer)
    async def stream_info(
        self, ctx: commands.Context, channel: Optional[TwitchChannelConverter],
    ):
        """
        Shows infos about a stream.

        If you want to view someone else's stream info, give its channel as the first argument.

        Examples:
        - `[p]stream info`
        - `[p]stream info https://twitch.tv/el_laggron`
        """
        tournament = self.tournaments[ctx.guild.id]
        if channel is None:
            streamer = tournament.find_streamer(discord_id=ctx.author.id)[1]
            if streamer is None:
                await ctx.send(
                    _(
                        "You don't have any stream. If you want to edit someone else's stream, "
                        "put its channel link as the first argument "
                        "(see `{prefix}help stream set`)."
                    ).format(prefix=ctx.clean_prefix)
                )
                return
        else:
            streamer = tournament.find_streamer(channel=channel)[1]
            if streamer is None:
                await ctx.send(
                    _(
                        "I can't find any existing stream with that link. "
                        "Please check the list with `{prefix}stream list`."
                    )
                )
                return
        sets = ""
        for match in streamer.matches:
            if isinstance(match, int):
                sets += _("#{set}: *waiting for players*\n").format(set=match)
                continue
            text = f"#{match.set}: {match.player1} vs {match.player2}"
            if match.status == "ongoing":
                text = f"**{text}**"
            else:
                text += _(" (on hold)")
            sets += text + "\n"
        embed = discord.Embed(title=streamer.link)
        embed.url = streamer.link
        embed.add_field(
            name=_("Room info"),
            value=_("ID: {id}\nCode: {code}").format(id=streamer.room_id, code=streamer.room_code),
            inline=False,
        )
        if len(sets) < 1024:
            embed.add_field(
                name=_("List of sets"), value=sets or _("Nothing set."), inline=False,
            )
            await ctx.send(embed=embed)
        else:
            embeds = []
            for page in pagify(sets):
                _embed = deepcopy(embed)
                _embed.add_field(
                    name=_("List of sets"), value=page, inline=False,
                )
                embeds.append(_embed)
            await menus.menu(ctx, embeds, controls=menus.DEFAULT_CONTROLS)

    @stream.command(name="end")
    @commands.check(mod_or_streamer)
    async def stream_end(
        self, ctx: commands.Context, channel: Optional[TwitchChannelConverter],
    ):
        """
        Closes a stream.

        If you want to close someone else's stream info, give its channel as the first argument.

        Examples:
        - `[p]stream end`
        - `[p]stream end https://twitch.tv/el_laggron`
        """
        tournament = self.tournaments[ctx.guild.id]
        if channel is None:
            i, streamer = tournament.find_streamer(discord_id=ctx.author.id)
            if streamer is None:
                await ctx.send(
                    _(
                        "You don't have any stream. If you want to edit someone else's stream, "
                        "put its channel link as the first argument "
                        "(see `{prefix}help stream set`)."
                    ).format(prefix=ctx.clean_prefix)
                )
                return
        else:
            i, streamer = tournament.find_streamer(channel=channel)
            if streamer is None:
                await ctx.send(
                    _(
                        "I can't find any existing stream with that link. "
                        "Please check the list with `{prefix}stream list`."
                    )
                )
                return
        await streamer.end()
        del tournament.streamers[i]
        await ctx.tick()
