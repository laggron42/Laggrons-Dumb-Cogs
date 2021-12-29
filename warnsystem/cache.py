import discord
import logging
import contextlib
import re

from redbot.core import Config
from redbot.core.bot import Red

from typing import Mapping, Optional

log = logging.getLogger("red.laggron.warnsystem")


class MemoryCache:
    """
    This class is used to store most used Config values and reduce calls for optimization.
    See Github issue #49
    """

    def __init__(self, bot: Red, config: Config):
        self.bot = bot
        self.data = config

        self.mute_roles = {}
        self.temp_actions = {}
        self.automod_enabled = []
        self.automod_antispam = {}
        self.automod_regex = {}
        self.automod_regex_edited = []

    async def init_automod_enabled(self):
        for guild_id, data in (await self.data.all_guilds()).items():
            try:
                if data["automod"]["enabled"] is True:
                    self.automod_enabled.append(guild_id)
                if data["automod"]["regex_edited_messages"] is True:
                    self.automod_regex_edited.append(guild_id)
            except KeyError:
                pass

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
            f"{guild_temp_actions_cached}/{guild_temp_actions} guilds with temp actions loaded in cache.\n"
            f"{temp_actions_cached}/{temp_actions} temporary actions loaded in cache."
        )
        log.info(text)
        return text

    async def get_mute_role(self, guild: discord.Guild):
        role_id = self.mute_roles.get(guild.id, False)
        if role_id is not False:
            return role_id
        role_id = await self.data.guild(guild).mute_role()
        self.mute_roles[guild.id] = role_id
        return role_id

    async def update_mute_role(self, guild: discord.Guild, role: discord.Role):
        await self.data.guild(guild).mute_role.set(role.id)
        self.mute_roles[guild.id] = role.id

    async def get_temp_action(self, guild: discord.Guild, member: Optional[discord.Member] = None):
        guild_temp_actions = self.temp_actions.get(guild.id, {})
        if not guild_temp_actions:
            guild_temp_actions = await self.data.guild(guild).temporary_warns.all()
            if guild_temp_actions:
                self.temp_actions[guild.id] = guild_temp_actions
        if member is None:
            return guild_temp_actions
        return guild_temp_actions.get(member.id)

    async def add_temp_action(self, guild: discord.Guild, member: discord.Member, data: dict):
        await self.data.guild(guild).temporary_warns.set_raw(member.id, value=data)
        try:
            guild_temp_actions = self.temp_actions[guild.id]
        except KeyError:
            self.temp_actions[guild.id] = {member.id: data}
        else:
            guild_temp_actions[member.id] = data

    async def remove_temp_action(self, guild: discord.Guild, member: discord.Member):
        await self.data.guild(guild).temporary_warns.clear_raw(member.id)
        with contextlib.suppress(KeyError):
            del self.temp_actions[guild.id][member.id]

    async def bulk_remove_temp_action(self, guild: discord.Guild, members: list):
        members = [x.id for x in members]
        warns = await self.get_temp_action(guild)
        warns = {x: y for x, y in warns.items() if int(x) not in members}
        await self.data.guild(guild).temporary_warns.set(warns)
        self.temp_actions[guild.id] = warns

    def is_automod_enabled(self, guild: discord.Guild):
        return guild.id in self.automod_enabled

    async def add_automod_enabled(self, guild: discord.Guild):
        self.automod_enabled.append(guild.id)
        await self.data.guild(guild).automod.enabled.set(True)

    async def remove_automod_enabled(self, guild: discord.Guild):
        self.automod_enabled.remove(guild.id)
        await self.data.guild(guild).automod.enabled.set(False)

    async def get_automod_antispam(self, guild: discord.Guild):
        automod_antispam = self.automod_antispam.get(guild.id, None)
        if automod_antispam is not None:
            return automod_antispam
        automod_antispam = await self.data.guild(guild).automod.antispam.all()
        if automod_antispam["enabled"] is False:
            self.automod_antispam[guild.id] = False
        else:
            self.automod_antispam[guild.id] = automod_antispam
        return automod_antispam

    async def update_automod_antispam(self, guild: discord.Guild):
        data = await self.data.guild(guild).automod.antispam.all()
        if data["enabled"] is False:
            # if the antispam is disabled, no need to store the entire dict, too heavy
            self.automod_antispam[guild.id] = False
        else:
            self.automod_antispam[guild.id] = data

    async def get_automod_regex(self, guild: discord.Guild):
        automod_regex = self.automod_regex.get(guild.id, {})
        if automod_regex:
            return automod_regex
        automod_regex = await self.data.guild(guild).automod.regex()
        for name, regex in automod_regex.items():
            pattern = re.compile(regex["regex"])
            automod_regex[name]["regex"] = pattern
        self.automod_regex[guild.id] = automod_regex
        return automod_regex

    async def add_automod_regex(
        self,
        guild: discord.Guild,
        name: str,
        regex: re.Pattern,
        level: int,
        time: int,
        reason: str,
    ):
        data = {"regex": regex.pattern, "level": level, "time": time, "reason": reason}
        await self.data.guild(guild).automod.regex.set_raw(name, value=data)
        data["regex"] = regex
        if guild.id not in self.automod_regex:
            self.automod_regex[guild.id] = {name: data}
        else:
            self.automod_regex[guild.id][name] = data

    async def remove_automod_regex(self, guild: discord.Guild, name: str):
        await self.data.guild(guild).automod.regex.clear_raw(name)
        try:
            del self.automod_regex[guild.id][name]
        except KeyError:
            pass

    async def set_automod_regex_edited(self, guild: discord.Guild, enable: bool):
        await self.data.guild(guild).automod.regex_edited_messages.set(enable)
        if enable is False and guild.id in self.automod_regex_edited:
            self.automod_regex_edited.remove(guild.id)
        elif enable is True and guild.id not in self.automod_regex_edited:
            self.automod_regex_edited.append(guild.id)

    def is_automod_regex_edited_enabled(self, guild: discord.Guild):
        return guild.id in self.automod_regex_edited
