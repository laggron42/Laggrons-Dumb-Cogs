import discord
from discord.ext import commands
from .utils.dataIO import dataIO
from .utils import checks
from __main__ import send_cmd_help, settings
from datetime import datetime
from collections import deque, defaultdict
from cogs.utils.chat_formatting import escape_mass_mentions, box, pagify
import os
import re
import logging
import asyncio

default_settings = {
    "mod-log"           : None
}

class BetterMod:
    """Better moderation commands"""

    def __init__(self, bot):
        self.bot = bot
        self.settings = dataIO.load_json('data/bettermod/settings.json')

    @commands.command(pass_context=True)
    async def report(self, ctx, user : discord.Member, *, reason):
        """Report a user to the moderation team"""
        
        message = ctx.message
        channel = self.bot.get_channel("303988901570150401") # don't forget to set ID register
        author = ctx.message.author

        await self.bot.delete_message(message)
        
        e = discord.Embed(color=user.color, description="A user has been report")
        e.title = "Report"
        e.set_footer(text=str(user.name), icon_url = user.avatar_url)
        e.set_thumbnail(url = "https://cdn.discordapp.com/attachments/303988901570150401/342427198269030402/Revitlink2BDamien2BWArnings.png")
        e.add_field(name = "From", value = author.mention, inline = True)
        e.add_field(name = "To", value = user.mention, inline = True)
        e.add_field(name = "Reason", value = reason, inline = False)

        await self.bot.send_message(channel, embed=e)
        await self.bot.say("Your report had been sent")

    @commands.command(pass_context=True, no_pm=True)
    async def chanlog(self, ctx, channel : discord.Channel):
        """Sets a channel as log"""

        server = ctx.message.server
        
        self.settings[server.id]["mod-log"] = channel.id
        await self.bot.say("Mod events will be sent to {}"
                            "".format(channel.mention))
        dataIO.save_json("data/bettermod/settings.json", self.settings)

    @checks.mod_or_permissions(administrator=True)
    @commands.command(pass_context=True)
    async def avert(self, ctx, level : int, user : discord.Member, *, reason):
        """Warn on 4 levels
        1: Simple DM warning
        2: Kick the user
        3: Ban temporarly the user
        4: Ban the user"""
    
        message = ctx.message
        channel = self.bot.get_channel("303988901570150401") # don't forget to set ID register
        author = ctx.message.author
        server = ctx.message.server

        await self.bot.delete_message(message)

        title = "Warning"

        if level is 1:

            mod = discord.Embed(color=user.color, description = "A moderator has give a level 1 warning to a user")
            mod.title = "Warning"
            mod.add_field(name = "Moderator", value = author.mention, inline = True)
            mod.add_field(name = "User", value = user.mention, inline = True)
            mod.add_field(name = "Reason", value = reason, inline = False)
            mod.set_thumbnail(url = "https://cdn.discordapp.com/attachments/303988901570150401/342427198269030402/Revitlink2BDamien2BWArnings.png")
            mod.set_footer(text=str(user.name), icon_url = user.avatar_url)
            
            target = discord.Embed(color = user.color, description = "You have received a level 1 warning")
            target.title = "Warning"
            target.add_field(name = "Reason", value = reason)
            target.set_thumbnail(url = "https://cdn.discordapp.com/attachments/303988901570150401/342427198269030402/Revitlink2BDamien2BWArnings.png")
            target.set_footer(text=str(user.name), icon_url = user.avatar_url)
            
            await self.bot.send_message(user, embed=target)
            await self.bot.send_message(channel, embed=mod)

        if level is 2:

            mod = discord.Embed(color=user.color, description = "A moderator has give a level 2 warning (kick) to a user")
            mod.title = "Warning"
            mod.add_field(name = "Moderator", value = author.mention, inline = True)
            mod.add_field(name = "User", value = user.mention, inline = True)
            mod.add_field(name = "Reason", value = reason, inline = False)
            mod.set_thumbnail(url = "https://cdn.discordapp.com/attachments/303988901570150401/342427198269030402/Revitlink2BDamien2BWArnings.png")
            mod.set_footer(text=str(user.name), icon_url = user.avatar_url)
            
            try:
                invite = await self.bot.create_invite(server, max_uses=1)
                target = discord.Embed(color = user.color, description = "You have received a level 2 warning (kick). You can now join back the server with [this invite](" + invite + ")")

            except:
                target = discord.Embed(color = user.color, description = "You have received a level 2 warning (kick). An invite couldn't be created for you.")
            
            target.title = "Warning"
            target.add_field(name = "Reason", value = reason)
            target.set_thumbnail(url = "https://cdn.discordapp.com/attachments/303988901570150401/342427198269030402/Revitlink2BDamien2BWArnings.png")

            await self.bot.send_message(user, embed=target)

            try:
                await self.bot.kick(user)
                mod.set_footer(text=str(user.name), icon_url = user.avatar_url)

            except:
                await self.bot.say("The user couln't be kicked. Please check my permissions")
                mod.set_footer(text="The user coudn't be kicked. Please check my permissions")

            await self.bot.send_message(channel, embed=mod)

        if level is 3:

            mod = discord.Embed(color=user.color, description = "A moderator has give a level 3 warning (ban) to a user")
            mod.title = "Warning"
            mod.add_field(name = "Moderator", value = author.mention, inline = True)
            mod.add_field(name = "User", value = user.mention, inline = True)
            mod.add_field(name = "Reason", value = reason, inline = False)
            mod.set_thumbnail(url = "https://cdn.discordapp.com/attachments/303988901570150401/342427198269030402/Revitlink2BDamien2BWArnings.png")
            mod.set_footer(text=str(user.name), icon_url = user.avatar_url)

            target = discord.Embed(color = user.color, description = "You have received a level 3 warning (ban). You now cannot go back to the server")

            target.title = "Warning"
            target.add_field(name = "Reason", value = reason)
            target.set_thumbnail(url = "https://cdn.discordapp.com/attachments/303988901570150401/342427198269030402/Revitlink2BDamien2BWArnings.png")

            await self.bot.send_message(user, embed=target)

            try:
                await self.bot.ban(user)
                mod.set_footer(text=str(user.name), icon_url = user.avatar_url)

            except:
                await self.bot.say("The user couln't be banned. Please check my permissions")
                mod.set_footer(text="The user coudn't be banned. Please check my permissions")

            await self.bot.send_message(channel, embed=mod)

def check_folders():
    folders = ("data", "data/bettermod/")
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating " + folder + " folder...")
            os.makedirs(folder)


def check_files():
    ignore_list = {"SERVERS": [], "CHANNELS": []}

    files = {
        "settings.json"         : {}
        }

    for filename, value in files.items():
        if not os.path.isfile("data/bettermod/{}".format(filename)):
            print("Creating empty {}".format(filename))
            dataIO.save_json("data/bettermod/{}".format(filename), value)


def setup(bot):
    check_folders()
    check_files()
    bot.add_cog(BetterMod(bot))
