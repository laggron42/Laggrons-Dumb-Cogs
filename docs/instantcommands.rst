===============
InstantCommands
===============

.. note:: These docs refers to the version **2..0**. 
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

InstantCommands is designed to create new objects, like commands, directly 
from Discord. You just need basic Python and discord.py knowledge.

You can also edit the Dev's environment added with Red 3.4.6.

From a code snippet in Discord, you can create the following objects:

- :ref:`commands <usage-adding-commands>`
- :ref:`listeners <usage-adding-listeners>`
- :ref:`dev env values <usage-adding-dev-values>`
- views

More objects will come in future releases, like application commands, message
components, cogs...

To add a code snippet, use :ref:`instantcmd create
<command-instantcommand-create>` and paste the code you want, following the
format described below. You can then manage code snippets with :ref:`instantcmd
list <command-instantcommand-list>`.

.. _usage-adding-commands:
~~~~~~~~~~~~~~~
Adding commands
~~~~~~~~~~~~~~~

Adding a command is very straightforward:

.. code-block:: py
    @commands.command()
    async def hello(ctx):
        await ctx.send(f"Hi {ctx.author.name}!")
    
    return hello

.. warning:: Don't forget to always return your object at the end!

.. _usage-adding-listeners:
~~~~~~~~~~~~~~~~
Adding listeners
~~~~~~~~~~~~~~~~

Adding a listener requires a custom decorator:

.. code-block:: py
    from instantcmd.utils import listener

    @listener()
    async def on_member_join(member):
        await member.send("Welcome there new member!")
    
    return on_member_join

To prevent conflicts, or name your code snippets better, you can give your
function a different name and provide the listener name in the decorator:

.. code-block:: py
    from instantcmd.utils import listener

    @listener("on_member_join")
    async def member_welcomer(member):
        await member.send("Welcome there new member!")
    
    return member_welcomer

Your code will be saved and referred as "member_welcomer".

.. _usage-adding-dev-values:
~~~~~~~~~~~~~~~~~~~~~
Adding dev env values
~~~~~~~~~~~~~~~~~~~~~

You can add custom dev env values, which will be made available to Red's dev
cog (``[p]debug``, ``[p]eval`` and ``[p]repl`` commands). For more information,
see :ref:`Red's documentation <https://docs.discord.red/en/stable/framework_bot.html#redbot.core.bot.RedBase.add_dev_env_value>`.

The format is similar to listeners:

.. code-block:: py
    from instantcmd.utils import dev_env_value

    @dev_env_value()
    def fluff_derg(ctx):
        ID = 215640856839979008
        if ctx.guild:
            return ctx.guild.get_member(ID) or bot.get_user(ID)
        else:
            return bot.get_user(ID)

    return fluff_derg

Just like listeners, you can give your function a different name and provide
the dev value name in the decorator:

.. code-block:: py
    from instantcmd.utils import dev_env_value

    @dev_env_value("fluff_derg")
    def give_me_a_dragon(ctx):
        ID = 215640856839979008
        if ctx.guild:
            return ctx.guild.get_member(ID) or bot.get_user(ID)
        else:
            return bot.get_user(ID)

    return give_me_a_dragon

Your code will be saved and referred as "give_me_a_dragon".

.. _usage-adding-views:
~~~~~~~~~~~~
Adding views
~~~~~~~~~~~~

You can register views that are then sent using the :ref:`sendview
<command-instantcommand-sendview>` command.

You do not need to write a function with a decorator, instead it's a class,
just like a normal view:

.. code-block:: py

    from discord.ui import View, button

    class SecretPing(View):
        @button(label="Ping", style=discord.ButtonStyle.primary)
        async def ping(self, interaction, button):
            await interaction.response.send_message(
                f"Hi {interaction.user.mention} but in private", ephemeral=True
            )

    return SecretPing

Then run ``[p]instantcmd sendview SecretPing Some message content`` to make
the bot send a message with your view attached.

Check out the documentation on :class:`discord.ui.View` and the corresponding
decorators below.

.. warning:: The default timeout for a view is 180 seconds! You can change it
    by overriding the default parameters of the view object.

    The cog currently has no support for permanent views.

--------
Commands
--------

Here's a list of all commands of this cog:

.. _command-instantcommand:

~~~~~~~~~~~~~~
instantcommand
~~~~~~~~~~~~~~

**Syntax**::

    [p][instacmd|instantcmd|instantcommand]

**Description**

This is the main command used for setting up the code. 
It will be used for all other commands.

.. _command-instantcommand-create:

~~~~~~~~~~~~~~~~~~~~~
instantcommand create
~~~~~~~~~~~~~~~~~~~~~

**Syntax**::

    [p]instantcommand [create|add]

**Description**

Creates a new command/listener from a code snippet.

You will be asked to give a code snippet which will contain your function. 
It can be any supported object as described above.

.. tip::

    Here are the available values within your code snippet:

    * ``bot`` (client object)
    * ``discord``
    * ``commands``
    * ``checks``
    * ``asyncio``
    * ``redbot``
    * ``instantcmd_cog`` (well, the InstantCommands cog)

If you try to add a new command/listener that already exists, the bot will ask
you if you want to replace the command/listener, useful for a quick bug fix
instead of deleting each time.

The code can be provided in the same message of the command, in a new 
followup message, or inside an attached text file.

.. _command-instantcommand-list:
~~~~~~~~~~~~~~~~~~~
instantcommand list
~~~~~~~~~~~~~~~~~~~

**Syntax**

.. code-block:: none

    [p]instantcommand list

**Description**

Lists the code snippets added with instantcmd.

Multiple select menus will be sent for each type of object, click them and
select the object you want to edit.

Once selected, a new message will be sent containing the source of the
message and 3 buttons: download the source file, enable/disable this object,
and delete it.

.. _command-instantcommand-sendview:
~~~~~~~~~~~~~~~~~~~~~~~
instantcommand sendview
~~~~~~~~~~~~~~~~~~~~~~~

**Syntax**::

    [p]instantcommand sendview <view> [channel] <message>

**Description**

Make the bot send a message with content ``<message>``, in ``[channel]``
or the current channel if not specified.

The instantcmd-registered ``<view>`` will be attached to that message.

--------------------------
Frequently Asked Questions
--------------------------

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
My command was added but doesn't respond when invoked.
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If a command is not invoked, this is most likely due to missing arguments.
Please check that you only have the :class:`ctx <discord.ext.commands.context>`
argument and **no self argument**.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Can I use Config in my command?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Yes you can. The :class:`~redbot.core.Config` module is already imported,
you just need to use it as in a cog.

.. tip:: Here's an example

    .. code-block:: python

        @commands.command(name="test")
        async def my_command(ctx):
            config = Config.get_conf(cog_instance="InstantCommands", identifier=42)
            # use anything but 260 for the identifier
            # since it's the one used for the cog settings
            config.register_guild(**{
                "foo": None
            })
        
            await config.guild(ctx.guild).foo.set("bar")
            await ctx.send("Well done")
        
        return my_command

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
How can limit a command for some users?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can use the :class:`~redbot.core.checks` module, like in a normal cog.

.. tip:: Here's an example

    .. code-block:: python

        @commands.command()
        @checks.admin_or_permissions(administrator=True)
        async def command(ctx):
            # your code
        
        return command

~~~~~~~~~~~~~~~~~~~~~~~~~~
How can I import a module?
~~~~~~~~~~~~~~~~~~~~~~~~~~

You can import your modules outside the function as you wish.

.. tip:: Here's an example

    .. code-block:: python

        from redbot.core import modlog
        import time

        @commands.command()
        async def command(ctx):
            # your code
        
        return command
