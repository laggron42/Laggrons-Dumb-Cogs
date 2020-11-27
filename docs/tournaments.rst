===========
Tournaments
===========

This is the guide for the ``tournaments`` cog. Everything you need is here.

``[p]`` is considered as your prefix.

.. tip:: If you're a french user, you should check the website of my public
    Red instance : `<https://atos.laggron.red/>`_, the documentation for
    Tournaments is way more detailed towards end users.

------------
Installation
------------

To install the cog, first load the downloader cog, included
in core Red.::

    [p]load downloader

Then you will need to install the Laggron's Dumb Cogs repository::

    [p]repo add Laggrons-Dumb-Cogs https://github.com/retke/Laggrons-Dumb-Cogs

Finally, you can install the cog::

    [p]cog install Laggrons-Dumb-Cogs tournaments

.. warning:: The cog is not loaded by default.
    To load it, type this::

        [p]load tournaments

-----
Usage
-----

The tournaments cog provides advanced tools for organizing your
`Challonge <https://challonge.com/>`_) tournaments on your Discord server!

From the beginning to the end of your tournament, members of your server will
be able to join and play in your tournaments without even creating a
Challonge account.

The cog supports the registration and check-in of the tournament, including
seeding with Braacket.

Then, once the game starts, just sit down and watch ~~the magic~~ the bot
manage everything:

*   For each match, a channel will be created with the two players of this
    match.

*   They have their own place for discussing about the tournament, checking
    the stage list, banning stages/characters...

*   The bot checks activity in the channels. If one player doesn't talk within
    the first minutes, he will be disqualified.

*   Once the players have done their match, they can set their score with a
    command.

*   Players can also forfeit a match, or disqualify themselves.

*   As the tournament goes on, outdated channels will be deleted, and new ones
    will be created for the upcoming matches, the bot is constantly
    checking the bracket.


The T.O.s, short for Tournament Organizers, also have their set of tools:

*   Being able to see all the channels and directly talk in one in case of a
    problem makes their job way easier

*   If a match takes too long, they will be warned in their channel to prevent
    slowing down the bracket

*   They can directly modify the bracket on Challonge (setting scores,
    resetting a match), and the bot will handle the changes, warning players
    if their match is cancelled or has to be replayed. A warning is also
    sent in the T.O. channel.

*   Players can call a T.O. for a lag test for example, and a message will
    be sent in the defined T.O. channel


Add to all of this tools for streamers too!

*   Streamers can add themselves to the tournament (not as a player) and
    comment some matches

*   They will choose the matches they want to cast, and also provide
    informations to players (for example, the room code and ID for smash bros)

*   If a match is launched but attached to a streamer, it will be paused until
    it is their turn. They will then receive the informations set above.

*   The streamer has access to the channels, so that he can also communicate
    with the players.

This was tested with tournaments up to 256 players, and I can personnaly
confirm this makes the organizers' job way easier.

^^^^^^^^^^^^^^^^^^
Setting up the cog
^^^^^^^^^^^^^^^^^^

There are multiple settings to configure before starting your tournament.

Most of these settings are optional, unless told.

First, set your Challonge credentials! This is specific to your server.

Use ``[p]challongeset username <your_challonge_username>``, then
``[p]challongeset api``. **Do not directly provide your token with the
command**, the bot will ask for it in DM, with the instructions.

.. warning:: Your token must stay secret, as it gives access to your account.

----

Then you can set the following channels with ``[p]tset channels``:

*   ``announcements``, where the bot announces registration, start and end of
    the tournament.

*   ``checkin``, where members will have to check (includes announcement).
    If this isn't set, members will be able to check everywhere.

*   ``queue``, where the bot announces the started matches.

*   ``register``, where members will be able to register (includes a pinned
    message with the count of participants updated in real time).
    If this isn't set, members will be able to register everywhere.

*   ``scores``, where participants will use the ``[p]win`` command to set their
    score. If this isn't set, participants will be able to
    use this command everywhere.

*   ``stream``, where sets going on stream will be announced.

*   ``to``, where the bot warns the T.O.s about important info (bracket
    modifications, participants asking for help). **Setting this is required.**

----

Next step, the roles with ``[p]tset roles``:

*   ``participant``, the role given to all participants when they register.
    **Setting this is required.**

*   ``streamer``, the role that gives access to the streamer commands.

*   ``to``, gives access to the T.O. commands. **This does not include the
    ``[p]tset`` command.**

.. attention:: The ``to`` role is available **if your T.O.s aren't
    moderators in your server**. If your T.O.s are moderators or
    administrators, use the core commands ``[p]set addmodrole`` and
    ``[p]set addadminrole`` instead, which will adapt the permissions of
    the entire bot to your mods and admins.

----

Some additional settings you can set:

*   ``[p]tset delay`` defines when a player is considered AFK and must be
    disqualified. This only listens for his first message in his channel, once
    someone spoke, he's safe. Defaults to 10 minutes.

*   ``[p]tset start_bo5`` defines at what point you want to move from BO3
    format to BO5.

*   ``[p]tset warntime`` customize the warnings sent for match duration.

*   ``[p]tset register`` defines when the registration should start and stop.
    See details in the :ref:`registrations section <register-checkin>`.

*   ``[p]tset checkin`` defines when the check-in should start and stop.
    See details in the :ref:`registrations section <register-checkin>`.

*   ``[p]tset autostopregister`` if registrations should be closed when filled.
    See details in the :ref:`registrations section <register-checkin>`.

*   ``[p]tset twostageregister`` defines a second start for registrations.
    See details in the :ref:`registrations section <register-checkin>`.

----

Finally, we can add our first game!

Some settings are dependant to a specific game, and this is where you set them.

Use ``[p]tset games add <name>`` to start. The name of the game must be the
same as the one provided by Challonge.

The bot will then give you the next commands to use. You can also type
``[p]help tset games``.

You will be able to define the legal stage list, list of counters, channel of
rules, role allowed to register (also pinged on registration start), info on
the mode of bans (like 3-4-1), and even braacket informations for seeding.

.. _register-checkin:

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Registration and check-in phases
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The cog handles registrations and check-in, automatic or manual.

Type ``[p]register start`` to start registrations. An announcement will be
sent, and the command ``[p]in`` will be available.

*   If you configured a registrations channel, the bot will open that channel
    to your game role and the ``[p]in`` command will be locked to the channel.
    There is also a message pinned with the number of participants.

Then type ``[p]register stop`` to end this phase. You can resume it later.

----

It's pretty much the same thing for check-in, but you have to keep some things
in mind:

*   The check-in requires all registered participants to confirm their presence
    by typing ``[p]in`` again.

*   When ending the check-in, all unchecked participants will be removed.

*   If you configured a closing date, the bot may send reminders, pinging
    and/or DMing remaining members. This can be done manually with ``[p]checkin
    call``.

"""""""""""""""""""""""""
Automatic opening/closing
"""""""""""""""""""""""""

You can configure opening and closing dates for both, based on tournament's
start date.

You have to calculate the number of minutes before the scheduled start time.

Here's an example situation:

*   Your tournament starts on **Saturday at 3:00 PM**
*   You want registrations to start on **Friday at 7:00 PM**
*   You need a check-in on **Saturday betweeen 2:00 and 2:40 PM**
*   Registrations should end on **Saturday at 2:45 PM**

You will have to run the following commands:

*   ``[p]tset register 1200 15``: opens 1200 minutes (20 hours) and closes 15
    minutes before tournament's start time.

*   ``[p]tset checkin 60 20``: opens 60 minutes (1 hour) and closes 20
    minutes before tournament's start time.

.. tip:: If you're unsure, the bot will give you the exact date and time
    calculated for both phases when setting up a tournament, asking for
    confirmation.

Even with this configured, you can still use the commands to manually start
and stop.

"""""""""""""""""""
Close when complete
"""""""""""""""""""

For large scale tournaments, you may not want to keep the registrations ongoing
forever with everyone spamming for a place.

You can make the bot automatically close registrations when the limit of
participants (defined on Challonge) is reached by enabling the setting with
``[p]tset autostopregister``.

"""""""""""""""""""""""
Two-stage registrations
"""""""""""""""""""""""

Once again useful for big tournaments that uses the previous setting, you can
give a second opening time for registrations.

The bot will try opening registrations if they're closed, else nothing
happens.

Configure that second time with ``[p]tset twostageregister``.

Let's use our previous example. Registrations end very soon due to the
number of participants, but you want to have last-minute registrations for
the places left by check-in. So, as soon as the check-in ends, registrations
are re-opened. Then type this :

*   ``[p]tset twostageregister 20`` reopens 20 minutes before tournament
    start.

The configured closing time is still applied.

----

All good! We went across all settings, you can check those with the
``[p]tset settings`` and ``[p]tset games show`` commands.

^^^^^^^^^^^^^^^^
Add a tournament
^^^^^^^^^^^^^^^^

You can then create a tournament on Challonge.

Make sure the format is correct (single/double elimination), game name set,
and start time configured.

Then you can run ``[p]setup`` with the link of your tournament. Check that
all informations are correct then confirm.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Start and manage the tournament
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Once you consider everything is good (check the bracket online to make sure),
start the tournament with ``[p]start``.

You may want to make sure participants are uploaded to the bracket with
``[p]upload`` before (clears previous list and seeding).

Multiple things will occur: first the tournament will be marked as started on
Challonge, then the bot will send all the initial messages in the defined
channels, and finally, the matchs will be launched.

The beginning is pretty impressive, because a lot of channels will start being
created. If you host a 128 players tournament, except 64 new channels in new
categories.

----

First thing to note: if a player does not talk in his channel within the 10
first minutes after the channel creation, he will be disqualified (you can
customize or disable this delay with ``[p]tset delay``). You are warned of this
in the T.O. channel.

If the bot somehow fails to create a channel, the match will be moved in DM
(the bot announces the set in DM, timers and AFK check are therefore disabled).

Players are able to use the ``[p]lag`` command, asking for a lag test. A
message will then be sent in the T.O. channel.

If a set takes too much time, the players will be warned first, then if it is
still not done, a message is sent in the T.O. channel (customizable with
``[p]tset warntime``).

You can edit things in the bracket yourself, such as setting a score or even
resetting a match. The bot should handle all changes, resulting in matches
being terminated (score set), relaunched (score reset) or even cancelled
(score reset with child matches ongoing). This will also be announced in the
T.O. channel.

The winner of a match will set his score with the ``[p]win`` command, inside
the scores channel if set.

Players can use at any time ``[p]ff`` for forfeiting a match (they can still
continue depending on the tournament mode, such as the usage of a loser
bracket), or ``[p]dq`` for completly disqualifying themselves.

T.O.s can disqualify players with ``[p]rm``.

.. tip:: To re-enable a disqualified player (because of an AFK check, or the
    ``[p]dq``/``[p]rm`` commands), do this directly on the bracket.

    On Challonge, go to the participants tab, and click on the "Reactivate"
    button.

If you need to restart the tournament, use the ``[p]resetbracket`` command.
Channels will be deleted, and the tournament will fall back to its previous
state. You can then either start again with ``[p]start`` or just remove it
with ``[p]reset``.

^^^^^^^^^^^^^^
Manage streams
^^^^^^^^^^^^^^

The cog comes with streaming support, aka managing a stream queue for streamers
who want to share and comment a match. The ``[p]stream`` command is accessible
to anyone, displaying the links of the current streamers. However, the sub
commands are only accessible to mods, T.O.s and streamers (role defined with
``[p]tset roles streamer``).

Here are the steps for adding a streamer to the tournament (only accessible
once the tournament has started):

1.  Initialize your stream with ``[p]stream init <link>``, where ``<link>`` is
    the URL of your Twitch channel.

2.  (Optional) Smash Bros. Ultimate streamers can setup the info of their room
    (ID + code) that will be shared to the players once it is their turn with
    ``[p]stream set <id> <code>``.

3.  Add matches to your stream queue with ``[p]stream add``. You can add sets
    that will start in the future, or even sets that already started (the bot
    will ping them, either for telling them to go on stream or to stop playing
    and wait for their turn). You can add multiple sets at once. Example for
    scheduling the top 4 of a 128 players tournament: ``[p]stream add 251 252
    253 254 255`` (the number of the sets can be found on Challonge).

4.  Remove scheduled matches with ``[p]stream remove`` followed by the sets.
    You can clear your queue with ``[p]stream remove all``.

5.  See the infos about your stream (such as the queue) with ``[p]stream
    info``.

6.  Reorder your stream queue with the following commands:

    *   ``[p]stream swap <set1> <set2>`` for swapping the position of two sets
        in your queue.
    
    *   ``[p]stream insert <set1> <set2>`` for inserting set 1 right before
        set 2 in the queue.
    
    *   ``[p]stream reorder`` for giving the entire order. This will add or
        remove sets if they're different from the previous stream queue.

7.  End your stream with ``[p]stream end``, cancelling your queue and sending
    players back to the game.

You can type ``[p]stream list`` for seeing all streamers. Note that a set
going on stream will be announced in the channel defined with ``[p]tset
channels stream``.

.. tip:: Any T.O. or streamer can edit anyone's stream by providing their
    channel as the first argument of the command. Examples:

    *   ``[p]stream add https://twitch.tv/el_laggron 254``
    *   ``[p]stream info el_laggron``

    This allows you to setup a stream for someone yourself, then transferring
    the ownership of this stream with ``[p]stream transfer``, making things
    easier for them.

--------------------
Additional resources
--------------------

^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Common Challonge error codes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The bot will usually provide an explaination for the most frequeunt error
codes from Challonge. Here's a table in case of:

+-------+------------------------------------------------------------------+
| Error | Explaination                                                     |
+=======+==================================================================+
| 401   | * The credentials are invalid                                    |
|       | * The user setup does not have access on that tournament         |
+-------+------------------------------------------------------------------+
| 404   | * The URL given is invalid                                       |
|       | * The tournament is hosted by a community (not supported by API) |
|       | * The tournament was deleted                                     |
|       | * The tournament's URL or host changed                           |
+-------+------------------------------------------------------------------+
| 422   | Can mean multiple things...                                      |
|       |                                                                  |
|       | * When uploading participants                                    |
|       |                                                                  |
|       |   * The limit was probably hit.                                  |
|       |     The bot could have registered too many                       |
|       |     participants, or the limit changed on Challonge.             |
|       |                                                                  |
|       | * When starting the tournament                                   |
|       |                                                                  |
|       |   * There are not enough participants on                         |
|       |     Challonge. Did the upload fail?                              |
|       |     Try ``[p]upload`` and try again.                             |
|       |                                                                  |
|       |   * You enabled the check-in via Challonge.                      |
|       |     Check members there or disable this.                         |
|       |                                                                  |
|       | * When closing the tournament (supressed)                        |
|       |                                                                  |
|       |   * The tournament was already closed by someone manually        |
|       |                                                                  |
|       | If there's a case I didn't mention, error means                  |
|       | "Unprocessable entity", so you're trying to do something         |
|       | inconsistant for Challonge. Check directly what                  |
|       | could be wrong on the bracket.                                   |
+-------+------------------------------------------------------------------+
| 502   | A sadly very common error, meaning Challonge is                  |
|       | being unstable again. Just try again later.                      |
+-------+------------------------------------------------------------------+

^^^^^^^^^^^^^^^
Troubleshooting
^^^^^^^^^^^^^^^

Having a critical bug in the middle of your tournament can be very annoying,
so this cog provides you advanced tools to attempt a fix while the
tournament is running with the ``[p]tfix`` command.

.. warning:: Those commands are high-level, and not knowing what you do can
    ruin your entire tournament, so *please* make sure to read the description
    of each command with ``[p]help tfix <your command>``.

----

First, the commands with the lowest risk level.

One thing to note, the bot fetches informations about the tournament only
during inital setup with ``[p]setup``. If you changed things like the limit
of participants or the tournament's name, use ``[p]tfix refresh``.

.. attention:: The following things will not be updated with
    ``[p]tfix refresh``:

    *   The game of the tournament (settings are based on this)
    *   Custom URL (the bot will return 404 if you do this, so don't try)

    *   The tournament's start date and time. Since registration and check-in
        opening and closing times are already calculated on this, redoing this
        process would be too hard to implement, with the ton of additional
        checks that comes with it.

If anything doesn't work correctly, try ``[p]tfix reload`` first. This is the
command that does the most: save, delete all objects we have in memory, then
rebuild the objects from what's saved on disk. Sounds like a lot, but this one
of the most stable functions since I kept spamming reloads when coding and
testing, so any issue with this was quickly fixed. However, if something wrong
happens, don't panic, and use the next command.

``[p]tfix restore`` can be used to attempt loading a tournament that is
saved on disk but not on the bot. If your bot suddenly tells you "There is
no tournament setup" (or the previous command failed), then you're looking for
this. If there are more issues, check the details in the logs, or ask a bot
administrator to help you.

----

Before explaining the next commands, let me explain what is the background loop
task. This is a task launched when you start your tournament that runs every
15 seconds, and does the following things :

*   Update the internal list of participants
*   Update the internal list of matches
*   Launch pending matches

*   Check for AFK players (someone didn't talk within the first 10 minutes in
    his channel, configurable with ``[p]tset delay``), and delete inactive
    channels (score reported and no message sent for 5 minutes)

*   Call streams

If too many errors occur in this task, it will be stopped, and you may not be
aware of this until you see that new matches stop being launched. You can
check the status of the task with ``[p]tinfo``.

Suppose you want to edit a lot of things in the bracket yourself, and you don't
want the bot to create 25 new channels and immediatly delete them, so you want
to pause this background task. Use ``[p]tfix pausetask`` and the bot won't
start new matches or look for bracket changes anymore.

You can then either use ``[p]tfix runtaskonce`` to only refresh matches and
launch matches once to check, or use ``[p]tfix resumetask`` to fully resume
the task. You can also use this last command to restore a task that bugged.

----

Finally, the danger zone. Those commands will perform a hard reset and cannot
restore what you had, depending on what you chose.

During registration and check-in, you can use ``[p]tfix resetparticipants``,
which will remove all participants from memory (not from the bracket if already
uploaded). If you want the bot to also remove the members' participant role,
call ``[p]tfix resetparticipants yes``, else everyone will keep their roles.

During the tournament, you can use ``[p]tfix resetmatches`` which removes all
matches and participants objects from memory. If the background task is still
running, the list of participants and matches will quickly be fetched back
from the bracket, re-creating fresh objects and new channels. Note that all
match channels existing when you run this command will be forgotten by the bot
and unusable. Like the command above, you can call ``[p]tfix resetmatches yes``
to make the bot delete all channels.

At whatever phase of the tournament, you can use ``[p]tfix hardreset``. See
this as the latest possible option, as this will simply delete all
internal objects, without trying anything else. It's like a factory reset,
put the bot back to its initial state, regardless of the current state (does
not reset settings). There is no announcement, no DM, no channel
cleared/removed, the bot will just say "There is no tournament" on commands.
Channels and roles will still be in place, everything will just stop. No API
call is sent to the bracket, it will stay as it is.

Before considering this, you must be sure of the consequences. Try to look
into other options first, like ``[p]reset``, ``[p]resetbracket`` or other
``[p]tfix`` commands.
