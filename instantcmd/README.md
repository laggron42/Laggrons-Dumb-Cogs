# InstantCommands

This is the InstantCommands cog for Red, a tool that can load and store commands or listeners directly from a code snippet sent through Discord.

If you're used to add commands using the eval command, you might like this cog, since what you adds stay loaded after reboot!

**This cog is made for those who know Python and are used to make cogs and commands. If you don't know coding, this is not for you.**

There is a detailed documentation, covering all commands in details, please read this if you want to know how commands works in details: https://laggron.red/instantcommands.html

## Installation and quick start

`[p]` is your prefix.

1.  Install the repo if it's not already done.
    ```
    [p]repo add Laggrons-Dumb-Cogs https://github.com/retke/Laggrons-Dumb-Cogs v3
    ```

2.  Install and load InstantCommands
    ```py
    [p]cog install Laggrons-Dumb-Cogs instantcmd
    # Type "I agree" if requested
    # wait for your bot to install the cog
    [p]load instantcmd
    ```

InstantCommands is now installed!

A few things to keep in mind when making commands and listeners:
-   **Do not add `self` as an argument to your command, only `ctx`.**
-   **Return the command/listener object at the end of your code.**
-   Some modules and values are available in your code:
    -   `bot` (instance of `redbot.core.commands.Bot`, same as with eval)
    -   `discord`
    -   `redbot.core.commands`
    -   `redbot.core.checks`
-   Config can be used in your code. Example:
    ```py
    from redbot.core import Config

    conf = Config.get_conf(None, 9549856112, cog_name="InstantCommands")
    conf.register_global(the_answer=42)

    @commands.command()
    async def deepthough(ctx):
        """
        What is the answer?
        """
        answer = await conf.the_answer()
        await ctx.send(f"The answer to the life, the universe and everything is {answer}.")
    
    return deepthough
    ```
    Some things to be careful when using Config:
    -   **Use `InstantCommands` as the cog name, like in the example.**
    -   **Do not use `260` as your identifier since it's the one used by the cog.**
    -   Be sure to know what you're doing, you have less control on these commands.

## Examples

```
[p]instantcmd create
```

Once the bot asks for it, you have 15 minutes to send your code.

```py
# command example

@commands.command()
@checks.admin()
async def addrole(ctx, *, role: discord.Role):
    """
    Add a role to the whole server.
    """
    for member in ctx.guild.members:
        try:
            await member.add_roles(role)
        except discord.errors.Forbidden:
            pass

return addrole
```

```py
# listener example

async def on_member_join(member):
    guild = member.guild
    role = guild.get_role(142006827155062784)
    await member.add_roles(role, reason="Autorole")

return on_member_join
```

## Discord server

If you need support, have bugs to report or suggestions to bring, please join my Discord server and tell me, `El Laggron#0260`, about it!

[![Discord server](https://discordapp.com/api/guilds/363008468602454017/embed.png?style=banner3)](https://discord.gg/AVzjfpR)

## [Laggron's Dumb Cogs](https://github.com/retke/Laggrons-Dumb-Cogs)

![Artwork](https://github.com/retke/Laggrons-Dumb-Cogs/blob/master/.github/RESSOURCES/BANNERS/Base_banner.png)

This cog is part of the Laggron's Dumb Cogs repository, where utility cogs for managing your server are made!
If you like this cog, you should check the other cogs from [the repository](https://github.com/retke/Laggrons-Dumb-Cogs)!

You can also support me on Patreon and get exclusive rewards!

<img src="https://c5.patreon.com/external/logo/become_a_patron_button@2x.png" alt="Become a Patreon" width="180"/>

<!-- Replace link by cogs.red link -->
