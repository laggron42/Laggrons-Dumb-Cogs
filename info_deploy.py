# This script is executed with Travis CI
# It will create all info.json files from cogs data
# Feel free to use it in your repo
# Made by retke (El Laggron)

import os
import json

from instantcmd import InstantCommands
from roleinvite import RoleInvite
from say import Say


def get_cog_data(instance):
    data = {
        "author": instance.__author__,
        "bot_version": instance.__info__["bot_version"],
        "description": instance.__info__["description"],
        "hidden": instance.__info__["hidden"],
        "install_msg": instance.__info__["install_msg"],
        "required_cogs": instance.__info__["required_cogs"],
        "requirements": instance.__info__["requirements"],
        "short": instance.__info__["short"],
        "tags": instance.__info__["tags"],
    }
    return data


def create_info_json(instance, file_name):
    path = "{0}/info.json".format(file_name)
    current_data = json.dumps(get_cog_data(instance))

    if not os.path.isfile(path):
        os.system("echo {} > " + path)
    file = open(path, "r")

    old_data = json.loads(file.read())
    if current_data != old_data:
        file.close()
        file = open(path, "w")
        file.write(current_data)
    file.close()


def commit():
    if os.popen("git diff").read() != "":
        print(1)
        os.system('git config user.name "Travis CI Auto-JSON"')
        print(2)
        os.system('git config user.email "travis@travis-ci.org"')
        print(3)
        os.system("git checkout v3")
        print(4)
        os.system("git add *.json")
        print(5)
        os.system('git commit -m "Updated info.json files"')
        print(6)
        os.system("git push")


if __name__ == "__main__":
    create_info_json(InstantCommands, "instantcmd")
    create_info_json(RoleInvite, "roleinvite")
    create_info_json(Say, "say")
    commit()
