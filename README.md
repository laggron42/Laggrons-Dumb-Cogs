# Laggron's dumb cogs

Hi I'm **El Laggron** from [Twentysix's Discord server](https://discord.gg/red) and I made this cog because I'm bored. Just that. And don't expect a lot from me, if the cog you're using works, this is mostly luck (or dark magic) because I'm a quite shit dev.

If you have any ideas of cogs, any bug you meet or any question, you can join my own [Discord server](https://discord.gg/WsTGeQM)

If you like these cogs, please consider donating to help me code better quality cogs. Everything is very helpful to me and means a lot, if you're interested (yay), visit my [Patreon](https://www.patreon.com/retke)

## How to install one of my cogs

Type the following command (if not responding, make sure you are the bot owner, the bot has access to your channel and the cog `downloader.py` is loaded (`[p]load downloader` if not):

`[p]cog repo add Laggrons-Dumb-Cogs https://github.com/retke/Laggrons-Dumb-Cogs`

Then to install a cog type this command:

`[p]cog install Laggrons-Dumb-Cogs <cog name>`

## Usage

Here is a short tuto on how to use my cogs. `[p]` is your prefix.

### Say

**Permissions:**

- `Upload files` To enable the upload function

- `Manage messages` To enable auto delete

**Commands:**

`[p]send here <message>` Send your message in the actual channel.

`[p]send channel <#channel_mention> <message>` Send your message in the given channel.

`[p]send upload <file.name> [comment (optional)]` Upload and send the give file in the local data folder, with an optional comment.

`[p]send dm <user.mention> <message>` Send the exact message you gave to a user in private message (instead of whisper which add the message author)

For file upload, you need to put your files in `/data/say/upload`. Then type the following command `[p]send upload myfile.png`

You can remove `.png`, the bot should find it, except if two files has the same name! Also **don't put files with spaces in its name or it won't work**

`[p]send autodelete` Enable auto deletion of the message that invoked the command. This will only if the bot has the `Manage messages` permission and on the commands of this cog (for autodeletion of all commands, look at `[p]modset deletedelay`)

### Bettermod

**Recommanded permissions to work correctly:**

- `Manage messages` Optional, but it will delete messages that invoked some command and also manage reactions, which is easier for menu control

- `Embed links` Needed for the cog. Report, warns, delete and edit confimations are using embed.

- `Add reactions` This is needed for the cog, as you move in the menu through reactions

- `Kick members` and `Ban members` This is optional, but warns 2 and 3 will obviously don't work (also Red need an upper role than the members he need to has control on, or it won't work)

**Commands:**

`[p]report @user <reason>` This will send a message in the mod log, set before, with the reason. Anyone can use this command and the message that invoked the command will be default auto delete.

`[p]warn` This will send a warning to the specified user, with the reason. This will also be sent in the modlog channel and the message that invoked the command will be auto delete. You will be able to check user's warns later. This command work with the following subcommands:

- `[p]warn <1|simple> @user <reason>` Works as said before. The reason is required

- `[p]warn <2|kick> @user <reason>` Same as before, but it will kick the user.

- `[p]warn <3|ban> @user <reason>` Same as before², but it will ban the user.

You can also set multiple settings, some are required:

`[p]bmodset` This is the command that will allow you to set everything:

- `[p]bmodset channel <channel mention>` This will set the modlog channel.

- `[p]bmodset color <report|simple|kick|ban>` This set the color bar of the differents embed messages that can be send in the modlog.

-  `[p]bmodset thumbnail <report|simple|kick|ban>` This set the thumbnail of the differents embed messages (the small picture at the top right) that can be send in the modlog.

- `[p]bmodset mention <role>` Enable the mention of a role when a report is done. The exact name need to be provided.

You can check warns using this command:

- `[p]bcheck <case number> [@user]` This will show a menu with the selected case. If you select case 0, the total number of warning will be given. If you specify a user, it will show its warnings, but you need to be moderator.

Moderators only:

- `[p]case edit <case number> <@user> <reason>` Modify the reason of the specified case.

- `[p]case delete <case number> <@user>` Delete the specified case. This will be removed from the UI but still available in the local data.

### Role Invite

**Permissions:**

- `Create instant invite` The bot won't create any invite but this perm is needed to let the bot access the current invites.

**Commands:**

`[p]roleset` This is the command that will set everything:

- `[p]roleset list` List all of the role-invite links on this server

- `[p]roleset add <invite> <role>` Add a role-invite link to the server. The invite can be `http://discord.gg/xyz` or just `xyz`.

- `[p]roleset remove <invite>` Remove a role-invite link to the server.

Roles will be added when a user join the server. If the user joined with an invite not know by the bot, he will keep the `@everyone` role.
