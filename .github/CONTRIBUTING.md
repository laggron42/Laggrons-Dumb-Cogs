# Laggron's Dumb Cogs contribution guide

Hello and welcome there, if you're here, that means that you want to contribute to the repository, which is great! Thank you for this.

Before contributing, make sure you joined the [Discord server](https://discord.gg/WsTGeQM) so you can directly discuss to me (El Laggron) about what you're planning to do.

## How to contribute

You can contribute to the repo by many ways : using, creating, fixing, testing, reporting, writing or even translating (soon).

Before reading below, please make sure you created your own [Github account](https://github.com/join). This is necessary if you want to go further in contributing.

### I want to help in the development but I don't know coding

If you don't know Python and still want to contribute, there are plenty of things you can do! First you can install the repository on your Red discord bot, use the available cogs and report every problem you can find (errors, bugs, weird things, grammar or typo errors, suggestions). When I code, I usually don't have a view on what I'm doing, that is why those who use my cogs and report their view are really useful for me!

If you meet any of these problems, just [create an issue](https://github.com/retke/Laggrons-Dumb-Cogs/issues/new/choose) with as much details as possible. We will fix the issue as quick as possible.

### I want to translate your cogs in my language

Laggron's Dumb Cogs is now using Crowdin for translations! You don't need to install anything, just create an account and start translating strings with a fancy online editor: **https://crowdin.com/project/laggrons-dumb-cogs/**

You can also translate locally by downloading [PoEdit](https://poedit.net) and creating translation files from the `messages.pot` file you can find in the `locales` folder of every cog., you can then upload the files to Crowdin.

### I want to contribute and I know coding

If you know Python and Discord.py, that's great, you will be able to understand how the bot works and be able to add new features or correct bugs by yourself! Pull requests are welcome on this repository, however, there are some guidelines you need to respect. Please read the rules below.

## Rules for submitting a Pull request

If you don't know how to make a pull request, [read this](https://help.github.com/articles/creating-a-pull-request/).

- Make sure what you made is accessible for both **Python 3.5** and **Python 3.6**, and every OS. Travis CI will compile your code on commit to make sure there's no error.
- Your code musn't contain malicious code.
- Your changes must bring something useful for everyone, and not some specific things that will only benefit for yourself.
- What you added needs to be accessible and user-friendly. Settings should be accessibe through Discord and **code editing should never be required**.
- The code should be clear and contain comments so everyone can understand what you're doing.
- Follow the logic of the current code if you are writing new functions.
- Test your code as much as possible. You can submit a non-tested PR (considering you will add commits in the future), but don't say something is ready while it isn't.

If you don't respect these rules, you may be banned from the repository (any activity will become impossible).