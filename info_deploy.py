# This script is executed with Travis CI
# It will create all info.json files from cogs data
# Feel free to use it in your repo
# Made by retke (El Laggron)

import os
import json
import sys

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
            "https://github.com/retke/Laggrons-Dumb-Cogs/wiki\n"
            "Join the official discord server for questions or suggestions.\n"
            "https://discord.gg/WsTGeQ"
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

        os.system('git config user.name "Travis CI Auto-JSON"')
        os.system('git config user.email "travis@travis-ci.org"')

        os.system("git checkout v3")
        for file in to_add:
            os.system("git add " + file)

        os.system('git commit -m "Updated info.json files. Build #{}"'.format(build))
        os.system(
            "git remote add github https://{}@github.com/retke/Laggrons-Dumb-Cogs.git".format(token)
        )
        os.system("git push github v3")
        print("Created info.json files, successfully pushed to Github")
        sys.exit(0)
    else:
        print("Docstring are the same, nothing to change.")
        sys.exit(0)


if __name__ == "__main__":
    create_info_json(InstantCommands, "instantcmd")
    create_info_json(RoleInvite, "roleinvite")
    create_info_json(Say, "say")
    create_info_json(Default, ".")  # repo info.json
    commit(token=sys.argv[1], build=sys.argv[2], to_add=to_add)
