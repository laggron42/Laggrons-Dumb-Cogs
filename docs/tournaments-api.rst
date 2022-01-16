.. role:: python(code)
    :language: python

===========
Tournaments
===========

-------------
API Reference
-------------

^^^^^^^^^^^^^^
Helper classes
^^^^^^^^^^^^^^

.. autoclass:: tournaments.objects.Buttons
    :members:

.. autoclass:: tournaments.objects.Channels
    :members:

.. autoclass:: tournaments.objects.Roles
    :members:

.. autoclass:: tournaments.objects.Settings
    :members:

.. class:: tournaments.objects.Phase
    
    Represents the current state of the tournament.

    .. attribute:: PENDING

        The tournament has been setup and is waiting for participants.
    
    .. attribute:: REGISTER

        Registrations and/or checkin is ongoing.
    
    .. attribute:: AWAITING

        Registrations are done and the tournament is ready to start.
    
    .. attribute:: ONGOING

        The tournament has been started and is ongoing.
    
    .. attribute:: DONE

        Tournament is over. This is generally never accessible as the
        tournament is immediatly erased from memory.

.. class:: tournaments.objects.EventPhase
    
    Represents the current state of an event (registrations or check-in)

    .. attribute:: MANUAL

        No start date setup, the event must be started manually.
    
    .. attribute:: PENDING

        The event has a start date and is waiting to start automatically.
    
    .. attribute:: ONGOING

        The event is open and running.
    
    .. attribute:: ON_HOLD

        The event was stopped but will be opened a second time (second start
        registrations or a manual stop)
    
    .. attribute:: DONE

        Event is now done and shouldn't be opened again.

.. autoclass:: tournaments.objects.Event
    :members:

.. autoclass:: tournaments.objects.RegisterEvent
    :members:

.. autoclass:: tournaments.objects.CheckinEvent
    :members:

^^^^
Base
^^^^

""""""""""
Tournament
""""""""""

.. autoclass:: tournaments.objects.Tournament
    :members:
    :private-members: _get_all_rounds, _update_participants_list, _update_match_list

"""""""""""
Participant
"""""""""""

.. autoclass:: tournaments.objects.Participant
    :members:

"""""
Match
"""""

.. autoclass:: tournaments.objects.Match
    :members:

""""""""
Streamer
""""""""

.. autoclass:: tournaments.objects.Streamer
    :members:

^^^^^^^^^^^^^
Challonge API
^^^^^^^^^^^^^

.. autoclass:: tournaments.objects.ChallongeTournament
    :members:

.. autoclass:: tournaments.objects.ChallongeParticipant
    :members:

.. autoclass:: tournaments.objects.ChallongeMatch
    :members:
