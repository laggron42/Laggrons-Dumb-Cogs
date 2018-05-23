===============
InstantCommands
===============

.. note:: These docs refers to the **beta 2b** version. 
    Make sure you're under the good version by typing ``[p]cog update``.

This is the guide for the ``instantcmd`` cog. Everything you need is here.

``[p]`` is considered as your prefix.

------------
Installation
------------

To install the cog, first load the downloader cog, included
in core Red.::

    [p]load downloader

Then you will need to install the Laggron's Dumb Cogs repository::

    [p]repo add Laggrons-Dumb-Cogs https://github.com/retke/Laggrons-Dumb-Cogs v3

Finally, you can install the cog::

    [p]cog install Laggrons-Dumb-Cogs instantcmd

.. warning:: The cog is not loaded by default. 
    To load it, type this::

        [p]load instantcmd

-----
Usage
-----

InstantCommands is designed to create new commands and listeners directly 
from Discord. You just need basic Python and discord.py knowledge.

Here's an example of his it works:

.. image:: .ressources/EXAMPLES/InstantCommands-example.png

Here's a list of all commands of this cog:

~~~~~~~~~~~~~~
instantcommand
~~~~~~~~~~~~~~

**Syntax**::

    [p][instacmd|instantcmd|instantcommand]

**Description**

This is the main command used for setting up the code. 
It will be used for all other commands.

~~~~~~~~~~~~~~~~~~~~~
instantcommand create
~~~~~~~~~~~~~~~~~~~~~

**Syntax**::

    [p]instantcommand create

**Description**

Creates a new command/listener from a code snippet.

You will be asked to give a code snippet which will contain your function. 
It can be a command (you will need to add the ``commands`` decorator) or a listener 
(your function name must correspond to an existing discord.py listener).

.. tip:: Here are some examples
    
    .. code-block:: python
    
        @roleset.command()
        @commands.command()
        async def command(ctx, *, argument):
            """Say your text with some magic"""

            await ctx.send("You excepted to see your text, "
                            "but it was I, Dio!")
                            
    .. code-block:: python
    
        async def on_reaction_add(reaction, user):
            await reaction.message.add_reaction('❤')
            await message.channel.send("Here's some love for " + user.mention)
