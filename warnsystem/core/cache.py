import discord
import logging
import contextlib

from redbot.core import Config
from redbot.core.bot import Red

from typing import List, Mapping, Optional

from warnsystem.core.warning import Warning

log = logging.getLogger("red.laggron.warnsystem")


class MemoryCache:
    """
    This class is used to store most used Config values and reduce calls for optimization.
    See Github issue #49
    """

    def __init__(self, bot: Red, config: Config):
        self.bot = bot
        self.data = config

        self.mute_roles: Mapping[discord.Guild, discord.Role] = {}
        self.temp_actions: Mapping[discord.Guild, Mapping[discord.Member, Warning]] = {}

    async def _debug_info(self) -> str:
        """
        Compare the cached data to the Config data. Text is logged (INFO) then returned.

        This calls a huge part of the Config database and will not load it into the cache.
        """
        config_data = await self.data.all_guilds()
        mute_roles_cached = len(self.mute_roles)
        mute_roles = len([x for x in config_data.values() if x["mute_role"] is not None])
        guild_temp_actions_cached = len(self.temp_actions)
        guild_temp_actions = len([x for x in config_data.values() if x["temporary_warns"]])
        temp_actions_cached = sum(len(x) for x in self.temp_actions.values())
        temp_actions = sum((len(x["temporary_warns"]) for x in config_data.values()))
        text = (
            f"Debug info requested\n"
            f"{mute_roles_cached}/{mute_roles} mute roles loaded in cache.\n"
            f"{guild_temp_actions_cached}/{guild_temp_actions} guilds "
            "with temp actions loaded in cache.\n"
            f"{temp_actions_cached}/{temp_actions} temporary actions loaded in cache."
        )
        log.info(text)
        return text

    async def get_mute_role(self, guild: discord.Guild) -> discord.Role:
        role = self.mute_roles.get(guild, False)
        if role is not False:
            return role
        role_id = await self.data.guild(guild).mute_role()
        role = guild.get_role(role_id)
        self.mute_roles[guild] = role
        return role

    async def update_mute_role(self, guild: discord.Guild, role: discord.Role):
        await self.data.guild(guild).mute_role.set(role.id)
        self.mute_roles[guild] = role

    async def get_temp_action(self, guild: discord.Guild, member: Optional[discord.Member] = None):
        guild_temp_actions = self.temp_actions.get(guild, None)
        if not guild_temp_actions:
            guild_temp_actions = await self.data.guild(guild).temporary_warns.all()
            if guild_temp_actions:
                self.temp_actions[guild] = guild_temp_actions
        if member is None:
            return guild_temp_actions
        return guild_temp_actions.get(member)

    async def add_temp_action(self, warning: Warning):
        await self.data.guild(warning.guild).temporary_warns.set_raw(
            warning.member.id, value=warning.to_dict
        )
        try:
            guild_temp_actions = self.temp_actions[warning.guild]
        except KeyError:
            self.temp_actions[warning.guild] = {warning.member: warning}
        else:
            guild_temp_actions[warning.member] = warning

    async def remove_temp_action(self, guild: discord.Guild, member: discord.Member):
        await self.data.guild(guild).temporary_warns.clear_raw(member.id)
        with contextlib.suppress(KeyError):
            del self.temp_actions[guild][member]

    async def bulk_remove_temp_action(self, guild: discord.Guild, members: List[discord.Member]):
        members = [x.id for x in members]
        warns = await self.get_temp_action(guild)
        warns = {x: y for x, y in warns.items() if x.id not in members}
        await self.data.guild(guild).temporary_warns.set({x.id: y for x, y in warns.items()})
        self.temp_actions[guild] = warns
