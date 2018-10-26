# BetterMod by retke, aka El Laggron
import discord
import logging
import re

from typing import Union, TYPE_CHECKING
from asyncio import TimeoutError as AsyncTimeoutError
from datetime import timedelta

from redbot.core import commands, Config, checks
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import predicates, menus, mod, chat_formatting

# from redbot.core.errors import BadArgument as RedBadArgument

# creating this before importing other modules allows to import the translator
_ = Translator("BetterMod", __file__)

from .api import API
from . import errors

if TYPE_CHECKING:
    from .loggers import Log

log = None
BaseCog = getattr(commands, "Cog", object)


# from Cog-Creators/Red-DiscordBot#2140
TIME_RE_STRING = r"\s?".join(
    [
        r"((?P<days>\d+?)\s?(d(ays?)?))?",
        r"((?P<hours>\d+?)\s?(hours?|hrs|hr?))?",
        r"((?P<minutes>\d+?)\s?(minutes?|mins?|m))?",
        r"((?P<seconds>\d+?)\s?(seconds?|secs?|s))?",
    ]
)
TIME_RE = re.compile(TIME_RE_STRING, re.I)


class RedBadArgument(Exception):
    """For testing, wait for release with errors.py"""

    pass


def timedelta_converter(argument: str) -> timedelta:
    """
    Attempts to parse a user input string as a timedelta
    Arguments
    ---------
    argument: str
        String to attempt to treat as a timedelta
    Returns
    -------
    datetime.timedelta
        The parsed timedelta

    Raises
    ------
    ~discord.ext.commands.BadArgument
        No time was found from the given string.
    """
    matches = TIME_RE.match(argument)
    params = {k: int(v) for k, v in matches.groupdict().items() if v is not None}
    if not params:
        raise RedBadArgument("I couldn't turn that into a valid time period.")
    return timedelta(**params)


EMBED_MODLOG = lambda x: _("A member got a level {} warning.").format(x)
EMBED_USER = lambda x: _("The moderation team set you a level {} warning.").format(x)


@cog_i18n(_)
class BetterMod(BaseCog):
    """
    An alternative to the Red core moderation system, providing a different system of moderation\
    similar to Dyno.

    Report a bug or ask a question: https://discord.gg/AVzjfpR
    Full documentation and FAQ: http://laggron.red/bettermod.html
    """

    default_global = {"enable_sentry": None}
    default_guild = {
        "delete_message": False,  # if the [p]warn commands should delete the context message
        "show_mod": False,  # if the responsible mod should be revealed to the warned user
        "mute_role": None,  # the role used for mute
        "respect_hierarchy": False,  # if the bot should check if the mod is allowed by hierarchy
        "reinvite": True,  # if the bot should try to send an invite to an unbanned/kicked member
        "channels": {  # modlog channels
            "main": None,  # default
            "report": None,
            "1": None,
            "2": None,
            "3": None,
            "4": None,
            "5": None,
        },
        "bandays": {  # the number of days of messages to delte in case of a ban/softban
            "softban": 7,
            "ban": 0,
        },
        "embed_description_modlog": {  # the description of each type of warn in modlog
            "1": EMBED_MODLOG(1),
            "2": EMBED_MODLOG(2),
            "3": EMBED_MODLOG(3),
            "4": EMBED_MODLOG(4),
            "5": EMBED_MODLOG(5),
        },
        "embed_description_user": {  # the description of each type of warn for the user
            "1": EMBED_USER(1),
            "2": EMBED_USER(2),
            "3": EMBED_USER(3),
            "4": EMBED_USER(4),
            "5": EMBED_USER(5),
        },
        "substitutions": {},
        "thumbnails": {  # image at the top right corner of an embed
            "report": "https://i.imgur.com/Bl62rGd.png",
            "1": "https://i.imgur.com/Bl62rGd.png",
            "2": "https://i.imgur.com/cVtzp1M.png",
            "3": "https://i.imgur.com/uhrYzyt.png",
            "4": "https://i.imgur.com/uhrYzyt.png",
            "5": "https://i.imgur.com/DfBvmic.png",
        },
        "colors": {  # color bar of an embed
            "report": 0xF4AA42,
            "1": 0xD1ED35,
            "2": 0xEDCB35,
            "3": 0xED9735,
            "4": 0xED6F35,
            "5": 0xFF4C4C,
        },
        "url": None,  # URL set for the title of all embeds
        "temporary_warns": [],  # list of temporary warns (need to unmute/unban after some time)
    }
    default_custom_member = {"x": []}  # cannot set a list as base group

    def __init__(self, bot):
        self.bot = bot

        self.data = Config.get_conf(self, 260, force_registration=True)
        self.data.register_global(**self.default_global)
        self.data.register_guild(**self.default_guild)
        self.data.register_custom("MODLOGS", **self.default_custom_member)

        self.api = API(bot, self.data)
        self.errors = errors
        self.sentry = None
        self.translator = _

        self.task = bot.loop.create_task(self.api._loop_task())

    __version__ = "indev"
    __author__ = "retke (El Laggron)"

    # helpers
    def _set_log(self, sentry: "Log"):
        self.sentry = sentry
        global log
        log = logging.getLogger("laggron.bettermod")
        # this is called now so the logger is already initialized

    async def call_warn(self, ctx, level, member, reason, time=None):
        """No need to repeat, let's do what's common to all 5 warnings."""
        reason = await self.api.format_reason(ctx.guild, reason)
        if len(reason) > 1024:  # embed limits
            await ctx.send(
                _(
                    "The reason is too long for an embed.\n\n"
                    "*Tip: You can use Github Gist to write a long text formatted in Markdown, "
                    "create a new file with the extension `.md` at the end and write as if you "
                    "were on Discord.\n<https://gist.github.com/>*"
                    # I was paid $99999999 for this, you're welcome
                )
            )
            return
        try:
            await self.api.warn(ctx.guild, member, ctx.author, level, reason, time)
        except errors.MissingPermissions as e:
            await ctx.send(e)
        except errors.MemberTooHigh as e:
            await ctx.send(e)
        except errors.MissingMuteRole:
            await ctx.send(
                _(
                    "You need to set up the mute role before doing this.\n"
                    "Use the `[p]bmodset mute` command for this."
                )
            )
        except errors.NotFound:
            await ctx.send(
                _(
                    "Please set up a modlog channel before warning a member.\n\n"
                    "**With BetterMod**\n"
                    "*Use the `[p]bmodset channel` command.*\n\n"
                    "**With Red Modlog**\n"
                    "*Load the `modlogs` cog and use the `[p]modlogset modlog` command.*"
                )
            )
        except errors.NotAllowedByHierarchy:
            is_admin = mod.is_admin_or_superior(member)
            await ctx.send(
                _(
                    "You are not allowed to do this, {member} is higher than you in the role "
                    "hierarchy. You can only warn members which top role is lower than yours.\n\n"
                ).format(member=str(member))
                + (
                    _("You can disable this check by using the `[p]bmodset hierarchy` command.")
                    if is_admin
                    else ""
                )
            )
        if await self.data.guild(ctx.guild).delete_message():
            await ctx.message.delete()

    # all settings
    @commands.group()
    @checks.admin_or_permissions(administrator=True)
    async def bmodset(self, ctx: commands.Context):
        """
        Set all BetterMod settings.

        For more informations about how to configure and use BetterMod, read the wiki:\
        https://laggron.red/bettermod.html
        """
        pass

    # goes from most basic to advanced settings
    @bmodset.command(name="channel")
    async def bmodset_channel(
        self, ctx: commands.Context, channel: discord.TextChannel, level: int = None
    ):
        """
        Set the channel for the BetterMod modlog.

        This will use the Red's modlog by default if it was set.

        All warnings will be logged here.
        I need the `Send Messages` and `Embed Links` permissions.

        If you want to set one channel for a specific level of warning, you can specify a\
        number after the channel
        """
        guild = ctx.guild
        if not channel.permissions_for(guild.me).send_messages:
            await ctx.send(_("I don't have the permission to send messages in that channel."))
        elif not channel.permissions_for(guild.me).embed_links:
            await ctx.send(_("I don't have the permissions to send embed links in that channel."))
        else:
            if not level:
                await self.data.guild(guild).channels.main.set(channel.id)
                await ctx.send(
                    _(
                        "Done. All events will be send to that channel by default.\n\nIf you want "
                        "to send a specific warning level in a different channel, you can use the "
                        "same command with the number after the channel.\nExample: "
                        "`{prefix}bmodset channel #your-channel 3`"
                    ).format(prefix=ctx.prefix)
                )
            elif not 1 <= level <= 5:
                await ctx.send(
                    _(
                        "If you want to specify a level for the channel, provide a number between "
                        "1 and 5."
                    )
                )
            else:
                await self.data.guild(guild).channels.set_raw(level, value=channel.id)
                await ctx.send(
                    _(
                        "Done. All level {level} warnings events will be sent to that channel."
                    ).format(level=str(level))
                )

    @bmodset.command(name="mute")
    async def bmodset_mute(self, ctx: commands.Context, *, role: discord.Role = None):
        """
        Create the role used for muting members.

        You can specify a role when invoking the command to specify which role should be used.
        If you don't specify a role, one will be created for you.
        """
        guild = ctx.guild
        my_position = guild.me.top_role.position
        if not role:
            if not guild.me.guild_permissions.manage_roles:
                await ctx.send(
                    _("I can't manage roles, please give me this permission to continue.")
                )
                return
            role = await self.api.maybe_create_mute_role(guild)
            if not role:
                await ctx.send(
                    _(
                        "A mute role was already created! You can change it by specifying "
                        "a role when typing the command.\n`[p]bmodset mute <role name>`"
                    )
                )
                return
            else:
                if isinstance(role, list):
                    errors = _(
                        "\n\nSome errors occured when editing the channel permissions:\n"
                    ) + "\n".join(role)
                else:
                    errors = ""
                await ctx.send(
                    _(
                        "The role `Muted` was successfully created at position {pos}. Feel free "
                        "to drag it in the hierarchy and edit its permissions, as long as my "
                        "top role is above and the members to mute are below."
                    ).format(pos=my_position - 1)
                    + errors
                )
        elif role.position >= my_position:
            await ctx.send(
                _(
                    "That role is higher than my top role in the hierarchy. "
                    'Please move it below "{bot_role}".'
                ).format(bot_role=guild.me.top_role.name)
            )
        else:
            await self.data.guild(guild).mute_role.set(role.id)
            await ctx.send(_("The new mute role was successfully set!"))

    @bmodset.command(name="hierarchy")
    async def bmodset_hierarchy(self, ctx: commands.Context, enable: bool = None):
        """
        Set if the bot should respect roles hierarchy.

        If enabled, a member cannot ban another member above him in the roles hierarchy, like\
        with manual bans.
        If disabled, mods can ban everyone while the bot can.

        Invoke the command without arguments to get the current status.
        """
        guild = ctx.guild
        current = await self.data.guild(guild).respect_hierarchy()
        if enable is None:
            await ctx.send(
                _(
                    "The bot currently {respect} role hierarchy. If you want to change this, "
                    "type `[p]bmodset hierarchy {opposite}`."
                ).format(
                    respect=_("respects") if current else _("doesn't respect"),
                    opposite=not current,
                )
            )
        elif enable:
            await self.data.guild(guild).respect_hierarchy.set(True)
            await ctx.send(
                _(
                    "Done. Moderators will not be able to take actions on the members higher "
                    "than himself in the role hierarchy of the server."
                )
            )
        else:
            await self.data.guild(guild).respect_hierarchy.set(False)
            await ctx.send(
                _(
                    "Done. Moderators will be able to take actions on anyone on the server, as "
                    "long as the bot is able to do so."
                )
            )

    @bmodset.command(name="reinvite")
    async def bmodset_reinvite(self, ctx: commands.Context, enable: bool = None):
        """
        Set if the bot should send an invite after a temporary ban.

        If enabled, any unbanned member will receive a DM with an invite to join the server back.
        The bot needs to share a server with the member to send a DM.

        Invoke the command without arguments to get the current status.
        """
        guild = ctx.guild
        current = await self.data.guild(guild).reinvite()
        if enable is None:
            await ctx.send(
                _(
                    "The bot {respect} reinvite unbanned members. If you want to "
                    "change this, type `[p]bmodset reinvite {opposite}`."
                ).format(respect=_("does") if current else _("doesn't"), opposite=not current)
            )
        elif enable:
            await self.data.guild(guild).reinvite.set(True)
            await ctx.send(
                _(
                    "Done. The bot will try to send an invite to unbanned members. Please note "
                    "that the bot needs to share one server in common with the member to receive "
                    "the message."
                )
            )
        else:
            await self.data.guild(guild).reinvite.set(False)
            await ctx.send(_("Done. The bot will no longer reinvite unbanned members."))

    @bmodset.group(name="substitutions")
    async def bmodset_substitutions(self, ctx: commands.Context):
        """
        Manage the reasons' substitutions

        A substitution is a text replaced by a key you place in your warn reason.

        For example, if you set a substitution with the keyword `last warn` associated with the\
        text `This is your last warning!`, this is what will happen with your next warnings:

        `[p]warn 4 @annoying_member Stop spamming. [last warn]`
        Reason = Stop spamming. This is your last warning!
        """
        pass

    @bmodset_substitutions.command(name="add")
    async def bmodset_substitutions_add(self, ctx: commands.Context, name: str, *, text: str):
        """
        Create a new subsitution.

        `name` should be something short, it will be the keyword that will be replaced by your text
        `text` is what will be replaced by `[name]`

        Example:
        - `[p]bmodset substitutions add ad Advertising for a Discord server`
        - `[p]warn 1 @noob [ad] + doesn't respect warnings`
        The reason will be "Advertising for a Discord server + doen't respect warnings".
        """
        async with self.data.guild(ctx.guild).substitutions() as substitutions:
            if name in substitutions:
                await ctx.send(
                    _(
                        "The name you're using is already used by another substitution!\n"
                        "Delete or edit it with `[p]bmodset substitutions delete`"
                    )
                )
                return
            if len(text) > 600:
                await ctx.send(_("That substitution is too long! Maximum is 600 characters!"))
                return
            substitutions[name] = text
        await ctx.send(
            _(
                "Your new subsitutions with the keyword `{keyword}` was successfully "
                "created! Type `[{substitution}]` in your warning reason to use the text you "
                "just set.\nManage your substitutions with the `{prefix}bmodset "
                "substitutions` subcommands."
            ).format(keyword=name, substitution=name, prefix=ctx.prefix)
        )

    @bmodset_substitutions.command(name="delete", aliases=["del"])
    async def bmodset_substitutions_delete(self, ctx: commands.Context, name: str):
        """
        Delete a previously set substitution.

        The substitution must exist, see existing substitutions with the `[p]bmodset substitutions\
        list` command.
        """
        async with self.data.guild(ctx.guild).substitutions() as substitutions:
            if name not in substitutions:
                await ctx.send(
                    _(
                        "That substitution doesn't exist!\nSee existing substitutions with the "
                        "`{prefix}bmodset substitutions list` command."
                    ).format(prefix=ctx.prefix)
                )
            del substitutions[name]
        await ctx.send(_("The substitutions was successfully deleted."))

    @bmodset_substitutions.command(name="list")
    async def bmodset_substitutions_list(self, ctx: commands.Context):
        """
        List all existing substitutions on your server
        """
        guild = ctx.guild
        substitutions = await self.data.guild(guild).substitutions()
        if len(substitutions) < 1:
            await ctx.send(
                _(
                    "You don't have any existing substitution on this server!\n"
                    "Create one with `{prefix}bmodset substitutions add`"
                ).format(prefix=ctx.prefix)
            )
            return
        embeds = []
        while True:
            embed = discord.Embed()
            embed.set_author(
                name=_("Substitutions for {guild}").format(guild=guild), icon_url=guild.icon_url
            )
            for i, (a, b) in enumerate(substitutions.items()):
                embed.add_field(name=a, value=b, inline=False)
                if i >= 25:
                    break
            embeds.append(embed)
        await menus.menu(ctx, embeds, controls=menus.DEFAULT_CONTROLS)

    @bmodset.command(name="showmod")
    async def bmodset_showmod(self, ctx, enable: bool = None):
        """
        Defines if the responsible moderator should be revealed to the warned member in DM.

        If enabled, any warned member will be able to see who warned him, else he won't know.

        Invoke the command without arguments to get the current status.
        """
        guild = ctx.guild
        current = await self.data.guild(guild).show_mod()
        if enable is None:
            await ctx.send(
                _(
                    "The bot {respect} show the responsible moderator to the warned member in DM. "
                    "If you want to change this, type `[p]bmodset reinvite {opposite}`."
                ).format(respect=_("does") if current else _("doesn't"), opposite=not current)
            )
        elif enable:
            await self.data.guild(guild).reinvite.set(True)
            await ctx.send(
                _(
                    "Done. The moderator responsible of a warn will now be shown to the warned "
                    "member in direct messages."
                )
            )
        else:
            await self.data.guild(guild).reinvite.set(False)
            await ctx.send(_("Done. The bot will no longer show the responsible moderator."))

    @bmodset.command(name="description")
    async def bmodset_description(
        self, ctx: commands.Context, level: int, destination: str, *, description: str
    ):
        """
        Set a custom description for the modlog embeds.

        You can set the description for each type of warning, one for the user in DM\
        and the other for the server modlog.

        __Keys:__

        You can include these keys in your message:

        - `{invite}`: Generate an invite for the server
        - `{member}`: The warned member (tip: you can use `{member.id}` for the member's ID or\
        `{member.mention}` for a mention)
        - `{mod}`: The moderator that warned the member (you can also use keys like\
        `{moderator.id}`)
        - `{duration}`: The duration of a timed mute/ban if it exists
        - `{time}`: The current date and time.

        __Examples:__

        - `[p]bmodset description 1 user You were warned by a moderator for your behaviour,\
        please read the rules.`
          This set the description for the first warning for the warned member.

        - `[p]bmodset description 3 modlog A member was kicked from the server.`
          This set the description for the 3rd warning (kick) for the modlog.

        - `[p]bmodset description 4 user You were banned and unbanned to clear your messages\
        from the server. You can join the server back with this link: {invite}`
          This set the description for the 4th warning (softban) for the user, while generating\
          an invite which will be replace `{invite}`
        """
        guild = ctx.guild
        if not any([destination == x for x in ["modlog", "user"]]):
            await ctx.send(
                _(
                    "You need to specify `modlog` or `user`. Read the help of "
                    "the command for more details."
                )
            )
            return
        if len(description) > 800:
            await ctx.send("Your text is too long!")
            return
        await self.data.guild(guild).set_raw(
            "embed_description_" + destination, str(level), value=description
        )
        await ctx.send(
            _("The new description for {destination} (warn {level}) was successfully set!")
        ).format(destination=_("modlog") if destination == "modlog" else _("user"), level=level)

    @bmodset.group(name="data")
    async def bmodset_data(self, ctx: commands.Context):
        """
        Manage your data.
        """
        await ctx.send("The work is in progress for this command...")
        # this should be included later, to know if some things are at least possible

    # all warning commands
    @commands.group()
    @checks.mod_or_permissions(administrator=True)
    @commands.guild_only()
    async def warn(self, ctx: commands.Context):
        """
        Take actions against a user and log it.
        The warned user will receive a DM.
        """
        pass

    @warn.command(name="1", aliases=["simple"])
    async def warn_1(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        """
        Set a simple warning on a user.
        """
        await self.call_warn(ctx, 1, member, reason)
        if ctx.message:
            await ctx.message.add_reaction("✅")

    @warn.command(name="2", aliases=["mute"], usage="<member> [time] <reason>")
    async def warn_2(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        """
        Mute the user in all channels, including voice channels.

        This mute will use a role that will automatically be created, if it was not already done.
        Feel free to edit the role's permissions and move it in the roles hierarchy.

        You can set a timed mute by providing a valid time before the reason. Unmute the user with\
        the `[p]

        Examples:
        - `[p]warn 2 @user 30m`: 30 minutes mute
        - `[p]warn 2 @user 5h Spam`: 5 hours mute for the reason "Spam"
        - `[p]warn 2 @user Advertising`: Infinite mute for the reason "Advertising"
        """
        time = None
        potential_time = reason.split()[0]
        try:
            time = timedelta_converter(potential_time)
        except RedBadArgument:
            pass
        else:
            reason = " ".join(reason.split()[1:])  # removes time from string
        await self.call_warn(ctx, 2, member, reason, time)
        if ctx.message:
            await ctx.message.add_reaction("✅")

    @warn.command(name="3", aliases=["kick"])
    async def warn_3(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        """
        Kick the member from the server.

        You can include an invite for the server in the message received by the kicked user by\
        using the `[p]bmodset reinvite` command.
        """
        await self.call_warn(ctx, 3, member, reason)
        if ctx.message:
            await ctx.message.add_reaction("✅")

    @warn.command(name="4", aliases=["softban"])
    async def warn_4(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        """
        Softban the member from the server.

        This means that the user will be banned and immediately unbanned, so it will purge his\
        messages in all channels.

        It will delete 7 days of messages by default, but you can edit this with the\
        `[p]bmodset bandays` command.
        """
        await self.call_warn(ctx, 4, member, reason)
        if ctx.message:
            await ctx.message.add_reaction("✅")

    @warn.command(name="5", aliases=["ban"], usage="<member> [time] <reason>")
    async def warn_5(
        self, ctx: commands.Context, member: Union[discord.Member, int], *, reason: str
    ):
        """
        Ban the member from the server.

        This ban can be a normal ban, a temporary ban or a hack ban (bans a user not in the\
        server).
        It won't delete messages by default, but you can edit this with the `[p]bmodset bandays`\
        command.

        If you want to perform a temporary ban, provide the time before the reason. A hack ban\
        needs a user ID, you can get it with the Developer mode (enable it in the Appearance tab\
        of the user settings, then right click on the user and select "Copy ID").

        Examples:
        - `[p]warn 5 @user`: Ban for no reason :c
        - `[p]warn 5 @user 7d Insults`: 7 days ban for the reason "Insults"
        - `[p]warn 5 012345678987654321 Advertising and leave`: Ban the user with the ID provided\
        while he's not in the server for the reason "Advertising and leave" (if the user shares\
        another server with the bot, a DM will be sent).
        """
        time = None
        potential_time = reason.split()[0]
        try:
            time = timedelta_converter(potential_time)
        except RedBadArgument:
            pass
        else:
            reason = " ".join(reason.split()[1:])  # removes time from string
        await self.call_warn(ctx, 5, member, reason, time)
        if ctx.message:
            await ctx.message.add_reaction("✅")

    # other moderation commands
    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.channel)
    async def slowmode(
        self, ctx: commands.Context, time: int, channel: discord.TextChannel = None
    ):
        """
        Set the Discord slowmode in a text channel.

        When sending a message, users will have to wait for the time you set before sending\
        another message. This can reduce spam.

        The slowmode is between 1 and 120 seconds and is included in the user client.
        You can specify a channel. If not, the slowmode will be applied in the current channel.

        Type `[p]slowmode 0` to disable. Note: `[p]slowoff` is an alias of `[p]slowmode 0`.
        """
        pass

    @commands.command(hidden=True)
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.channel)
    async def slowoff(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """
        An alias to `[p]slowmode 0`
        """
        slowmode = self.bot.get_command("slowmode")
        channel = ctx.channel if not channel else channel
        await ctx.invoke(slowmode, time=0, channel=channel)

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(5, 60, commands.BucketType.member)  # no more spike in the API response time
    async def report(self, ctx: commands.Context, user: discord.Member = None, reason: str = None):
        """
        Report a member to the moderation team.

        You can attach files to your report. For that, drag files to Discord and type the command\
        as the file comment.

        Depending on the server settings, attaching a file to your report can be required.
        """
        pass

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(add_reactions=True, manage_messages=True)
    @commands.cooldown(1, 3, commands.BucketType.member)
    async def warnings(
        self, ctx: commands.Context, user: Union[discord.User, int] = None, index: int = 0
    ):
        """
        Shows all warnings of a member.

        This command can be used by everyone, but only moderators can see other's warnings.
        Moderators can also edit or delete warnings by using the reactions.
        """
        if not user:
            await ctx.send_help()
            return
        if isinstance(user, int):
            try:
                user = self.bot.get_user_info(user)
            except discord.errors.NotFound:
                await ctx.send(_("User not found."))
                return
        if not await mod.is_mod_or_superior(self.bot, ctx.author) and user != ctx.author:
            await ctx.send(_("You are not allowed to see other's warnings!"))
            return
        cases = await self.api.get_all_cases(ctx.guild, user)
        if not cases:
            await ctx.send(_("That member was never warned."))
            return
        if 0 < index < len(cases):
            await ctx.send(_("That case doesn't exist."))

        total = lambda level: len([x for x in cases if x["level"] == level])
        warning_str = (
            lambda x: _("Mute")
            if x == 2
            else _("Kick")
            if x == 3
            else _("Softban")
            if x == 4
            else _("Ban")
            if x == 5
            else _("Warning")
        )

        embeds = []
        msg = []
        for i in range(6):
            total_warns = total(i)
            if total_warns > 0:
                msg.append(
                    _(
                        "{action}{plural}: {number}".format(
                            action=warning_str(i),
                            plural=_("s") if total_warns > 1 else "",
                            number=total_warns,
                        )
                    )
                )
        warn_field = "\n".join(msg) if len(msg) > 1 else msg[0]
        embed = discord.Embed(description=_("User modlog summary."))
        embed.set_author(name=f"{user} | {user.id}", icon_url=user.avatar_url)
        embed.add_field(name=_("Total number of warnings: ") + str(len(cases)), value=warn_field)
        embed.set_footer(text=_("Click on the reactions to scroll through the warnings"))
        embeds.append(embed)

        for i, case in enumerate(cases):
            level = case["level"]
            moderator = ctx.guild.get_member(case["author"])
            moderator = "ID: " + case["author"] if not moderator else moderator.mention

            embed = discord.Embed(
                description=_("Case #{number} informations").format(number=i + 1)
            )
            embed.set_author(name=f"{user} | {user.id}", icon_url=user.avatar_url)
            embed.add_field(name=_("Level"), value=f"{warning_str(level)} ({level})", inline=True)
            embed.add_field(name=_("Moderator"), value=moderator, inline=True)
            if case["duration"]:
                embed.add_field(
                    name=_("Duration"),
                    value=_("{duration}\n(Until {date})").format(
                        duration=case["duration"], date=case["until"]
                    ),
                )
            embed.add_field(name=_("Reason"), value=case["reason"], inline=False),
            embed.set_footer(text=_("The action was taken on {date}").format(date=case["time"]))
            embed.color = await self.data.guild(ctx.guild).colors.get_raw(level)

            embeds.append(embed)

        controls = {"⬅": menus.prev_page, "❌": menus.close_menu, "➡": menus.next_page}
        if await mod.is_mod_or_superior(self.bot, ctx.author) and user != ctx.author:
            controls.update({"✏": self._edit_case, "🗑": self._delete_case})

        await menus.menu(
            ctx=ctx, pages=embeds, controls=controls, message=None, page=index, timeout=60
        )

    async def _edit_case(
        self,
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float,
        emoji: str,
    ):
        """
        Edit a case, this is linked to the warnings menu system.
        """
        guild = ctx.guild
        if page == 0:
            # first page, no case to edit
            await message.remove_reaction(emoji, ctx.author)
            return await menus.menu(
                ctx, pages, controls, message=message, page=page, timeout=timeout
            )
        await message.clear_reactions()
        embed = message.embeds[0]
        member = await self.bot.get_user_info(
            int(embed.author.name.rpartition("|")[2].replace(" ", ""))
        )
        embed.clear_fields()
        embed.description = _(
            "Case #{number} edition.\n\n**Please type the new reason to set**"
        ).format(number=page)
        embed.set_footer(text=_("You have two minuts to type your text in the chat."))
        case = (await self.data.custom("MODLOGS", guild.id, member.id).x())[page - 1]
        await message.edit(embed=embed)
        try:
            response = await self.bot.wait_for(
                "message", check=predicates.MessagePredicate.same_context(ctx), timeout=120
            )
        except AsyncTimeoutError:
            await message.delete()
            return
        new_reason = await self.api.format_reason(guild, response.content)
        embed.description = _("Case #{number} edition.").format(number=page)
        embed.add_field(name=_("Old reason"), value=case["reason"], inline=False)
        embed.add_field(name=_("New reason"), value=new_reason, inline=False)
        embed.set_footer(text=_("Click on ✅ to confirm the changes."))
        await message.edit(embed=embed)
        await menus.start_adding_reactions(message, predicates.ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = predicates.ReactionPredicate.yes_or_no(message, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
        except AsyncTimeoutError:
            await message.clear_reactions()
            await message.edit(content=_("Question timed out."), embed=None)
            return
        if pred.result:
            async with self.data.custom("MODLOGS", guild.id, member.id).x() as logs:
                logs[page - 1]["reason"] = new_reason
            await message.clear_reactions()
            await message.edit(content=_("The reason was successfully edited!"), embed=None)
        else:
            await message.clear_reactions()
            await message.edit(content=_("The reason was not edited."), embed=None)

    async def _delete_case(
        self,
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float,
        emoji: str,
    ):
        """
        Remove a case, this is linked to the warning system.
        """
        guild = ctx.guild
        if page == 0:
            await message.remove_reaction(emoji, ctx.author)
            return await menus.menu(
                ctx, pages, controls, message=message, page=page, timeout=timeout
            )
        await message.clear_reactions()
        embed = message.embeds[0]
        member = await self.bot.get_user_info(
            int(embed.author.name.rpartition("|")[2].replace(" ", ""))
        )
        embed.clear_fields()
        embed.set_footer(text="")
        embed.description = _(
            "Case #{number} deletion.\n\n**Click on the reaction to confirm your action.**"
        ).format(number=page)
        await message.edit(embed=embed)
        await menus.start_adding_reactions(message, predicates.ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = predicates.ReactionPredicate.yes_or_no(message, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
        except AsyncTimeoutError:
            await message.clear_reactions()
            await message.edit(content=_("Question timed out."), embed=None)
            return
        if pred.result:
            async with self.data.custom("MODLOGS", guild.id, member.id).x() as logs:
                logs.remove(logs[page - 1])
            await message.clear_reactions()
            await message.edit(content=_("The case was successfully deleted!"), embed=None)
        else:
            await message.clear_reactions()
            await message.edit(content=_("The case was not deleted."), embed=None)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def bettermodinfo(self, ctx, sentry: str = None):
        """
        Get informations about the cog.

        Type `sentry` after your command to modify its status.
        """
        current_status = await self.data.enable_sentry()
        status = lambda x: _("enable") if x else _("disable")

        if sentry is not None and "sentry" in sentry:
            await ctx.send(
                _(
                    "You're about to {} error logging. Are you sure you want to do this? Type "
                    "`yes` to confirm."
                ).format(status(not current_status))
            )
            predicate = predicates.MessagePredicate.yes_or_no(ctx)
            try:
                await self.bot.wait_for("message", timeout=60, check=predicate)
            except AsyncTimeoutError:
                await ctx.send(_("Request timed out."))
            else:
                if predicate.result:
                    await self.data.enable_sentry.set(not current_status)
                    if not current_status:
                        # now enabled
                        self.sentry.enable()
                        await ctx.send(
                            _(
                                "Upcoming errors will be reported automatically for a faster fix. "
                                "Thank you for helping me with the development process!"
                            )
                        )
                    else:
                        # disabled
                        self.sentry.disable()
                        await ctx.send(_("Error logging has been disabled."))
                    log.info(
                        f"Sentry error reporting was {status(not current_status)}d "
                        "on this instance."
                    )
                else:
                    await ctx.send(
                        _("Okay, error logging will stay {}d.").format(status(current_status))
                    )
                return

        message = _(
            "Laggron's Dumb Cogs V3 - bettermod\n\n"
            "Version: {0.__version__}\n"
            "Author: {0.__author__}\n"
            "Sentry error reporting: {1}d (type `{2}bettermodinfo sentry` to change this)\n\n"
            "Github repository: https://github.com/retke/Laggrons-Dumb-Cogs/tree/v3\n"
            "Discord server: https://discord.gg/AVzjfpR\n"
            "Documentation: http://laggrons-dumb-cogs.readthedocs.io/\n\n"
            "Support my work on Patreon: https://www.patreon.com/retke"
        ).format(self, status(current_status), ctx.prefix)
        await ctx.send(message)

    # error handling
    def _set_context(self, data):
        self.sentry.client.extra_context(data)

    async def on_command_error(self, ctx, error):
        if not isinstance(error, commands.CommandInvokeError):
            return
        if not ctx.command.cog_name == self.__class__.__name__:
            # That error doesn't belong to the cog
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(
                _(
                    "I need the `Add reactions` and `Manage messages` in the "
                    "current channel if you want to use this command."
                )
            )
        messages = "\n".join(
            [
                f"{x.author} %bot%: {x.content}".replace("%bot%", "(Bot)" if x.author.bot else "")
                for x in await ctx.history(limit=5, reverse=True).flatten()
            ]
        )
        log.propagate = False  # let's remove console output for this since Red already handle this
        context = {
            "command": {
                "invoked": f"{ctx.author} (ID: {ctx.author.id})",
                "command": f"{ctx.command.name} (cog: {ctx.cog})",
                "arguments": ctx.kwargs,
            }
        }
        if ctx.guild:
            context["guild"] = f"{ctx.guild.name} (ID: {ctx.guild.id})"
        self._set_context(context)
        log.error(
            f"Exception in command '{ctx.command.qualified_name}'.\n\n"
            f"Myself: {ctx.me}\n"
            f"Last 5 messages:\n\n{messages}\n\n",
            exc_info=error.original,
        )
        log.propagate = True  # re-enable console output for warnings
        self._set_context({})  # remove context for future logs

    # correctly unload the cog
    def __unload(self):
        log.debug("Cog unloaded from the instance.")

        # remove all handlers from the logger, this prevents adding
        # multiple times the same handler if the cog gets reloaded
        log.handlers = []

        # stop checking for unmute and unban
        self.task.cancel()
