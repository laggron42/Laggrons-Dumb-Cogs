.. role:: python(code)
    :language: python

===========
Tournaments
===========

-------------
API Reference
-------------

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
