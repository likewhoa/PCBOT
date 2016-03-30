import logging
import os
import random
import shlex
import re
import importlib
from datetime import datetime
from getpass import getpass
from sys import exit

import discord
import asyncio

from pcbot.config import Config

logging_level = logging.INFO  # Change this is you want more / less log info
logging.basicConfig(level=logging_level, format="%(levelname)s [%(module)s] %(asctime)s: %(message)s")
plugins = {}


def load_plugin(plugin_name):
    if not plugin_name.startswith("__") or not plugin_name.endswith("__"):
        try:
            plugin = importlib.import_module("plugins.{}".format(plugin_name))
        except ImportError:
            return False

        plugins[plugin_name] = plugin
        logging.log(logging.DEBUG, "LOADED PLUGIN " + plugin_name)
        return True

    return False


def reload_plugin(plugin_name):
    if plugins.get(plugin_name):
        plugins[plugin_name] = importlib.reload(plugins[plugin_name])
        logging.log(logging.DEBUG, "RELOADED PLUGIN " + plugin_name)


def unload_plugin(plugin_name):
    if plugins.get(plugin_name):
        plugins.pop(plugin_name)
        logging.log(logging.DEBUG, "UNLOADED PLUGIN " + plugin_name)


def load_plugins():
    for plugin in os.listdir("plugins/"):
        plugin_name = os.path.splitext(plugin)[0]
        load_plugin(plugin_name)


class Bot(discord.Client):
    def __init__(self):
        super().__init__()
        self.message_count = Config("count", data={})
        self.owner = Config("owner")
        self.lambdas = Config("lambdas", data={})
        self.lambda_blacklist = []

        load_plugins()
        asyncio.async(self.autosave())

    # Return true if user/member is the assigned bot owner
    def is_owner(self, user):
        if type(user) is not str:
            user = user.id

        if user == self.owner.data:
            return True

        return False

    # Save a plugins files if it has a save function
    def save_plugin(self, plugin):
        if plugins.get(plugin):
            try:
                yield from plugins[plugin].save(self)
            except AttributeError:
                pass

    # Looks for any save function in a plugin and saves. Set up for saving on !stop and periodic saving every 30 mins
    def save_plugins(self):
        for name, _ in plugins.items():
            yield from self.save_plugin(name)

    @asyncio.coroutine
    def autosave(self):
        while True:
            # Sleep for 30 minutes before saving (no reason to save on startup)
            yield from asyncio.sleep(60 * 30)
            yield from self.save_plugins()
            logging.log(logging.INFO, "Plugins saved")

    @staticmethod
    def find_member(server: discord.Server, name, steps=3, mention=True):
        member = None

        # Return a member from mention
        found_mention = re.search(r"<@([0-9]+)>", name)
        if found_mention and mention:
            member = server.get_member(found_mention.group(1))

        if not member:
            # Steps to check, higher values equal more fuzzy checks
            checks = [lambda m: m.name.lower() == name.lower(),
                      lambda m: m.name.lower().startswith(name.lower()),
                      lambda m: name.lower() in m.name.lower()]

            for i in range(steps if steps <= len(checks) else len(checks)):
                member = discord.utils.find(checks[i], server.members)

                if member:
                    break

        # Return the found member or None
        return member

    @staticmethod
    def find_channel(server: discord.Server, name, steps=3, mention=True):
        channel = None

        # Return a member from mention
        found_mention = re.search(r"<#([0-9]+)>", name)
        if found_mention and mention:
            channel = server.get_channel(found_mention.group(1))

        if not channel:
            # Steps to check, higher values equal more fuzzy checks
            checks = [lambda c: c.name.lower() == name.lower(),
                      lambda c: c.name.lower().startswith(name.lower()),
                      lambda c: name.lower() in c.name.lower()]

            for i in range(steps if steps <= len(checks) else len(checks)):
                channel = discord.utils.find(checks[i], server.channels)

                if channel:
                    break

        # Return the found channel or None
        return channel

    @asyncio.coroutine
    def on_ready(self):
        logging.log(logging.INFO, "\nLogged in as\n"
                                  "{0.user.name}\n"
                                  "{0.user.id}\n".format(self) +
                                  "-" * len(self.user.id))

        # Call any on_ready function in plugins
        for name, plugin in plugins.items():
            try:
                asyncio.async(plugin.on_ready(self))
            except AttributeError:
                pass

    @asyncio.coroutine
    def on_message(self, message: discord.Message):
        if message.author == self.user:
            return

        if not message.content:
            return

        # Log every command to console (logs anything starting with !)
        if message.content.startswith("!"):
            # logging.log(logging.INFO, "{0}@{1.author.name}: {1.content}".format(
            #     datetime.now().strftime("%d.%m.%y %H:%M:%S"),
            #     message
            # ))
            logging.log(logging.INFO, message.content)

        # Split content into arguments by space (surround with quotes for spaces)
        try:
            args = shlex.split(message.content)
        except ValueError:
            args = message.content.split()

        # Bot help command. Loads info from plugins
        if args[0] == "!help":
            # Command specific help
            if len(args) > 1:
                plugin_name = args[1].lower()
                for name, plugin in plugins.items():
                    if plugin.commands:
                        cmd = plugin.commands.get(plugin_name)
                        if cmd:
                            m = "**Usage**: ```{}```\n" \
                                "**Description**: {}".format(cmd.get("usage"), cmd.get("desc"))
                            yield from self.send_message(message.channel, m)
                            break

            # List all commands
            else:
                m = "**Commands:**```"
                for name, plugin in plugins.items():
                    if plugin.commands:
                        m += "\n" + "\n".join(plugin.commands.keys())

                m += "```\nUse `!help <command>` for command specific help."
                yield from self.send_message(message.channel, m)

        # Below are all owner specific commands
        if message.channel.is_private and message.content == "!setowner":
            if self.owner.data:
                yield from self.send_message(message.channel, "An owner is already set.")
                return

            owner_code = str(random.randint(100, 999))
            print("Owner code for assignment: {}".format(owner_code))
            yield from self.send_message(message.channel,
                                         "A code has been printed in the console for you to repeat within 15 seconds.")
            user_code = yield from self.wait_for_message(timeout=15, channel=message.channel, content=owner_code)
            if user_code:
                yield from self.send_message(message.channel, "You have been assigned bot owner.")
                self.owner.data = message.author.id
                self.owner.save()
            else:
                yield from self.send_message(message.channel, "You failed to send the desired code.")

        if self.is_owner(message.author):
            # Stops the bot
            if message.content == "!stop":
                yield from self.save_plugins()
                bot.logout()
                exit("Stopped by owner.")

            # Sets the bots game
            elif args[0] == "!game":
                if len(args) > 1:
                    game = discord.Game(name=args[1])
                    logging.log(logging.DEBUG, "Setting bot game to {}".format(args[1]))
                    yield from self.change_status(game)
                else:
                    yield from self.send_message(message.channel, "Usage: `!game <game>`")

            # Runs a piece of code
            elif args[0] == "!do":
                if len(args) > 1:
                    def say(msg, c=message.channel):
                        asyncio.async(self.send_message(c, msg))

                    script = message.content[len("!do "):]
                    try:
                        exec(script, locals(), globals())
                    except Exception as e:
                        say("```" + str(e) + "```")

            # Evaluates a piece of code and prints the result
            elif args[0] == "!eval":
                if len(args) > 1:
                    script = message.content[len("!eval "):].replace("`", "")
                    result = eval(script)
                    yield from self.send_message(message.channel, "**Result:** \n```{}\n```".format(result))

            elif args[0] == "!lambda":
                m = ""

                if len(args) > 2:
                    name = args[2].lower()
                    m = "Command `{}` ".format(name)

                    if args[1] == "add" and len(args) > 3:
                        # Get the clean representation of the command
                        cmd = message.content[len(" ".join(args[:3]))+1:]

                        if name not in self.lambdas.data:
                            self.lambdas.data[name] = cmd
                            self.lambdas.save()
                            m += "set."
                        else:
                            m += "already exists."
                    elif args[1] == "remove":
                        if name in self.lambdas.data:
                            self.lambdas.data.pop(name)
                            self.lambdas.save()
                            m += "removed."
                        else:
                            m += "does not exist."
                    elif args[1] == "disable":
                        if name not in self.lambda_blacklist:
                            self.lambda_blacklist.append(name)
                            self.lambdas.save()
                            m += "disabled."
                        else:
                            if name in self.lambdas.data:
                                m += "is already disabled."
                            else:
                                m += "does not exist."
                    elif args[1] == "enable":
                        if name in self.lambda_blacklist:
                            self.lambda_blacklist.remove(name)
                            self.lambdas.save()
                            m += "enabled."
                        else:
                            if name in self.lambdas.data:
                                m += "is already enabled."
                            else:
                                m += "does not exist."
                    elif args[1] == "source":
                        if name in self.lambdas.data:
                            m = "Source for {}: \n{}".format(name, self.lambdas.data[name])
                        else:
                            m += "does not exist."

                if m:
                    yield from self.send_message(message.channel, m)

            # Plugin specific commands
            elif args[0] == "!plugin":
                if len(args) > 1:
                    if args[1] == "reload":
                        if len(args) > 2:
                            if plugins.get(args[2]):
                                yield from self.save_plugin(args[2])
                                reload_plugin(args[2])
                                yield from self.send_message(message.channel, "Reloaded plugin `{}`.".format(args[2]))
                            else:
                                yield from self.send_message(message.channel,
                                                             "`{}` is not a plugin. Use `!plugins`.".format(args[2]))
                        else:
                            yield from self.save_plugins()
                            for plugin in list(plugins.keys()):
                                reload_plugin(plugin)
                            yield from self.send_message(message.channel, "All plugins reloaded.")
                    elif args[1] == "load":
                        if len(args) > 2:
                            if not plugins.get(args[2].lower()):
                                loaded = load_plugin(args[2].lower())
                                if loaded:
                                    yield from self.send_message(message.channel, "Plugin `{}` loaded.".format(args[2]))
                                else:
                                    yield from self.send_message(message.channel,
                                                                 "Plugin `{}` could not be loaded.".format(args[2]))
                            else:
                                yield from self.send_message(message.channel,
                                                             "Plugin `{}` is already loaded.".format(args[2]))
                    elif args[1] == "unload":
                        if len(args) > 2:
                            if plugins[args[2].lower()]:
                                yield from self.save_plugin(args[2])
                                unload_plugin(args[2].lower())
                                yield from self.send_message(message.channel, "Plugin `{}` unloaded.".format(args[2]))
                            else:
                                yield from self.send_message(message.channel,
                                                             "`{}` is not a plugin. Use `!plugins`.".format(args[2]))
                    else:
                        yield from self.send_message(message.channel, "`{}` is not a valid argument.".format(args[1]))
                else:
                    yield from self.send_message(message.channel,
                                                 "**Plugins:** ```\n"
                                                 "{}```".format(",\n".join(plugins.keys())))

            # Originally just a test command
            elif message.content == "!count":
                if not self.message_count.data.get(message.channel.id):
                    self.message_count.data[message.channel.id] = 0

                self.message_count.data[message.channel.id] += 1
                yield from self.send_message(message.channel, "I have counted `{}` times in this channel.".format(
                    self.message_count.data[message.channel.id]
                ))
                self.message_count.save()

        # Run plugins on_message
        for name, plugin in plugins.items():
            if args[0][1:] in plugin.commands or getattr(plugin, "always_run", False):
                yield from plugin.on_message(self, message, args)

        if args[0] in self.lambdas.data and args[0] not in self.lambda_blacklist:
            def say(msg, c=message.channel):
                asyncio.async(self.send_message(c, msg))

            def arg(i, default=0):
                if len(args) > i:
                    return args[i]
                else:
                    return default

            exec(self.lambdas.data[args[0]], locals(), globals())


bot = Bot()

if __name__ == "__main__":
    email = input("Email: ")
    password = getpass()
    bot.run(email, password)
