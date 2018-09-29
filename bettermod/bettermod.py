import discord

from typing import Union

from redbot.core import commands, Config, checks
from redbot.core.i18n import Translator, cog_i18n

_ = Translator("BetterMod", __file__)


@cog_i18n(_)
class BetterMod:
    """
    An alternative to the Red core moderation system, providing a different system of moderation\
    similar to Dyno.

    Report a bug or ask a question: https://discord.gg/AVzjfpR
    Full documentation and FAQ: http://laggron.red/bettermod.html
    """

    def __init__(self, bot):
        self.bot = bot
        self.data = Config.get_conf(self, 260, force_registration=True)

    # all settings
    @commands.group()
    @checks.admin_or_permissions(administrator=True)
    async def bmodset(self, ctx: commands.Context):
        """
        Set BetterMod's all settings.

        For more informations about how to configure and use BetterMod, read the wiki:\
        https://laggron.red/bettermod.html

        If you want to set more specific settings than what can be set through command,
        take a look at `[p]bmodset advanced`.
        """
        pass

    @bmodset.command(name="advanced")
    async def bmodset_advanced(self, ctx: commands.Context):
        """
        Edit the advanced settings.

        This includes the following settings:
        - Embed customization for warnings
        - Report customization
        - Modlog channels (one for each type of warning/report)
        - Deletion of message for warn
        """
        pass

    # goes from most basic to advanced settings
    @bmodset.command(name="channel")
    async def bmodset_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Set the channel for the BetterMod modlog.

        This will use the Red's modlog by default if it was set.

        All warnings and reports will be logged here.
        I need the `Send Messages` and `Embed Links` permissions.
        """
        pass

    @bmodset.command(name="mention")
    async def bmodset_mention(
        self, ctx: commands.Context, *roles: Union[discord.Role, discord.Member]
    ):
        """
        Set a list of roles or members to mention when a report is received. @here\
        and @everyone pings are supported.

        If you have roles with spaces, use quote marks or IDs.

        Example:
        `[p]bmodset mention "The Moderators" @RandomUser Admins`
        This will mention 2 roles and RandomUser.
        """
        pass

    @bmodset.command(name="proof")
    async def bmodset_proof(self, ctx: commands.Context, enable: bool = None):
        """
        Set if the bot should require an attachment for a report.

        If enabled, any attachment will be **needed** for using the report command.
        If disabled, it's still possible to attach a file, but not required.
        """
        pass

    @bmodset.command(name="hierarchy")
    async def bmodset_hierarchy(self, ctx: commands.Context, enable: bool = None):
        """
        Set if the bot should respect roles hierarchy.

        If enabled, a member cannot ban another member above him in the roles hierarchy, like\
        with manual bans.
        If disabled, mods can ban everyone while the bot can.
        """
        pass

    @bmodset.command(name="reinvite")
    async def bmodset_reinvite(self, ctx: commands.Context, enable: bool = None):
        """
        Set if the bot should send an invite after a temporary ban.

        If enabled, any unbanned member will receive a DM with an invite to join the server back.
        The bot needs to share a server with the member to send a DM.
        """
        pass

    @bmodset.group(name="data")
    async def bmodset_data(self, ctx: commands.Context):
        """
        Manage your log data.
        """
        pass
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
        pass

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
        pass

    @warn.command(name="3", aliases=["kick"])
    async def warn_3(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        """
        Kick the member from the server.

        You can include an invite for the server in the message received by the kicked user by\
        using the `[p]bmodset reinvite` command.
        """
        pass

    @warn.command(name="4", aliases=["softban"])
    async def warn_4(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        """
        Softban the member from the server.

        This means that the user will be banned and immediately unbanned, so it will purge his\
        messages in all channels.

        It will delete 7 days of messages by default, but you can edit this with the\
        `[p]bmodset bandays` command.
        """
        pass

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
        pass

    # other moderation commands
    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.channel)
    async def slowmode(self, ctx: commands.Context, time: int, channel: discord.TextChannel = None):
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
    @commands.cooldown(1, 30, commands.BucketType.member)
    async def warnings(
        self, ctx: commands.Context, user: Union[discord.User, int] = None, case: int = 0
    ):
        """
        Shows all warnings of a member.

        This command can be used by everyone, but only moderators can see other's warnings.
        Moderators can also edit or delete warnings by using the reactions.
        """
        pass
