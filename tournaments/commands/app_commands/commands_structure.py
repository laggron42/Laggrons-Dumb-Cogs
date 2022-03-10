# flake8: noqa: E501

SLASH_COMMANDS = [
    {
        "type": 1,
        "name": "tset",
        "description": "Tournament settings",
        "default_permission": False,
        "options": [
            {
                "type": 1,
                "name": "challonge",
                "description": "Set Challonge identifiers",
                "options": [
                    {
                        "type": 3,
                        "name": "username",
                        "description": "Your Challonge username",
                        "required": True,
                    },
                    {
                        "type": 3,
                        "name": "api_key",
                        "description": "Your Challonge API key. Get one here: https://challonge.com/settings/developer",
                        "required": True,
                    },
                    {
                        "type": 3,
                        "name": "config",
                        "description": "The config under which this setting will be saved",
                        "required": False,
                        "autocomplete": True,
                    },
                ],
            },
            {
                "type": 2,
                "name": "channels",
                "description": "Set different channels",
                "options": [
                    {
                        "type": 1,
                        "name": "announcements",
                        "description": "Where announcements about your tournament are sent",
                        "options": [
                            {
                                "type": 7,
                                "channel_types": [0, 5],  # text + news channel
                                "name": "channel",
                                "description": "The new channel to set, blank to reset",
                                "required": False,
                            },
                            {
                                "type": 3,
                                "name": "config",
                                "description": "The config under which this setting will be saved",
                                "required": False,
                                "autocomplete": True,
                            },
                        ],
                    },
                    {
                        "type": 1,
                        "name": "category",
                        "description": "Temporary channels will be created below that category",
                        "options": [
                            {
                                "type": 7,
                                "channel_types": [4],  # category channel
                                "name": "category",
                                "description": "The new category to set, blank to reset",
                                "required": False,
                            },
                            {
                                "type": 3,
                                "name": "config",
                                "description": "The config under which this setting will be saved",
                                "required": False,
                                "autocomplete": True,
                            },
                        ],
                    },
                    {
                        "type": 1,
                        "name": "queue",
                        "description": "All sets will be announced there once they start",
                        "options": [
                            {
                                "type": 7,
                                "channel_types": [0, 5],  # text + news channel
                                "name": "channel",
                                "description": "The new channel to set, blank to reset",
                                "required": False,
                            },
                            {
                                "type": 3,
                                "name": "config",
                                "description": "The config under which this setting will be saved",
                                "required": False,
                                "autocomplete": True,
                            },
                        ],
                    },
                    {
                        "type": 1,
                        "name": "registrations",
                        "description": "The channel where the registrations and checkin message is sent (defaults to announcements)",
                        "options": [
                            {
                                "type": 7,
                                "channel_types": [0, 5],  # text + news channel
                                "name": "channel",
                                "description": "The new channel to set, blank to reset",
                                "required": False,
                            },
                            {
                                "type": 3,
                                "name": "config",
                                "description": "The config under which this setting will be saved",
                                "required": False,
                                "autocomplete": True,
                            },
                        ],
                    },
                    {
                        "type": 1,
                        "name": "ruleset",
                        "description": "A channel with your tournament rules",
                        "options": [
                            {
                                "type": 7,
                                "channel_types": [0, 5],  # text + news channel
                                "name": "channel",
                                "description": "The new channel to set, blank to reset",
                                "required": False,
                            },
                            {
                                "type": 3,
                                "name": "config",
                                "description": "The config under which this setting will be saved",
                                "required": False,
                                "autocomplete": True,
                            },
                        ],
                    },
                    {
                        "type": 1,
                        "name": "stream",
                        "description": "Announce streamed sets in this channel",
                        "options": [
                            {
                                "type": 7,
                                "channel_types": [0, 5],  # text + news channel
                                "name": "channel",
                                "description": "The new channel to set, blank to reset",
                                "required": False,
                            },
                            {
                                "type": 3,
                                "name": "config",
                                "description": "The config under which this setting will be saved",
                                "required": False,
                                "autocomplete": True,
                            },
                        ],
                    },
                    {
                        "type": 1,
                        "name": "to",
                        "description": "The channel for tournament organisers (required)",
                        "options": [
                            {
                                "type": 7,
                                "channel_types": [0],  # text + news channel
                                "name": "channel",
                                "description": "The new channel to set, blank to reset",
                                "required": False,
                            },
                            {
                                "type": 3,
                                "name": "config",
                                "description": "The config under which this setting will be saved",
                                "required": False,
                                "autocomplete": True,
                            },
                        ],
                    },
                ],
            },
            {
                "type": 2,
                "name": "roles",
                "description": "Set different roles",
                "options": [
                    {
                        "type": 1,
                        "name": "participant",
                        "description": "The role given to registered players (required)",
                        "options": [
                            {
                                "type": 8,
                                "name": "role",
                                "description": "The new role to set, blank to reset",
                                "required": False,
                            },
                            {
                                "type": 3,
                                "name": "config",
                                "description": "The config under which this setting will be saved",
                                "required": False,
                                "autocomplete": True,
                            },
                        ],
                    },
                    {
                        "type": 1,
                        "name": "player",
                        "description": "Limit registrations to members of this role",
                        "options": [
                            {
                                "type": 8,
                                "name": "role",
                                "description": "The new role to set, blank to reset",
                                "required": False,
                            },
                            {
                                "type": 3,
                                "name": "config",
                                "description": "The config under which this setting will be saved",
                                "required": False,
                                "autocomplete": True,
                            },
                        ],
                    },
                    {
                        "type": 1,
                        "name": "streamer",
                        "description": "The role for streamers, giving access to stream-related commands",
                        "options": [
                            {
                                "type": 8,
                                "name": "role",
                                "description": "The new role to set, blank to reset",
                                "required": False,
                            },
                            {
                                "type": 3,
                                "name": "config",
                                "description": "The config under which this setting will be saved",
                                "required": False,
                                "autocomplete": True,
                            },
                        ],
                    },
                    {
                        "type": 1,
                        "name": "tester",
                        "description": "A role mentioned when a lag test is asked",
                        "options": [
                            {
                                "type": 8,
                                "name": "role",
                                "description": "The new role to set, blank to reset",
                                "required": False,
                            },
                            {
                                "type": 3,
                                "name": "config",
                                "description": "The config under which this setting will be saved",
                                "required": False,
                                "autocomplete": True,
                            },
                        ],
                    },
                    {
                        "type": 1,
                        "name": "to",
                        "description": "The role for tournament organisers, giving access to all commands",
                        "options": [
                            {
                                "type": 8,
                                "name": "role",
                                "description": "The new role to set, blank to reset",
                                "required": False,
                            },
                            {
                                "type": 3,
                                "name": "config",
                                "description": "The config under which this setting will be saved",
                                "required": False,
                                "autocomplete": True,
                            },
                        ],
                    },
                ],
            },
            {
                "type": 1,
                "name": "registrations",
                "description": "Set the time (before start of tournament) for opening and closing registrations/check-in",
                "options": [
                    {
                        "type": 3,
                        "name": "registrations_opening",
                        "description": "Time before opening registrations, omit to disable (format: 5d2h30m = 5 days 2 hours 30 min)",
                        "required": False,
                    },
                    {
                        "type": 3,
                        "name": "registrations_closing",
                        "description": "Time before closing registrations, omit to disable (format: 5d2h30m = 5 days 2 hours 30 min)",
                        "required": False,
                    },
                    {
                        "type": 3,
                        "name": "checkin_opening",
                        "description": "Time before opening check-in, omit to disable (format: 5d2h30m = 5 days 2 hours 30 min)",
                        "required": False,
                    },
                    {
                        "type": 3,
                        "name": "checkin_closing",
                        "description": "Time before closing check-in, omit to disable (format: 5d2h30m = 5 days 2 hours 30 min)",
                        "required": False,
                    },
                    {
                        "type": 3,
                        "name": "config",
                        "description": "The config under which this setting will be saved",
                        "required": False,
                        "autocomplete": True,
                    },
                ],
            },
            {
                "type": 1,
                "name": "timeout",
                "description": "Set the time before timing out a player for inactivity",
                "options": [
                    {
                        "type": 3,
                        "name": "time",
                        "description": "The new time to set, omit to disable (format: 2h30m15s = 2 hours 30 min 15 secs)",
                        "required": False,
                    },
                    {
                        "type": 3,
                        "name": "config",
                        "description": "The config under which this setting will be saved",
                        "required": False,
                        "autocomplete": True,
                    },
                ],
            },
            {
                "type": 1,
                "name": "warntime",
                "description": "Set the time before warning players for too long sets",
                "options": [
                    {
                        "type": 3,
                        "name": "first_warn",
                        "description": "Time before warning players in their channel, omit to disable (format: 30m = 30 min)",
                        "required": False,
                    },
                    {
                        "type": 3,
                        "name": "to_warn",
                        "description": "Time before warning organisers (in addition to the first time set), omit to disable",
                        "required": False,
                    },
                    {
                        "type": 3,
                        "name": "config",
                        "description": "The config under which this setting will be saved",
                        "required": False,
                        "autocomplete": True,
                    },
                ],
            },
            {
                "type": 1,
                "name": "ranking",
                "description": "Setup braacket.com for ranking and seeding (see docs)",
                "options": [
                    {
                        "type": 3,
                        "name": "url",
                        "description": "The URL of your braacket ranking, omit to disable",
                        "required": False,
                    },
                    {
                        "type": 3,
                        "name": "config",
                        "description": "The config under which this setting will be saved",
                        "required": False,
                        "autocomplete": True,
                    },
                ],
            },
            {
                "type": 2,
                "name": "config",
                "description": "Save multiple settings configurations for different tournaments",
                "options": [
                    {
                        "type": 1,
                        "name": "add",
                        "description": "Create a new config",
                        "options": [
                            {
                                "type": 3,
                                "name": "name",
                                "description": "Name of your config (can be the exact name of a game)",
                                "required": True,
                            }
                        ],
                    },
                    {
                        "type": 1,
                        "name": "clone",
                        "description": "Clone an existing config into a new one",
                        "options": [
                            {
                                "type": 3,
                                "name": "config",
                                "description": "The config you want to copy the data from",
                                "required": True,
                                "autocomplete": True,
                            },
                            {
                                "type": 3,
                                "name": "name",
                                "description": "Name of your new config (can be the exact name of a game)",
                                "required": True,
                            },
                        ],
                    },
                    {"type": 1, "name": "list", "description": "List existing configs"},
                    {
                        "type": 1,
                        "name": "remove",
                        "description": "Remove an existing config",
                        "options": [
                            {
                                "type": 3,
                                "name": "config",
                                "description": "The config you want to delete",
                                "required": True,
                                "autocomplete": True,
                            },
                        ],
                    },
                    {
                        "type": 1,
                        "name": "rename",
                        "description": "Rename an existing config",
                        "options": [
                            {
                                "type": 3,
                                "name": "config",
                                "description": "The config you want to copy the data from",
                                "required": True,
                                "autocomplete": True,
                            },
                            {
                                "type": 3,
                                "name": "new_name",
                                "description": "New name of your config (can be the exact name of a game)",
                                "required": True,
                            },
                        ],
                    },
                ],
            },
            {"type": 1, "name": "settings", "description": "List all of your settings"},
        ],
    },
    {
        "name": "registrations",
        "description": "Manage registrations and check-in",
        "default_permission": False,
        "options": [
            {
                "type": 1,
                "name": "start",
                "description": "Manually start the registrations now",
            },
            {
                "type": 1,
                "name": "stop",
                "description": "Manually stop the registrations now",
            },
            {
                "type": 2,
                "name": "checkin",
                "description": "Manually start and stop the check-in",
                "options": [
                    {
                        "type": 1,
                        "name": "start",
                        "description": "Manually start the check-in now",
                    },
                    {
                        "type": 1,
                        "name": "stop",
                        "description": "Manually stop the check-in now",
                    },
                ],
            },
            {
                "type": 1,
                "name": "list",
                "description": "Show the list of registered participants",
            },
            {
                "type": 1,
                "name": "fromrole",
                "description": "Register or check an entire role (useful for restoring broken tournaments)",
                "options": [
                    {
                        "type": 8,
                        "name": "role",
                        "description": "The role whose members will be registered",
                        "required": True,
                    }
                ],
            },
            {
                "type": 1,
                "name": "upload",
                "description": "Force upload all participants to the bracket",
                "options": [
                    {
                        "type": 5,
                        "name": "force",
                        "description": "Reset any custom seeding and force upload everyone",
                        "required": False,
                    }
                ],
            },
            {
                "type": 1,
                "name": "add",
                "description": "Register or check a member manually",
                "options": [
                    {
                        "type": 6,
                        "name": "member",
                        "description": "The member to register or check to the tournament",
                        "required": True,
                    }
                ],
            },
            {
                "type": 1,
                "name": "remove",
                "description": "Unregister a member manually",
                "options": [
                    {
                        "type": 6,
                        "name": "member",
                        "description": "The member to remove from tournament",
                        "required": True,
                    }
                ],
            },
        ],
    },
    {
        "type": 1,
        "name": "tfix",
        "description": "Advanced actions for editing your tournament live. DO NOT USE WITHOUT ADVICE",
        "default_permission": False,
        "options": [
            {
                "type": 1,
                "name": "hardreset",
                "description": "Hard reset everything saved for the current tournament (CANNOT BE UNDONE)",
            },
            {
                "type": 1,
                "name": "refresh",
                "description": "Refresh the tournament name and limit of participants from the bracket",
            },
            {
                "type": 1,
                "name": "reload",
                "description": "Internally reload the tournament from disk (like a Windows restart)",
            },
            {
                "type": 1,
                "name": "resetmatches",
                "description": "Reset the internal list of matches (WILL RELAUNCH EVERYTHING)",
            },
            {
                "type": 1,
                "name": "resetparticipants",
                "description": "Reset the internal list of participants",
            },
            {
                "type": 1,
                "name": "restore",
                "description": "Attempts to restore a lost tournament from disk",
            },
            {
                "type": 2,
                "name": "task",
                "description": "Interact with the internal task (continuous update from the bracket)",
                "options": [
                    {
                        "type": 1,
                        "name": "pause",
                        "description": "Pause the internal task, stopping new matches from appearing",
                    },
                    {
                        "type": 1,
                        "name": "resume",
                        "description": "Resume the internal task",
                    },
                    {
                        "type": 1,
                        "name": "runonce",
                        "description": "Run the internal task only once to check behaviour",
                    },
                ],
            },
        ],
    },
    {
        "type": 1,
        "name": "tinfo",
        "description": "Get information about the currently setup tournament",
        "default_permission": False,
    },
    {
        "type": 1,
        "name": "start",
        "description": "Start the tournament",
        "default_permission": False,
    },
    {
        "type": 1,
        "name": "lsmatches",
        "description": "List the ongoing sets in the tournament",
        "default_permission": False,
    },
    {
        "type": 1,
        "name": "setscore",
        "description": "Set the score for an ongoing set manually",
        "default_permission": False,
        "options": [
            {
                "type": 3,
                "name": "set",
                "description": "The set you want to edit",
                "required": True,
                "autocomplete": True,
            }
        ],
    },
    {
        "type": 1,
        "name": "reset",
        "description": "Reset the currently setup tournament OR the ongoing bracket if launched",
        "default_permission": False,
    },
    {
        "type": 1,
        "name": "stream",
        "description": "Manage the stream queue",
        "default_permission": False,
        "options": [
            {
                "type": 1,
                "name": "add",
                "description": "Add sets to a stream queue",
                "options": [
                    {
                        "type": 3,
                        "name": "sets",
                        "description": "List of sets, separated by spaces",
                        "required": True,
                    },
                    {
                        "type": 3,
                        "name": "streamer",
                        "description": "The stream queue to edit, defaults to yours",
                        "required": False,
                        "autocomplete": True,
                    },
                ],
            },
            {
                "type": 1,
                "name": "end",
                "description": "End a stream",
                "options": [
                    {
                        "type": 3,
                        "name": "streamer",
                        "description": "The stream to end, defaults to yours",
                        "required": True,
                        "autocomplete": True,
                    }
                ],
            },
            {
                "type": 1,
                "name": "info",
                "description": "Info about a stream queue",
                "options": [
                    {
                        "type": 3,
                        "name": "streamer",
                        "description": "The stream queue to get info about, defaults to yours",
                        "required": True,
                        "autocomplete": True,
                    }
                ],
            },
            {
                "type": 1,
                "name": "init",
                "description": "Initialize a new stream queue",
                "options": [
                    {
                        "type": 3,
                        "name": "link",
                        "description": "The link to your Twitch channel",
                        "required": True,
                    }
                ],
            },
            {
                "type": 1,
                "name": "insert",
                "description": "Insert an existing set in a stream queue (reorder)",
                "options": [
                    {
                        "type": 3,
                        "name": "set_to_insert",
                        "description": "The set you want to move somewhere",
                        "required": True,
                        "autocomplete": True,
                    },
                    {
                        "type": 3,
                        "name": "set_new_position",
                        "description": "Where you want to move your set (will be inserted before selected set)",
                        "required": True,
                        "autocomplete": True,
                    },
                    {
                        "type": 3,
                        "name": "streamer",
                        "description": "The stream queue to edit, defaults to yours",
                        "required": False,
                        "autocomplete": True,
                    },
                ],
            },
            {
                "type": 1,
                "name": "remove",
                "description": "Remove a set from a stream queue",
                "options": [
                    {
                        "type": 3,
                        "name": "set_to_remove",
                        "description": "The set you want to remove",
                        "required": True,
                        "autocomplete": True,
                    },
                    {
                        "type": 3,
                        "name": "streamer",
                        "description": "The stream queue to edit, defaults to yours",
                        "required": False,
                        "autocomplete": True,
                    },
                ],
            },
            {
                "type": 1,
                "name": "replace",
                "description": "Replace an entire stream queue (add, remove, reorder)",
                "options": [
                    {
                        "type": 3,
                        "name": "sets",
                        "description": "The new list of sets, separated by spaces",
                        "required": True,
                    },
                    {
                        "type": 3,
                        "name": "streamer",
                        "description": "The stream queue to edit, defaults to yours",
                        "required": False,
                        "autocomplete": True,
                    },
                ],
            },
            {
                "type": 1,
                "name": "setinfo",
                "description": "Define the information about your current room",
                "options": [
                    {
                        "type": 3,
                        "name": "room_id",
                        "description": "ID of the room",
                        "required": True,
                    },
                    {
                        "type": 3,
                        "name": "room_passcode",
                        "description": "Passcode of the room",
                        "required": True,
                    },
                    {
                        "type": 3,
                        "name": "streamer",
                        "description": "The stream queue to edit, defaults to yours",
                        "required": False,
                        "autocomplete": True,
                    },
                ],
            },
            {
                "type": 1,
                "name": "swap",
                "description": "Swap two sets in a stream queue (reorder)",
                "options": [
                    {
                        "type": 3,
                        "name": "set_1",
                        "description": "The set you want to move",
                        "required": True,
                        "autocomplete": True,
                    },
                    {
                        "type": 3,
                        "name": "set_2",
                        "description": "The set to swap with",
                        "required": True,
                        "autocomplete": True,
                    },
                    {
                        "type": 3,
                        "name": "streamer",
                        "description": "The stream queue to edit, defaults to yours",
                        "required": False,
                        "autocomplete": True,
                    },
                ],
            },
            {
                "type": 1,
                "name": "transfer",
                "description": "Transfer the ownership of a stream queue to someone else",
                "options": [
                    {
                        "type": 6,
                        "name": "member",
                        "description": "New owner of the stream queue",
                        "required": True,
                    },
                    {
                        "type": 3,
                        "name": "streamer",
                        "description": "The stream queue to edit, defaults to yours",
                        "required": False,
                        "autocomplete": True,
                    },
                ],
            },
        ],
    },
    {"type": 1, "name": "bracket", "description": "Get the link of the bracket"},
    {"type": 1, "name": "stages", "description": "Get the link of allowed stages"},
    {"type": 1, "name": "counters", "description": "Get the link of allowed counterpicks"},
    {"type": 1, "name": "ruleset", "description": "Get the tournament ruleset"},
    {"type": 1, "name": "streamlink", "description": "Get the current broadcast, if any"},
    {
        "type": 1,
        "name": "ff",
        "description": "Forfeit the current set. You will continue playing if there are other sets (loser bracket)",
        "default_permission": False,
    },
    {
        "type": 1,
        "name": "dq",
        "description": "Disqualify from the tournament and forfeit all sets",
        "default_permission": False,
    },
    {
        "type": 1,
        "name": "lag",
        "description": "Request a lag test from the tournament organisers",
        "default_permission": False,
    },
    {
        "type": 1,
        "name": "flip",
        "description": "Flip a coin",
    },
]
