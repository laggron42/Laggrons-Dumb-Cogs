===
Say
===

.. note:: These docs refers to the **release 1.1** version. 
    Maje sure you're under the good version by typing ``[p]cog update``.

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

        [p]load Say

-----
Usage
-----

Here's the list of all commands of this cog.

~~~
say
~~~

**Syntax**::

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

* ``[channel=ctx]``: The channel where the bot will send a message. Default to where you typed the command.

* ``<text>``: The text that the bot will say in the channel.

* ``attachment``: The file you want to make the bot send. This is optional.

~~~~~~~~~
saydelete
~~~~~~~~~

**Syntax**::

    [p][sayd|saydelete] [channel] <text>

**Descripton**

Exact same as ``[p]say`` command, except it deletes your message.

.. warning:: The ``Manage message`` permission is needed for the bot to use this function.

~~~~~~~~
interact
~~~~~~~~

**Syntax**::

    [p]interact [channel]

**Description**

Starts a rift between the channel and your DMs. The messages you send to the bot in DM will make 
him post your messages in the channel. It will also post every message send in that time lapse.

.. info:: Click on the ❌ reaction on the first message to cancel the interaction.

**Arguments**

* ``[channel=ctx]``: The channel where you want to start the interaction. Default to where 
you typed the command.

.. tip:: This can be used directly from DM. Then it will be cross-server. 
    Just make sure you give an ID as the channel. Giving the channel name can lead to a different server. 
    Get the channel ID by enabling the developer mode (under Appearance section in the Discord user parameters), 
    then right click on the channel and copy the ID.