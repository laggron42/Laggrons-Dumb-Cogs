# This script is executed with Travis CI
# It will create all info.json files from cogs data
# Feel free to use it in your repo
# Made by retke (El Laggron)

import os
import json
import sys

from warnsystem import WarnSystem
from instantcmd import InstantCommands
from roleinvite import RoleInvite
from say import Say


class Default:
    """
    This contains the documentation of the repository
    """

    __author__ = "El Laggron"
    __info__ = {
        "description": (
            "A buch of utility and quality cogs "
            "that brings unique features for your server. "
            "Made by Laggron."
        ),
        "install_msg": (
            "Thanks for installing the repository! Please check the wiki "
            "for all informations about the cogs.\n"
            "https://laggrons-dumb-cogs.readthedocs.io/\n"
            "Join the official discord server for questions or suggestions.\n"
            "https://discord.gg/AVzjfpR\n\n"
            "**Important**\n"
            "Some cogs use Sentry error reporting, like core Red. If Sentry is "
            "enabled on Red, it will also be enabled with these cogs."
        ),
        "short": "Utility cogs for your server.",
    }


to_add = []


def get_cog_data(instance):

    data = {"author": instance.__author__}
    data.update(instance.__info__)
    return data


def create_info_json(instance, file_name):
    path = "{0}/info.json".format(file_name)
    current_data = json.dumps(get_cog_data(instance), indent=4, sort_keys=True)

    if not os.path.isfile(path):
        os.system("echo {} > " + path)
    file = open(path, "r")

    old_data = json.loads(file.read())
    if current_data != old_data:
        file.close()
        file = open(path, "w")
        file.write(current_data)
        to_add.append(path)
    file.close()


def commit(token, build, to_add):
    if os.popen("git diff").read() != "":
        exits = []  # collect the exit int of the process

        exits.append(os.system('git config user.name "Travis CI Auto-JSON"'))
        exits.append(os.system('git config user.email "travis@travis-ci.org"'))

        exits.append(os.system("git checkout v3"))
        for file in to_add:
            exits.append(os.system("git add " + file))

        exits.append(os.system('git commit -m "Updated info.json files. Build #{}"'.format(build)))
        exits.append(
            os.system(
                "git remote add github https://{}@github.com/retke/Laggrons-Dumb-Cogs.git".format(
                    token
                )
            )
        )
        exits.append(os.system("git push github v3"))

        if 1 in exits:
            # something existed with error code 1
            print("Something went wrong during the process.")
            sys.exit(1)
        print("Created info.json files, successfully pushed to Github")
        sys.exit(0)
    else:
        print("Docstring are the same, nothing to change.")
        sys.exit(0)


if __name__ == "__main__":
    if "GH_TOKEN" not in os.environ:
        print("GitHub token not found. This environement may be a pull request. Closing...")
        sys.exit(0)
    create_info_json(WarnSystem, "warnsystem")
    create_info_json(InstantCommands, "instantcmd")
    create_info_json(RoleInvite, "roleinvite")
    create_info_json(Say, "say")
    create_info_json(Default, ".")  # repo info.json
    commit(token=sys.argv[1], build=sys.argv[2], to_add=to_add)
