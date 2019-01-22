==========
WarnSystem
==========

.. note:: These docs refers to the version **1.0.1**.
    Make sure you're under the good version by typing ``[p]cog update``.

This is the guide for the ``warnsystem`` cog. Everything you need is here.

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

    [p]cog install Laggrons-Dumb-Cogs warnsystem

.. warning:: The cog is not loaded by default.
    To load it, type this::

        [p]load warnsystem

-----
Usage
-----

This cog is an alternative to the Mod core cog. It provides a moderation system
similar to Dyno. Actions are stored and can be accessed at any time. This is
the rewrite of the BetterMod cog for Red V3. Here is a quick start guide.

1. Define a modlog channel

    You can define a channel where all actions will be logged, either with the
    ``[p]warnset channel` command or with the ``[p]modlogset modlog`` command,
    from Modlog cog.

2. Set your moderators

    All members with the moderator role will be able to use the ``[p]warn``
    command. You can set the moderator and administrator role with the ``[p]set
    modrole`` and ``[p]set adminrole`` commands.

3. (Optional) Set up the mute role

    The mute from WarnSystem uses roles instead of separate channel
    permissions. Type ``[p]warnset mute`` to create the mute role. It will be
    placed below the bot's top role and all channel permissions will be edited
    so those who have this role cannot send messages and add reactions.

    You can edit this role as you want, as long as it is below the bot's top
    role so it can assign it to users.

4. Warn members

    Once this is setup, moderators and administartors will be able to use the
    ``[p]warn`` command, with 5 different levels:

    1.  Simple warning
    2.  Server mute (can be temporary)
    3.  Kick
    4.  Softban (ban then quickly unban the member, to clean his messages)
    5.  Ban (can be temporary, and also ban members not on the server)

    Each warn will send a DM to the warned member, a log in the modlog channel,
    then the bot will take actions. You can check, edit and delete a member's
    warnings with the ``[p]warnings`` command.

You now have the basic setup ready! If you want, you can setup more features
for your bot:

*   **Substitutions:** If you own a huge server, you might repeat yourself in
    the reasons of your warnings. You can setup substitutions, so you can
    include small words that will be replaced by a defined sentence. For
    example, if you set "Advertising for a Discord server." as a substitution
    of ``ad``, type this: ``[p]warn 3 @El Laggron#0260 [ad] This is your last
    warning!`` and the reason of the warn will be "Advertising for a Discord
    Server. This is your last warning!". Get started with the ``[p]warnset
    substitutions`` group command.

*   **Reinvite:** Enabling this feature will try to send a DM to all unbanned
    members after their temporary ban, including an invite for yout server.
    Note that the bot must share a server in commom with the unbanned member.

*   **Hierarchy:** To make sure your moderators doesn't abuse with their
    permissions, you can enable hierarchy protection. This means that the bot
    will block a moderator trying to warn a member higher than him in the role
    hierarchy, like with the manual Discord actions.

*   **Multiple modlogs:** If you want to send all warnings, mutes, kicks and
    softban in a private channel, but you want to make the ban publics, you
    can set a different channel for a specific warning level. Type ``[p]warnset
    channel #your-channel 5`` to make all bans goes into that channel. Just
    change the number for the warn level.

*   **Hide responsible moderator:** Sometimes, moderators wants to keep their
    action anonymous to the warned member. If you want to stay transparent,
    type ``[p]warnset showmod`` to show the author of a warn to the warned
    member in DM.

*   **Set number of days of messages to delete:** A Discord ban allows to set
    a specific number of days of messages sent by the banned member to delete,
    up to 7 days. By default, softbans will delete 7 days of messages and bans
    won't delete any. You can customize this with the ``[p]warnset bandays``
    command.

*   **Custom embed description:** If you want to customize your modlog and set
    your own sentence for logs sent to the modlog channel and to the warned
    member, you can do this with the ``[p]warnset description`` command.

*   **Convert your old BetterMod logs:** If you're migrating to V3 and you were
    using the BetterMod cog on your V2 bot, you can migrate the logs for V3!
    Get the file of your modlog history (located at
    ``/data/bettermod/history/<your server ID>.json``) and use the ``[p]warnset
    convert`` command.

--------
Commands
--------

Here is a list of all commands from this cog.

^^^^
warn
^^^^

**Syntax**

.. code-block:: none

    [p]warn

**Description**

The base command used to warn members. You must either have the moderator role,
administrator role, have the administrator permission or be the server owner.

.. warning:: You **must** setup a modlog channel before using warn, either with
    the core Modlog cog (``[p]modlogset modlog``) or with WarnSystem
    (``[p]warnset channel``).

Each warning will be logged to the modlog channel, and a DM will be sent to the
warned member. If the bot cannot send a message to that member (the member may
have blocked the bot, disabled DMs from this server, or doesn't share a server
in common with the bot), it will be showed in the modlog.

You can check the warnings set on a specific member later with the
``[p]warnings`` command. This command also allows to edit the reason of the
warning, or delete them.

""""""
warn 1
""""""

**Syntax**

.. code-block:: none

    [p]warn <1|simple> <member> [reason]

**Description**

Sets a simple warning on a member. This does not take any action, but the warn
will be showed to the member and stored.

**Example**

*   .. code-block:: none

        [p]warn 1 @El Laggron#0260 Rude behaviour.

    This warns El Laggron for the following reason: Rude behaviour.

**Arguments**

*   ``<member>``: The member to warn. Can either be a mention, the name + tag,
    the name, the nickname or an ID.

*   ``[reason]``: The reason of the warn. Omitting this will set the reason as
    "No reason set.".

""""""
warn 2
""""""

**Syntax**

.. code-block:: none

    [p]warn <2|mute> <member> [duration] [reason]

**Description**

Mutes the member with a role on the server.

.. warning:: You **must** have the mute role setup. Use the ``[p]warnset mute``
    command to create/assign the role.

The member will get the mute role for the specified time. You can edit this
role as you like to allow him some channels for example. Removing his role
manually will cancel his mute without problem, but the warn will still exist.
Removing the warn with the ``[p]warnings`` command will also remove the role
if needed.

You can set a duration to the mute with the first word of the reason, which
should be a number followed by the unit. Examples:

*   ``20s`` = ``20secs`` = ``20seconds``: 20 seconds
*   ``5m`` = ``5minutes`` = ``5min``: 5 minutes
*   ``2h`` = ``2hours`` = ``2hrs``: 2 hours
*   ``1d`` = ``1day``: one day
*   ``7d`` = ``7days``: a week

You can also stack them like this:

*   ``5m30s``: 5 minutes and 30 seconds
*   ``1d12h``: One day and a half
*   ``1h45m``: 1 hours and 45 minutes

**Examples**

*   .. code-block:: none

        [p]warn 2 @El Laggron#0260 Hacked account.
    
    This will mute El Laggron for an undefined duration.

*   .. code-block:: none

        [p]warn 2 @El Laggron#0260 2h Spam for exp.
    
    This will mute El Laggron for two hours, then remove his role.

**Arguments**

*   ``<member>``: The member to warn. Can either be a mention, the name + tag,
    the name, the nickname or an ID.

*   ``[reason]``: The reason of the warn. Omitting this will set the reason as
    "No reason set.".

""""""
warn 3
""""""

**Syntax**

.. code-block:: none

    [p]warn <3|kick> <member> [reason]

**Description**

Kicks the member from the server.

**Example**

*   .. code-block:: none

        [p]warn 3 @El Laggron#0260 Selfbot.
    
    This will just kick the member.

**Arguments**

*   ``<member>``: The member to warn. Can either be a mention, the name + tag,
    the name, the nickname or an ID.

*   ``[reason]``: The reason of the warn. Omitting this will set the reason as
    "No reason set.".

""""""
warn 4
""""""

**Syntax**

.. code-block:: none

    [p]warn <4|softban> <member> [reason]

**Description**

Bans the member from the server, then unbans him, to mass delete his messages.
This can be considered as a kick with a massive cleanup of messages.

The bot will delete 7 days of messages by default, this can be changed with the
``[p]warnset bandays`` command.

**Example**

*   .. code-block:: none

        [p]warn 4 @El Laggron#0260 NSFW in inappropriate channels.
    
    This will kick El Laggron and delete all of his messages sent in the last 7
    days.

**Arguments**

*   ``<member>``: The member to warn. Can either be a mention, the name + tag,
    the name, the nickname or an ID.

*   ``[reason]``: The reason of the warn. Omitting this will set the reason as
    "No reason set.".

""""""
warn 5
""""""

**Syntax**

.. code-block:: none

    [p]warn <5|ban> <member> [duration] [reason]

**Description**

Bans the member from the server, can be a temporary ban. It can also be a
hackban (banning a member which is not on the server).

If you want to perform a hackban, get the ID of the user and provide it for
the ``<member>`` argument. You can get a user ID by enabling the developer mode
(User Settings > Appearance > Developer mode), then right-clicking on that user
and clicking on "Copy ID".

The bot won't delete any message by default, this can be changed with the
``[p]warnset bandays`` command.

You can set a duration to the mute with the first word of the reason, which
should be a number followed by the unit. Examples:

*   ``20s`` = ``20secs`` = ``20seconds``: 20 seconds
*   ``5m`` = ``5minutes`` = ``5min``: 5 minutes
*   ``2h`` = ``2hours`` = ``2hrs``: 2 hours
*   ``1d`` = ``1day``: one day
*   ``7d`` = ``7days``: a week

You can also stack them like this:

*   ``5m30s``: 5 minutes and 30 seconds
*   ``1d12h``: One day and a half
*   ``1h45m``: 1 hours and 45 minutes

.. attention:: Deleting the warning through the ``[p]warnings`` command does
    not remove the ban.

**Examples**

*   .. code-block:: none

        [p]warn 5 @El Laggron#0260 Harassing
    
    Bans El Laggron forever from the server.

*   .. code-block:: none

        [p]warn 5 @El Laggron#0260 7d Doesn't respect the previous warnings
    
    Bans El Laggron for a week from the server, then unbans him.

*   .. code-block:: none

        [p]warn 5 348415857728159745 Advertising for a weird dating website,
        then leaves.
    
    Bans El Laggron forever while he is not on the server.

**Arguments**

*   ``<member>``: The member to warn. Can either be a mention, the name + tag,
    the name, the nickname or an ID.

*   ``[reason]``: The reason of the warn. Omitting this will set the reason as
    "No reason set.".

^^^^^^^
warnset
^^^^^^^

**Syntax**

.. code-block:: none

    [p]warnset

**Description**

Base command used for all WarnSystem settings.

""""""""""""""""
warnset settings
""""""""""""""""

**Syntax**

.. code-block:: none

    [p]warnset settings

**Description**

Lists all settings defined on the current server.

"""""""""""""""
warnset channel
"""""""""""""""

**Syntax**

.. code-block:: none

    [p]warnset channel <channel> [level]

**Description**

Defines the modlog channel for the cog. This is a required step before warning
members.

.. note:: You can also use the core Red modlog by loading the modlogs cog, then
    using the ``[p]modlogset modlog`` command.

If you want to set a different modlog for a specific warning level (like,
sending ban warnings in a different channel), you can provide the warning level
after your channel to set it as the modlog channel for this specific warning
level.

**Arguments**

*   ``<channel>``: The text channel where the modlog will be set.

*   ``[level]``: The warning level associated to the channel. If this is not
    provided, the channel will be set as the default modlog channel.

""""""""""""
warnset mute
""""""""""""

**Syntax**

.. code-block:: none

    [p]warnset mute [role]

**Description**

Creates a role used for muting the members, or set an existing one as the mute
role. If you don't provide any role, the bot will create one below his top
role, then deny the "Send messages" and "Add reactions" on all text channels.
**Editing all channels takes a long time, depending on the number of text
channels you have on the server,** so don't worry if nothing happens for about
30 seconds, it's doing the setup for the mute.

You can also provide an existing role to set it as the new mute role.
**Permissions won't be modified in any channel in that case**, so make sure you
have the right permissions setup for that role.

**Arguments**

*   ``[role]``: The exact name of an existing role to set it as the mute role.
    If this is omitted, a new role will be created.

""""""""""""""""
warnset reinvite
""""""""""""""""

**Syntax**

.. code-block:: none

    [p]warnset reinvite [enable]

**Description**

Enables or disables the DM sent to unbanned members. If you enable this, make
sure the bot has the permission to create new invites.

This is enabled by default.

**Arguments**

*   ``[enable]``: The new status to set. If omitted, the bot will display the
    current setting and show how to reverse it.

"""""""""""""""""
warnset hierarchy
"""""""""""""""""

**Syntax**

.. code-block:: none

    [p]warnset hierarchy [enable]

**Description**

Enables or disables the hierarchy respect. If you enable this, the bot will
make sure the moderator is allowed to warn someone with the Discord hierarchy
rules (cannot warn someone if the warned member has a role equal or higher than
the moderator's top role).

This is disabled by default.

**Arguments**

*   ``[enable]``: The new status to set. If omitted, the bot will display the
    current setting and show how to reverse it.

"""""""""""""""
warnset showmod
"""""""""""""""

**Syntax**

.. code-block:: none

    [p]warnset showmod [enable]

**Description**

Toggles if the bot should show or hide the responsible moderator of a warn to
the warned member in DM.

This is disabled by default.

**Arguments**

*   ``[enable]``: The new status to set. If omitted, the bot will display the
    current setting and show how to reverse it.

"""""""""""""""
warnset bandays
"""""""""""""""

**Syntax**

.. code-block:: none

    [p]warnset bandays <ban_type> <days>

**Descritpion**

Defines how many days of messages should be deleted when a member is banned or
softbanned. The number of days can be between 1 and 7. You can set 0 to disable
message deletion for the bans, not for softbans.

**Arguments**

*   ``<ban_type>``: The type of ban that should be edited. Either ``ban`` or
    ``softban``.

*   ``<days>``: The number of days of messages that should be deleted. Between
    1 and 7 only. 0 to disable for bans.

"""""""""""""""""""""
warnset substitutions
"""""""""""""""""""""

**Syntax**

.. code-block:: none

    [p]warnset substitutions add <name> <text>
    [p]warnset substitutions [delete|del] <name>
    [p]warnset substitutions list

**Description**

Group command for managing the substitutions. A substitution is used to replace
a small word in brackets by a long sentence in your warn reason, to avoid
repetitions when taking actions.

Use ``[p]warnset substitutions add <name> <text>`` to create a substitution,
where ``<name>`` is the keyword and ``<text>`` is what will replace the
keyword.

Use ``[p]warnset delete`` to delete a substitution and ``[p]warnset list`` to
list them.

**Example**

| ``[p]warnset substitutions add lastwarn This is your last warning!``
| This creates a substitution with the keyword ``lastwarn``.

| ``[p]warn 3 @El Laggron#0260 Racist insults. [lastwarn]``
| The reason of this warn will be: Racist insults. This is your last warning!

"""""""""""""""""""
warnset description
"""""""""""""""""""

**Syntax**

.. code-block:: none

    [p]warnset description <level> <destination> <description>

**Description**

Edits the description of an embed for the modlog or the warned member. The
default description for the modlog is "A member got a level (x) warning.", for
the member, it is "The moderation team set you a level (x) warning.".

You can use the following keys in your custom description:

*   ``{invite}``: Generates an invite for the server and place it.

*   ``{member}``: The warned member. You can use attributes such as
    ``{member.name}``, ``{member.id}``, ``{member.nick}``...

*   ``{mod}``: The responsible mod of a warn. You can use the same attributes
    as for ``{member}``.

*   ``{duration}``: The duration of a mute/ban if set.

*   ``{time}``: The current date and time.

**Arguments**

*   ``<level>``: The level of the warn to edit.

*   ``<destination>``: Either ``user`` for the warned member or ``modlog`` for
    the modlog.

*   ``<description>``: The new description.

"""""""""""""""
warnset convert
"""""""""""""""

**Syntax**

.. code-block:: none

    [p]warnset convert <path>

**Description**

Converts a V2 BetterMod history file to migrate its logs to WarnSystem V3.

The history file is located at the following path:
``Red-DiscordBot/data/bettermod/history/<server ID>.json``. You can grab your
server ID with the ``[p]serverinfo`` command.

You can decide to append or overwrite the logs to the current logs through
the guided configuration. Append will get the logs and add them, while
overwrite will reset the current logs and replace them with the migrated ones.

**Example**

*   .. code-block:: none

        [p]warnset convert /home/laggron/Desktop/Red-DiscordBot/data/bettermod/history/363008468602454017.json

**Arguments**

*   ``<path>``: The path to your history file.

^^^^^^^^^^^^^^
warnsysteminfo
^^^^^^^^^^^^^^

.. note:: This command is locked to the bot owner.

**Syntax**

.. code-block:: none

    [p]warnsysteminfo [sentry]

**Description**

Shows multiple informations about WarnSystem such as its author, its version,
the status of Sentry logging, the link for the Github repository, the Discord
server and the documentation, and a link for my Patreon if you want to support
my work ;)

If you provide ``sentry`` after your command, you will enable or disable Sentry
logging on the instance for the cog.
