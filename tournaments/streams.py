import discord
import logging
import re

from typing import Optional, Union
from copy import deepcopy

from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils import menus
from redbot.core.utils.chat_formatting import pagify

from .abc import MixinMeta
from .utils import only_phase, prompt_yes_or_no
from .objects import Streamer

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)

TWITCH_CHANNEL_RE = re.compile(r"(https://(www\.)?twitch.tv/)?(?P<channel_name>\S[^/]+)(/.*)?")


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
        if not result or not result.group("channel_name"):
            raise commands.BadArgument
        result = result.group("channel_name")
        if ctx.command.name == "init":
            return result
        tournament = ctx.bot.get_cog("Tournaments").tournaments[ctx.guild.id]
        streamer = tournament.find_streamer(channel=result)[1]
        if streamer is None:
            raise commands.BadArgument
        return streamer


class Streams(MixinMeta):
    async def _get_streamer_from_ctx(self, ctx: commands.Context, streamer) -> Optional[Streamer]:
        if streamer is not None:
            return streamer
        tournament = self.tournaments[ctx.guild.id]
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
        return streamer

    @only_phase()
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

    @only_phase()
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
        if tournament.status != "ongoing":
            await tournament.save()
        await ctx.tick()

    @only_phase()
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

    @only_phase()
    @stream.command(name="set")
    @commands.check(mod_or_streamer)
    async def stream_set(
        self,
        ctx: commands.Context,
        streamer: Optional[TwitchChannelConverter],
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
        streamer = await self._get_streamer_from_ctx(ctx, streamer)
        if not streamer:
            return
        streamer.set_room(room_id, room_code)
        if tournament.status != "ongoing":
            await tournament.save()
        await ctx.tick()

    @only_phase()
    @stream.command(name="transfer")
    @commands.check(mod_or_streamer)
    async def stream_transfer(
        self,
        ctx: commands.Context,
        streamer: Optional[TwitchChannelConverter],
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
        streamer = await self._get_streamer_from_ctx(ctx, streamer)
        if not streamer:
            return
        streamer.member = member or ctx.author
        if tournament.status != "ongoing":
            await tournament.save()
        await ctx.tick()

    @only_phase()
    @stream.command(name="add")
    @commands.check(mod_or_streamer)
    async def stream_add(
        self,
        ctx: commands.Context,
        streamer: Optional[TwitchChannelConverter],
        *sets: int,
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
        streamer = await self._get_streamer_from_ctx(ctx, streamer)
        if not streamer:
            return
        errors = await streamer.check_integrity(sets, add=True)
        if errors:
            await ctx.send(
                _("Some errors occured:\n\n")
                + "\n".join([f"#{x}: {y}" for x, y in errors.items()])
            )
        else:
            await ctx.tick()

    @only_phase()
    @stream.command(name="remove", aliases=["del", "delete", "rm"])
    @commands.check(mod_or_streamer)
    async def stream_remove(
        self,
        ctx: commands.Context,
        streamer: Optional[TwitchChannelConverter],
        *sets: Union[int, str],
    ):
        """
        Remove sets from your stream.

        You can remove multiple sets at once.
        The set numbers are listed with `[p]stream info`.
        Type **all** instead of the list to remove all the sets.

        If you want to edit someone else's stream, give its channel as the first argument.

        Examples:
        - `[p]stream remove 252 253 254 255`
        - `[p]stream remove https://twitch.tv/el_laggron 252 253 254 255`
        """
        if not sets:
            await ctx.send_help()
            return
        tournament = self.tournaments[ctx.guild.id]
        streamer = await self._get_streamer_from_ctx(ctx, streamer)
        if not streamer:
            return
        if len(sets) == 1 and sets[0] == "all":
            await streamer.end()
            streamer.matches = []
            streamer.current_match = None
            await ctx.tick()
        else:
            if not all(isinstance(x, int) for x in sets):
                await ctx.send_help()
                return
            try:
                await streamer.remove_matches(*sets)
            except KeyError:
                await ctx.send(_("None of the sets you sent were listed in the stream."))
            else:
                await ctx.tick()
        if tournament.status != "ongoing":
            await tournament.save()

    @only_phase()
    @stream.command(name="replace")
    @commands.check(mod_or_streamer)
    async def stream_replace(
        self,
        ctx: commands.Context,
        streamer: Optional[TwitchChannelConverter],
        *sets: int,
    ):
        """
        Replace the set list of your stream.

        The set numbers are listed with `[p]stream info`.

        If you want to edit someone else's stream, give its channel as the first argument.

        Examples:
        - `[p]stream replace 252 253 254 255`
        - `[p]stream replace https://twitch.tv/el_laggron 252 253 254 255`
        """
        if not sets:
            await ctx.send_help()
            return
        streamer = await self._get_streamer_from_ctx(ctx, streamer)
        if not streamer:
            return
        tournament = self.tournaments[ctx.guild.id]
        if not streamer.matches:
            await ctx.send(
                _(
                    "You don't even have sets in your queue. " "Use `{prefix}stream add` instead."
                ).format(prefix=ctx.clean_prefix)
            )
            return

        def find_match(_set: int):
            try:
                return next(filter(lambda x: streamer.get_set(x) == _set, streamer.matches))
            except StopIteration:
                return None

        new_list = []
        to_add = []
        for _set in sets:
            streamer_match = find_match(_set)
            match = tournament.find_match(match_set=str(_set))[1] or _set
            if streamer_match is None:
                to_add.append(match)
            new_list.append(match)
        to_remove = [x for x in streamer.matches if x not in new_list]
        if new_list == streamer.matches:
            await ctx.send(_("Same order, same sets, nothing to change."))
            return
        if to_add:
            errors = await streamer.check_integrity([streamer.get_set(x) for x in to_add])
            if errors:
                await ctx.send(
                    _("There are some problems with the new sets, nothing was changed.\n\n")
                    + "\n".join([f"#{x}: {y}" for x, y in errors.items()])
                )
                return
        if to_add or to_remove:

            def get_str_repr(sets):
                str_sets = []
                for _set in sets:
                    if (
                        streamer.current_match
                        and _set == streamer.current_match
                        or _set == streamer.get_set(streamer.current_match)
                    ):
                        str_sets.append(f"**{_set if isinstance(_set, int) else _set.set}**")
                    elif isinstance(_set, int):
                        str_sets.append(f"*{_set}*")
                    else:
                        str_sets.append(str(_set.set))
                return ", ".join(str_sets)

            embed = discord.Embed(color=await ctx.embed_colour())
            embed.description = _("Please confirm the following changes")
            if streamer.current_match and streamer.current_match.status == "ongoing":
                if streamer.current_match in to_remove:
                    embed.set_footer(text=_("⚠ This will cancel your current set!"))
                else:
                    embed.set_footer(text=_("Your current set will not be cancelled"))
            if to_remove:
                embed.add_field(
                    name=_("Sets removed"),
                    value=get_str_repr(to_remove),
                )
            if to_add:
                embed.add_field(name=_("Sets added"), value=get_str_repr(to_add))
            embed.add_field(name=_("New order"), value=get_str_repr(new_list), inline=False)
            response = await prompt_yes_or_no(ctx, embed=embed, delete_after=False)
            if response is False:
                return
        async with ctx.typing():
            async with tournament.lock:
                pass  # would suck to perform that operation while an update is going on
            for match in to_add:
                if isinstance(match, int):
                    continue
                match.streamer = streamer
                if match.status == "ongoing":
                    if new_list.index(match) == 0:
                        match.on_hold = False
                    else:
                        match.on_hold = True
                    await match.stream_queue_add()
            if to_remove:
                await streamer.remove_matches(*[streamer.get_set(x) for x in to_remove])
            streamer.matches = new_list
        if tournament.status != "ongoing":
            await tournament.save()
        await ctx.send(_("Stream queue successfully modified."))

    @only_phase()
    @stream.command(name="swap")
    @commands.check(mod_or_streamer)
    async def stream_swap(
        self,
        ctx: commands.Context,
        streamer: Optional[TwitchChannelConverter],
        set1: int,
        set2: int,
    ):
        """
        Swap two matches in your list.

        If the stream strictly respects order, then this can be useful for modifying the order.
        Else this doesn't marrer.

        If you want to edit someone else's stream, give its channel as the first argument.

        Examples:
        - `[p]stream swap 252 254`
        - `[p]stream swap https://twitch.tv/el_laggron 252 254`
        """
        tournament = self.tournaments[ctx.guild.id]
        streamer = await self._get_streamer_from_ctx(ctx, streamer)
        if not streamer:
            return
        try:
            streamer.swap_match(set1, set2)
        except KeyError:
            await ctx.send(_("One of the provided sets cannot be found."))
        else:
            await ctx.tick()
        if tournament.status != "ongoing":
            await tournament.save()

    @only_phase()
    @stream.command(name="insert")
    @commands.check(mod_or_streamer)
    async def stream_insert(
        self,
        ctx: commands.Context,
        streamer: Optional[TwitchChannelConverter],
        set1: int,
        set2: int,
    ):
        """
        Insert a match in your list.

        This is similar to `[p]stream swap` as this modifies the order of your stream queue, \
but instead of swapping two matches position, you insert a match before another. The match must
already be in your stream queue.

        The first set given is the one you want to move, the second is the position you want.

        If you want to edit someone else's stream, give its channel as the first argument.

        Examples:
        - `[p]stream insert 252 254`
        - `[p]stream insert https://twitch.tv/el_laggron 252 254`
        """
        tournament = self.tournaments[ctx.guild.id]
        streamer = await self._get_streamer_from_ctx(ctx, streamer)
        if not streamer:
            return
        try:
            streamer.insert_match(set1, set2=set2)
        except KeyError:
            await ctx.send(_("One of the provided sets cannot be found."))
        else:
            await ctx.tick()
        if tournament.status != "ongoing":
            await tournament.save()

    @only_phase()
    @stream.command(name="info")
    @commands.check(mod_or_streamer)
    async def stream_info(
        self,
        ctx: commands.Context,
        streamer: Optional[TwitchChannelConverter],
    ):
        """
        Shows infos about a stream.

        If you want to view someone else's stream info, give its channel as the first argument.

        Examples:
        - `[p]stream info`
        - `[p]stream info https://twitch.tv/el_laggron`
        """
        streamer = await self._get_streamer_from_ctx(ctx, streamer)
        if not streamer:
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
                name=_("List of sets"),
                value=sets or _("Nothing set."),
                inline=False,
            )
            await ctx.send(embed=embed)
        else:
            embeds = []
            for page in pagify(sets):
                _embed = deepcopy(embed)
                _embed.add_field(
                    name=_("List of sets"),
                    value=page,
                    inline=False,
                )
                embeds.append(_embed)
            await menus.menu(ctx, embeds, controls=menus.DEFAULT_CONTROLS)

    @only_phase()
    @stream.command(name="end")
    @commands.check(mod_or_streamer)
    async def stream_end(
        self,
        ctx: commands.Context,
        streamer: Optional[TwitchChannelConverter],
    ):
        """
        Closes a stream.

        If you want to close someone else's stream info, give its channel as the first argument.

        Examples:
        - `[p]stream end`
        - `[p]stream end https://twitch.tv/el_laggron`
        """
        streamer = await self._get_streamer_from_ctx(ctx, streamer)
        if not streamer:
            return
        tournament = self.tournaments[ctx.guild.id]
        await streamer.end()
        tournament.streamers.remove(streamer)
        if tournament.status != "ongoing":
            await tournament.save()
        await ctx.tick()
