""" Handle any bot specific configs.

This module includes the command syntax, github repo path,
setting the bot's version and a class for creating configs.
"""

import json
from os.path import exists
from os import mkdir


github_repo = "PcBoy111/PCBOT/"
command_prefix = "!"
help_arg = ("?", "help")
version = ""
name = "PCBOT"  # Placebo name, should be changed on_ready
owner_error = False  # Whether the bot owner should receive error messages in chat


def set_version(ver: str):
    """ Set the version of the API. This function should really only
    be used in bot.py. """
    global version
    version = ver
    return version


class Config:
    config_path = "config/"

    def __init__(self, filename: str, data=None, load: bool=True, pretty=False):
        """ Setup the config file if it does not exist.

        :param filename: usually a string representing the module name.
        :param data: default data setup, usually an empty/defaulted dictionary or list.
        :param load: should the config file load when initialized? Only loads when a config already exists. """
        self.filepath = "{}{}.json".format(self.config_path, filename)
        self.pretty = pretty

        if not exists(self.config_path):
            mkdir(self.config_path)

        loaded_data = self.load() if load else None

        if data is not None and not loaded_data:
            self.data = data
        elif loaded_data:
            # If the default data is a dict, compare and add missing keys
            updated = False
            if type(loaded_data) is dict:
                for k, v in data.items():
                    if k not in loaded_data:
                        loaded_data[k] = v
                        updated = True

            self.data = loaded_data

            if updated:
                self.save()
        else:
            self.data = None

        if not self.data == loaded_data:
            self.save()

    def save(self):
        """ Write the current config to file. """
        with open(self.filepath, "w") as f:
            if self.pretty:
                json.dump(self.data, f, sort_keys=True, indent=4)
            else:
                json.dump(self.data, f)

    def load(self):
        """ Load the config from file if it exists.

        :return: config parsed from json or None"""
        if exists(self.filepath):
            with open(self.filepath, "r") as f:
                try:
                    return json.load(f)
                except ValueError:
                    pass

        return None
