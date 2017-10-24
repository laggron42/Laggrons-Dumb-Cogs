import discord
import os
import json

from discord.ext import commands
from .utils.dataIO import dataIO

class RoleInvite:
    """Autorole on users following the invite they used"""

    def __init__(self, bot):
        self.bot = bot
        self.settings = dataIO.load_json('data/roleinvite/settings.json')
    
    def init(self, server_id):
        self.settings[server_id] = {
            'invites': {},
                'len': 0
        }
    
    @commands.group(pass_context=True)
    async def roleset(self, ctx):
        """Settings for role invite cog"""
    
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

    @roleset.command(pass_context=True)
    async def add(self, ctx, invite: str, *, rolename: str):
        """Add an invite trigger
            
            Usage: [p]roleset add https://discord.gg/red Linux users
            Will add the Linux users role to anyone who joins using the red invite link"""
        
        if ctx.message.server.id not in self.settings:
            self.init(ctx.message.server.id)
    
        role = discord.utils.get(ctx.message.server.roles, name=rolename)

        if role is None:
            await self.bot.say("The given role cannot be found.")
            return

        try:
            invites = await self.bot.invites_from(ctx.message.server)
        except:
            await self.bot.say("There is no invites on this server")
            return

        if invite.startswith("https://discord.gg/") or invite.startswith("http://discord.gg/"):
            tmp = invite.split('/')
            invite = tmp[3]
        
        print(invite)

        for i in invites:
            print(i.url)
            tmp = i.url.split('/')
            name_i = tmp[3]
            print(name_i)
            if name_i == invite:
                print("{} Good".format(i))
                self.settings[ctx.message.server.id]['len'] += 1
                self.settings[ctx.message.server.id]['invites'][i.url] = {"role": str(role), "use": int(i.uses)}
                
                await self.bot.say("The invite `{}` is now assigned to the role `{}`".format(i, role.name))
                dataIO.save_json('data/roleinvite/settings.json', self.settings)
                return

        await self.bot.say("The invite cannot be found")


    @roleset.command(pass_context=True)
    async def list(self, ctx):
        """List all of the invites assigned to a role on this server"""

        if ctx.message.server.id not in self.settings:
            self.init(ctx.message.server.id)
        
        if self.settings[ctx.message.server.id]['invites'] == {}:
            await self.bot.say("There is nothing set on this server yet")
            return
                
        message = "List of current enabled invites on this server:\n`Invite`: role concerned\n\n"

        for invite in self.settings[ctx.message.server.id]['invites']:
            message += "`{}`: {}\n".format(invite, self.settings[ctx.message.server.id]['invites'][invite]['role'])
        
        await self.bot.say(message)
            
    
    @roleset.command(pass_context=True)
    async def remove(self, ctx, invite: str):
        """Remove a link between an invite and a role
            
            Give as argument the invite used to link"""

        if ctx.message.server.id not in self.settings:
            self.init(ctx.message.server.id)

        if invite.startswith("https://discord.gg/") or invite.startswith("http://discord.gg/"):
            tmp = invite.split('/')
            invite_sh = tmp[3]
        else:
            invite_sh = invite
            invite = "http://discord.gg/" + invite_sh

        if invite not in self.settings[ctx.message.server.id]['invites']:
            await self.bot.say("That invite does not exist or is not registered. Type `{}roleset list` to see all invites registered".format(ctx.prefix))
            return
                
        e = discord.Embed(description="Deletion of role-invite link")
        e.add_field(name="Invite", value=invite, inline=True)
        e.add_field(name="Role", value=self.settings[ctx.message.server.id]['invites'][invite]['role'], inline=True)
        e.set_author(name=ctx.message.server.name, icon_url=ctx.message.server.icon_url)
        e.set_footer(text="Click on the reaction to confirm changes")
            
        msg = await self.bot.say(embed=e)
            
        await self.bot.add_reaction(msg, "✅")
        reaction = await self.bot.wait_for_reaction(message=msg, user=ctx.message.author, emoji="✅", timeout=30)
        
        if reaction is None:
            await self.bot.remove_reaction(msg, "✅")
            return
                
        del self.settings[ctx.message.server.id]['invites'][invite]
        dataIO.save_json('data/roleinvite/settings.json', self.settings)

        try:
            await self.bot.delete_message(msg)
        except:
            pass
        await self.bot.say("The link has been removed, users won't get this role anymore when joining with this link")
            
            
    async def on_member_join(self, member):
        
        if member.bot:
            print("member is bot")
            return
    
        if member.server.id not in self.settings:
            self.init(member.server.id)

        sett = self.settings[member.server.id]
        try:
            invites = await self.bot.invites_from(member.server)
        except:
            return
        
        print(json.dumps(sett, indent=4))
        print(list(invites))
        print("\n\n")

        for i in invites:
            
            print("""Invite: {}
                Uses: {}
                User: {}""".format(i, i.uses, member))
            
            if i.url in sett['invites']:
                print("Condition reached! URL {} inside invites list".format(i))
                if int(i.uses) > int(sett['invites'][str(i)]['use']):
                    print("Condition reached! Invite uses:{} > Stored invite uses:{}".format(i, sett['invites'][str(i)]['use']))
                    role = discord.utils.get(member.server.roles, name=sett['invites'][str(i)]['role'])
                    print("Role for {} is {}".format(i, role))
                    if role is not None:
                        await self.bot.add_roles(member, role)
                    else:
                        print("Role not found")
                sett['invites'][str(i)]['use'] = i.uses
                print("\nEnd of loop\n\n")

def check_folders():
    folders = ('data', 'data/roleinvite/')
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating " + folder + " folder...")
            os.makedirs(folder)


def check_files():
    ignore_list = {'SERVERS': [], 'CHANNELS': []}
    
    files = {
        'settings.json'         : {}
    }
    
    for filename, value in files.items():
        if not os.path.isfile('data/roleinvite/{}'.format(filename)):
            print("Creating empty {}".format(filename))
            dataIO.save_json('data/roleinvite/{}'.format(filename), value)


def setup(bot):
    check_folders()
    check_files()
    bot.add_cog(RoleInvite(bot))
