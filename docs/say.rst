===
Say
===

.. note:: These docs refers to the version **1.4.8**.
    Make sure you're under the good version by typing ``[p]cog update``.

This is the guide for the ``say`` cog. Everything you need is here.

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

    [p]cog install Laggrons-Dumb-Cogs say

.. warning:: The cog is not loaded by default. 
    To load it, type this::

        [p]load say

-----
Usage
-----

Here's the list of all commands of this cog.

.. _command-say:
    
~~~
say
~~~

**Syntax**

.. code-block:: none

    [p]say [channel] <text>

**Description**

Make the bot say ``<text>`` in the channel you want. If specified, 
it is send in a different channel.

.. tip::

    **Examples**
    
    .. code-block:: none

        [p]say Hello it's me, Red bot!
        [p]say #general Hello, it's still me but from a different channel!

**Arguments**

* ``[channel=ctx]``: The channel where the bot will send a message. 
  Default to where you typed the command.

* ``<text>``: The text that the bot will say in the channel.

* ``attachment``: The file you want to make the bot send. This is optional.

.. _command-sayd:
    
~~~~~~~~~
saydelete
~~~~~~~~~

**Syntax**

.. code-block:: none

    [p][sayd|saydelete] [channel] <text>

**Descripton**

Exact same as :ref:`say <command-say>` command, except it deletes your message.

.. warning:: The ``Manage message`` permission is needed for the bot to use this function.

.. _command-interact:

~~~~~~~~
interact
~~~~~~~~

**Syntax**

.. code-block:: none

    [p]interact [channel]

**Description**

Starts a rift between the channel and your DMs. The messages you send to the bot in DM will make 
him post your messages in the channel. It will also post every message send in that time lapse.

.. note:: Click on the ❌ reaction on the first message to cancel the interaction.

**Arguments**

* ``[channel=ctx]``: The channel where you want to start the interaction. Default to where 
  you typed the command.

.. tip:: This can be used directly from DM. Then it will be cross-server. 

    Just make sure you give an ID as the channel. Giving the channel name can lead to a different server. 
    Get the channel ID by enabling the developer mode (under Appearance section in the Discord user parameters), 
    then right click on the channel and copy the ID.

--------------------------
Frequently Asked Questions
--------------------------

.. note::

    **Your question is not in the list or you got an unexcpected issue?**

    You should join the `Discord server <https://discord.gg/AVzjfpRM>`_ or
    `post an issue <https://github.com/retke/Laggrons-Dumb-Cogs/issues/new/choose>`_
    on the repo.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Can I send messages in another channel than the one where I typed the command?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Yes, by giving the channel as the first argument, like that:

.. code-block:: none
    
    [p]say #my-channel Hello!
    [p]say my-channel Hello!

You can also use the command in DM. 
It is recommended to give the channel ID as argument, since there may be many 
channels that has the same name in the bot servers.

.. code-block:: none

    [p]say 363031186504941578 Hello!

.. tip::
  Get the ID by enabling the developer mode (User settings -> Appearance), then by right-clicking on the channel.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Can I make the bot upload links?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Yes, just attach a file to your message, 
it will be reposted with the same content. You can also add or not a comment.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Can I make the bot delete my message?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Yes, there's a command called :ref:`sayd <command-sayd>` (for say delete) that 
will delete your message before posting.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
My bot is slow to delete messages
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If your bot is slow, that is an issue with your discord connection. Try changing
the host machine.

.. tip::
    
    You should use the :ref:`interact <command-interact>` command 
    that let you tell what the bot should say in DM, so users won't see you typing.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
I am not allowed to use the command
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The command is only available for server owners and bot owner by default.
You can modify this by using the core permissions cog.