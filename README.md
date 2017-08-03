# Laggron's dumb cogs

Hi I'm **El Laggron** from [Twentysix's Discord server](https://discord.gg/red) and I made this cog because I'm bored. Just that. And don't expect a lot from me, if the cog you're using works, this is mostly luck (or dark magic) because I'm a quite shit dev. 

If you have any ideas of cogs I should make, contact me in DM. 

Also I should credit **UltimatePancake** and **Sentry** who helped me a lot on cog creation (not Kowlin who just spit on me).

If you like these cogs, please consider donating at [Twentysix](https://www.patreon.com/Twentysix26) (surprising ?) because he way more deserves it than me C:

## How to install one of my cogs

Type the following command (if not responding, make sure you are the bot owner, the bot has access to your channel and the cog `downloader.py` is loaded (`[p]load downloader` if not):

`!cog repo add Laggrons-Dumb-Cogs https://github.com/retke/Laggrons-Dumb-Cogs`

Then to install a cog type this command:

`!cog install Laggrons-Dumb-Cogs <cog name>`

## Usage

Here is a short tuto on how to use my cogs. `[p]` is your prefix.

### Say

`[p]send here <message>` Send your message in the actual channel and delete the message that invoked the command

`[p]send channel <#channel_mention> <message>` Send your message in the given channel and delete the message that invoked the command

`[p]send upload <file.name> [comment (optional)]` Upload and send the give file in the local data folder, with an optional comment. Delete the message that invoked the command

`[p]send dm <user.mention> <message>` Send the exact message you gave to a user in private message (instead of whisper which add the message author)

For file upload, you need to put your files in `/data/say/` and don't forget to reload the cog (`[p]reload say`) everytime you add something. On command, don't forget to add the extention like this

`[p]send upload my_zelda_wallpaper.png` `[p]send upload random_dead_meme.gif`

And try to don't add spaces in your file's name, or you will have to type this : (file is `screenshot from random date.png`) `[p]send upload "screenshot\ from\ random\ date.png" [comment]`
