==========
RoleInvite
==========

.. note:: These docs refers to the version **2.0.0**.
    Make sure you're under the good version by typing ``[p]cog update``.

This is the guide for the ``roleinvite`` cog. Everything you need is here.

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

    [p]cog install Laggrons-Dumb-Cogs roleinvite

.. warning:: The cog is not loaded by default.
    To load it, type this::

        [p]load roleinvite

-----
Usage
-----

Before giving the commands list, I'd like to show you how the cog is working.

The cog works with what I call invite links. Each invite
link is linked to one or more roles. This mean that,
every time a new user join the server, if he used the invite A to
join the server, he will get the list of roles linked to the invite A.

You can link many roles  to multiple invites, so you can imagine something
like "click **here** if you are an engineer, else click **here** if you're
an architect", and make roleinvite give the engineer or architect roles.

You can also link roles to default or main autorole.
If you link roles to the main autorole,
the new member will get these roles if he
joined with an unlinked invite. If you link roles
to the default autorole, new users will always get
these roles, whatever invite he used.

Here's a schema for a better understanding:

.. image:: .ressources/FLOWCHARTS/RoleInvite.png

Here's the list of all commands of this cog.

.. _command-roleset:

~~~~~~~
roleset
~~~~~~~

**Syntax**::

    [p]roleset

**Description**

This is the main command used for setting up the code.
It will be used for all other commands.

.. _command-roleset-add:

~~~~~~~~~~~
roleset add
~~~~~~~~~~~

**Syntax**::

    [p]roleset add <invite|main|default> <role>

**Description**

Link a role to a Discord invite or a default autorole.

* If ``invite`` is specified (a discord invite link),
  a new invite link will be created with the role you gave.

* If ``main`` is specified, the role will be linked to the main autorole.

* If ``default`` is given, the role will be linked to the default autorole.

You can link more roles by typing the command with the same argument.

**Arguments**

* ``<invite>`` The object to link the role to.

    * If it is a Discord invite URL, the role will be linked to it.

    * If it is ``main``, the role will be linked to the main autorole
      (role given if the invite used is not linked to any roles).

    * If it is ``default``, the role will be linked to the default autorole
      (role always given, whatever invite the user used).

* ``<role>`` The role to be linked. Please give the **exact role name**
  or the ID.

.. _command-roleset-remove:

~~~~~~~~~~~~~~
roleset remove
~~~~~~~~~~~~~~

**Syntax**::

    [p]roleset remove <invite|main|default> [role]

**Description**

Unlink a role from an autorole. If the role is not given, the entire autorole
will be removed.

**Arguments**

* ``<invite>`` The object that will be edited.

    * If it is a Discord invite URL, the role will be unlinked from it.

    * If it is ``main``, the role will be unlinked from the main autorole.

    * If it is ``default``, the role will be unlinked from
      the default autorole.

* ``[role]`` Optional. The role to be unlinked. Please give the
  **exact role name** or the ID. If not given, the entire
  autorole will be removed.

.. _command-roleset-list:

~~~~~~~~~~~~
roleset list
~~~~~~~~~~~~

**Syntax**

.. code-block:: none

    [p]roleset list

**Description**

List all of the existing autoroles on the guild, with their linked roles.

.. _command-roleset-enable:

~~~~~~~~~~~~~~
roleset enable
~~~~~~~~~~~~~~

**Syntax**

.. code-block:: none

    [p]roleset enable

**Description**

Enable or disable the autorole system.

.. note::

    If it was removed without your action, that means that the bot somehow
    lost its permissions. Make sure it has the good permissions and enable it again.

-------------------------
Frequently Asked Question
-------------------------

.. note::

    **Your question is not in the list or you got an unexcpected issue?**

    You should join the `Discord server <https://discord.gg/AVzjfpRM>`_ or
    `post an issue <https://github.com/retke/Laggrons-Dumb-Cogs/issues/new/choose>`_
    on the repo.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Can I make it so the bot adds x roles if the invite used is unknown?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Yes, by using the ``main`` value instead of using a discord invite
when creating a new invite link. See :ref:`roleset add <command-roleset-add>` command's
arguments for more informations.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Can I make it so the bot always adds x roles, regardless of the invite used?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Yes, by using the ``default`` value instead of using a discord invite
when creating a new invite link. See :ref:`roleset add <command-roleset-add>` command's
arguments for more informations.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Can I make a custom welcome message for each invite link?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Not for now. I'm thinking about interacting with another package for that, 
but that'll require an API, which is rare with cog creators, and creating 
my own welcomer system is a lot of work. 

This may be available in a future release.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The bot suddenly stopped adding roles to the new members
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The bot will automatically turn off the autorole system if he lose the ``Manage
sever`` or the ``Add roles`` permissions, which are absolutely necessary for the cog.

If you added the permissions back, enable the autorole again with the command 
:ref:`enable <command-roleset-enable>`.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Some roles are not added to the new members
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This can happens if the role hierarchy is modified after the roles got linked.
Remember that a bot/member can only add roles that are below him in the role
hierarchy. 

Modify the role hirearchy and make sure all necessary roles are **below**
the bot's highest role. If it still doesn't work, try to link the role again.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
An invite link was removed without any action
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Invite links will be deleted if the invite doesn't exist anymore
(manual delete or invite expired).