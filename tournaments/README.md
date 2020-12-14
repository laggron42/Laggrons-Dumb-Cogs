# Tournaments

The tournaments cog provides advanced tools for organizing your [Challonge](https://challonge.com/) tournaments on your Discord server!

From the beginning to the end of your tournament, members of your server will be able to join and play in your tournaments without even creating a Challonge account.

The cog supports the registration and check-in of the tournament, including seeding with Braacket.

Then, once the game starts, just sit down and watch ~~the magic~~ the bot manage everything:
- For each match, a channel will be created with the two players of this match.
- They have their own place for discussing about the tournament, checking the stage list, banning stages/characters...
- The bot checks activity in the channels. If one player doesn't talk within the first minutes, he will be disqualified.
- Once the players have done their match, they can set their score with a command.
- Players can also forfeit a match, or disqualify themselves.
- As the tournament goes on, outdated channels will be deleted, and new ones will be created for the upcoming matches, the bot is constantly checking the bracket.

The T.O.s, short for Tournament Organizers, also have their set of tools:
- Being able to see all the channels and directly talk in one in case of a problem makes their job way easier
- If a match takes too long, they will be warned in their channel to prevent slowing down the bracket
- They can directly modify the bracket on Challonge (setting scores, resetting a match), and the bot will handle the changes, warning players if their match is cancelled or has to be replayed. A warning is also sent in the T.O. channel.
- Players can call a T.O. for a lag test for example, and a message will be sent in the defined T.O. channel

Add to all of this tools for streamers too!
- Streamers can add themselves to the tournament (not as a player) and comment some matches
- They will choose the matches they want to cast, and also provide informations to players (for example, the room code and ID for smash bros)
- If a match is launched but attached to a streamer, it will be paused until it is their turn. They will then receive the informations set above.
- The streamer has access to the channels, so that he can also communicate with the players.

This was tested with tournaments up to 256 players, and I can personnaly confirm this makes the organizers' job way easier.

There is a detailed documentation, covering all commands in details, please read this if you want to know how commands works in details: https://laggron.red/tournaments.html

## Installation and quick start

`[p]` is your prefix.

1.  Install the repo if it's not already done.
    ```
    [p]repo add Laggrons-Dumb-Cogs https://github.com/retke/Laggrons-Dumb-Cogs
    ```

2.  Install and load Tournaments
    ```py
    [p]cog install Laggrons-Dumb-Cogs tournaments
    # Type "I agree" if requested
    # wait for your bot to install the cog
    [p]load tournaments
    ```
    Tournaments is now installed!

3.  Setup your credentials for Challonge
    ```py
    [p]challongeset username
    # the command below will prompt for the token in DM
    [p]challongeset api
    ```

4.  On your server, configure your channels and roles
    ```
    [p]help tset channels
    [p]help tset roles
    ```

5.  Configure one of the games you plan to use
    ```
    [p]tset games add <full game name>
    ```
    The next commands to use will be directly shown. You can also type `[p]help tset games`.

6.  Configure other various settings:
    
    - Start and end time for the registration and check-in with `[p]tset register` and `[p]tset checkin`.
    - Delay until someone is considered AFK and disqualified with `[p]tset delay`.
    - Define when matchs will move from BO3 to BO5 with `[p]tset startbo5`.
    - Check everything with `[p]tset settings`.

All done! You can now setup a tournament with `[p]setup` and your Challonge tournament.

## Discord server

If you need support, have bugs to report or suggestions to bring, please join my Discord server and tell me, `El Laggron#0260`, about it!

[![Discord server](https://discordapp.com/api/guilds/363008468602454017/embed.png?style=banner3)](https://discord.gg/AVzjfpR)

## Future compatibility

Currently, this only supports [Challonge](https://challonge.com/) tournaments, but the cog is built in a way that allows adding more providers easily! I'm planning to add support for [smash.gg](https://smash.gg/) tournaments soon...

## [Laggron's Dumb Cogs](https://github.com/retke/Laggrons-Dumb-Cogs)

![Artwork](https://github.com/retke/Laggrons-Dumb-Cogs/blob/master/.github/RESSOURCES/BANNERS/Base_banner.png)

This cog is part of the Laggron's Dumb Cogs repository, where utility cogs for managing your server are made!
If you like this cog, you should check the other cogs from [the repository](https://github.com/retke/Laggrons-Dumb-Cogs)!

You can also support me on [Patreon](https://patreon.com/retke) or [Github Sponsors](https://github.com/sponsors/retke/card) and get exclusive rewards!

## Credits

This cog is based on the [ATOS Discord bot](https://github.com/Wonderfall/ATOS). A huge thanks to [Wonderfall](https://github.com/Wonderfall) for allowing me to convert his bot to a Red cog! The entire goal of this cog and the interface are based on his work.

Thanks to [Xyleff](https://github.com/Xyleff2049) too who also helped me a lot for creating this cog!

## Contribute

If you're reading this from Github and want to contribute or just understand the source code, I'm gonna stop you right there. Indeed, the cog is a bit complex so let me explain a bit how each file work before source diving.

To prevent having files too long, I splitted categories of commands across different files. The most important part of the code, the core of all this, is inside the `objects` folder. Indeed, you will find there 4 classes: `Tournament`, `Participant`, `Match` and `Streamer`, and most of the commands simply calls those objects' methods. More details below.

- `__init__.py` The first file invoked when loading the cog. Nothing really useful here, only checks for libs and restore previous tournaments.
- `abc.py` Just stuff for the inheritance of some classes.
- `games.py` The commands that are used during a tournament are located here, such as `[p]start`, `[p]resetbracket`, `[p]win`, `[p]dq`... This mostly interacts with the objects defined in the `objects` folder, few code is actually in there.
- `registration.py` All the commands related to registration and check-in, such as `[p]in`, `[p]out`, `[p]add`, `[p]rm`... This mostly interacts with the objects defined in the `objects` folder.
- `settings.py` All the settings commands: `[p]tset`, `[p]challongeset` and `[p]setup`. Boring file, super long because of the huge amount of settings.
- `streams.py` Streamer related commands (`[p]stream`). This mostly interacts with the objects defined in the `objects` folder.
- `tournaments.py` The base class of the cog. Not that interesting, as it inherits from the classes in `games.py`, `registration.py`, `settings.py` and `streams.py`. You will find here Config definition, the code for restoring tournaments from saved data, and some basic stuff for the cog.
- `utils.py` Some utility functions, like one for calling and retrying API calls, or a decorator for specifying when a command can be used.

Now the interesting part, the `objects` folder:

- `__init__.py` Nothing lol
- `base.py` The core of your tournaments. There are 4 classes :
  - `Tournament` The first object created, it contains all the config you set, plus infos from the API. Then there are a lot of various methods, like the loop task ran during a tournament, code for launching the sets, sending messages, checking for timeout, adding a player... Then there are abstract methods, they represent API calls but just do nothing at this point, but we'll define them in the next file. There are also 3 lists for each of the objects described below. If you want to delete an object, remove it from those lists.
  - `Participant` Represents a participant in the tournament. It inherits from `discord.Member` and adds some attributes and methods useful for our tournament, such as its player ID on the bracket, his current match, and see if he spoke (AFK check). There are once again abstract methods representing API calls, like DQing.
  - `Match` Represents a match. It is associated to two participants, and contains the stuff for a match (setting scores, announcing changes, checking for DQ)... It is usually associated with a `discord.TextChannel` (if creating the channel failed, we move the stuff in DM). Still more abstract methods for API calls.
  - `Streamer` Very small object that represents a streamer, and doesn't have API calls (we keep that for ourselves for now). It contains a list of the sets he will comment, and additional info.
- `challonge.py` This file has 3 classes: `ChallongeTournament`, `ChallongeParticipant` and `ChallongeMatch`. You guessed it, they all inherit from the objects in `base.py` and will define those abstract methods with the actual API calls to Challonge. Stuff in here is specific to Challonge, it treats raw data from the Challonge API and adapts it to the structure of the base objects.

You may have guessed it, using this structure, with base classes that are inherited, allows an easy integration for more services. If you have another great website for tournaments and brackets, create a new file, adapt the API data to the classes, and then there will be very few code to change, everything will work as intended!

With that said, source diving should be easier.
