""" Plugin for built-in commands.

This script works just like any of the plugins in plugins/
"""

import importlib
import inspect
import logging
import random
from datetime import datetime, timedelta

import discord
import asyncio

from pcbot import utils, Config, Annotate, config
import plugins
client = plugins.client  # type: discord.Client


sub = asyncio.subprocess
lambdas = Config("lambdas", data={})
lambda_config = Config("lambda-config", data=dict(imports=[], blacklist=[]))

code_globals = {}


@plugins.command(name="help", aliases="commands")
async def help_(message: discord.Message, command: str.lower=None, *args):
    """ Display commands or their usage and description. """
    # Display the specific command
    if command:
        if command.startswith(config.command_prefix):
            command = command[len(config.command_prefix):]

        cmd = plugins.get_command(command)
        if not cmd:
            return

        # Get the specific command with arguments and send the help
        cmd = plugins.get_sub_command(cmd, *args)
        await client.say(message, utils.format_help(cmd))

    # Display every command
    else:
        commands = []

        for plugin in plugins.all_values():
            if getattr(plugin, "__commands", False):  # Massive pile of shit that works (so sorry)
                commands.extend(
                    cmd.name_prefix.split()[0] for cmd in plugin.__commands
                    if not cmd.hidden and
                    (not getattr(getattr(cmd, "function"), "owner", False) or
                     utils.is_owner(message.author))
                )

        commands = ", ".join(sorted(commands))

        m = "**Commands**: ```{0}```Use `{1}help <command>`, `{1}<command> {2}` or " \
            "`{1}<command> {3}` for command specific help.".format(
            commands, config.command_prefix, *config.help_arg)
        await client.say(message, m)


@plugins.command(hidden=True)
async def setowner(message: discord.Message):
    """ Set the bot owner. Only works in private messages. """
    if not message.channel.is_private:
        return

    assert not utils.owner_cfg.data, "An owner is already set."

    owner_code = str(random.randint(100, 999))
    logging.critical("Owner code for assignment: {}".format(owner_code))

    await client.say(message,
                     "A code has been printed in the console for you to repeat within 60 seconds.")
    user_code = await client.wait_for_message(timeout=60, channel=message.channel, content=owner_code)

    assert user_code, "You failed to send the desired code."

    if user_code:
        await client.say(message, "You have been assigned bot owner.")
        utils.owner_cfg.data = message.author.id
        utils.owner_cfg.save()


@plugins.command()
@utils.owner
async def stop(message: discord.Message):
    """ Stops the bot. """
    await client.say(message, "\N{COLLISION SYMBOL}\N{PISTOL}")
    await plugins.save_plugins()
    await client.logout()


@plugins.command()
@utils.owner
async def update(message: discord.Message):
    """ Update the bot by running `git pull`. """
    await client.say(message, "```diff\n{}```".format(await utils.subprocess("git", "pull")))


@plugins.command()
@utils.owner
async def game(message: discord.Message, name: Annotate.Content=None):
    """ Stop playing or set game to `name`. """
    await client.change_presence(game=discord.Game(name=name, type=0))
    await client.say(message, "**Set the game to** `{}`.".format(name) if name else "**No longer playing.**")


@game.command()
@utils.owner
async def stream(message: discord.Message, url: str, title: Annotate.Content):
    """ Start streaming a game. """
    await client.change_status(game=discord.Game(name=title, url=url, type=1))
    await client.say(message, "Started streaming **{}**.".format(title))


@plugins.command(name="as")
@utils.owner
async def do_as(message: discord.Message, member: Annotate.Member, command: Annotate.Content):
    """ Execute a command as the specified member. """
    message.author = member
    message.content = command
    await client.on_message(message)


async def send_result(channel: discord.Channel, result, time_elapsed: timedelta):
    """ Sends eval results. """
    if type(result) is discord.Embed:
        await client.send_message(channel, embed=result)
    else:
        embed = discord.Embed(color=channel.server.me.color, description="```py\n{}```".format(result))
        embed.set_footer(text="Time elapsed: {:.3f}ms".format(time_elapsed.total_seconds() * 1000))
        await client.send_message(channel, embed=embed)


@plugins.command()
@utils.owner
async def do(message: discord.Message, python_code: Annotate.Code):
    """ Execute python code. """
    code_globals.update(dict(message=message, client=client,
                             author=message.author, server=message.server, channel=message.channel))

    # Create an async function so that we can await it using the result of eval
    python_code = "async def do_session():\n    " + "\n    ".join(line for line in python_code.split("\n"))
    try:
        exec(python_code, code_globals)
    except SyntaxError as e:
        await client.say(message, "```" + utils.format_syntax_error(e) + "```")
        return

    before = datetime.now()
    try:
        result = await eval("do_session()", code_globals)
    except Exception as e:
        await client.say(message, "```" + utils.format_exception(e) + "```")
    else:
        if result:
            await send_result(message.channel, result, datetime.now() - before)


@plugins.command(name="eval")
@utils.owner
async def eval_(message: discord.Message, python_code: Annotate.Code):
    """ Evaluate a python expression. Can be any python code on one
    line that returns something. Coroutine generators will by awaited. """
    code_globals.update(dict(message=message, client=client,
                             author=message.author, server=message.server, channel=message.channel))

    before = datetime.now()
    try:
        result = eval(python_code, code_globals)
        if inspect.isawaitable(result):
            result = await result
    except SyntaxError as e:
        result = utils.format_syntax_error(e)
    except Exception as e:
        result = utils.format_exception(e)

    await send_result(message.channel, result, datetime.now() - before)


@plugins.command(name="plugin", hidden=True, aliases="pl")
async def plugin_(message: discord.Message):
    """ Manage plugins.
        **Owner command unless no argument is specified.** """
    await client.say(message, "**Plugins:** ```{}```".format(", ".join(plugins.all_keys())))


@plugin_.command(aliases="r", pos_check=False)
@utils.owner
async def reload(message: discord.Message, *names: str.lower):
    """ Reloads all plugins or the specified plugin. """
    if names:
        reloaded = []
        for name in names:
            if not plugins.get_plugin(name):
                await client.say(message, "`{}` is not a plugin.".format(name))
                continue

            # The plugin entered is valid so we reload it
            await plugins.save_plugin(name)
            plugins.reload_plugin(name)
            reloaded.append(name)

        if reloaded:
            await client.say(message, "Reloaded plugin{} `{}`.".format(
                "s" if len(reloaded) > 1 else "", ", ".join(reloaded)))
    else:
        # Reload all plugins
        await plugins.save_plugins()

        for plugin_name in plugins.all_keys():
            plugins.reload_plugin(plugin_name)

        await client.say(message, "All plugins reloaded.")


@plugin_.command(error="You need to specify the name of the plugin to load.")
@utils.owner
async def load(message: discord.Message, name: str.lower):
    """ Loads a plugin. """
    assert not plugins.get_plugin(name), "Plugin `{}` is already loaded.".format(name)

    # The plugin isn't loaded so we'll try to load it
    assert plugins.load_plugin(name), "Plugin `{}` could not be loaded.".format(name)

    # The plugin was loaded successfully
    await client.say(message, "Plugin `{}` loaded.".format(name))


@plugin_.command(error="You need to specify the name of the plugin to unload.")
@utils.owner
async def unload(message: discord.Message, name: str.lower):
    """ Unloads a plugin. """
    assert plugins.get_plugin(name), "`{}` is not a loaded plugin.".format(name)

    # The plugin is loaded so we unload it
    await plugins.save_plugin(name)
    plugins.unload_plugin(name)
    await client.say(message, "Plugin `{}` unloaded.".format(name))


@plugins.command(name="lambda", hidden=True)
async def lambda_(message: discord.Message):
    """ Create commands. See `{pre}help do` for information on how the code works.

        **In addition**, there's the `arg(i, default=0)` function for getting arguments in positions,
        where the default argument is what to return when the argument does not exist.
        **Owner command unless no argument is specified.**"""
    await client.say(message,
                     "**Lambdas:** ```\n" "{}```".format(", ".join(sorted(lambdas.data.keys()))))


@lambda_.command(aliases="a")
@utils.owner
async def add(message: discord.Message, trigger: str, python_code: Annotate.Code):
    """ Add a command that runs the specified python code. """
    lambdas.data[trigger] = python_code
    lambdas.save()
    await client.say(message, "Command `{}` set.".format(trigger))


@lambda_.command(aliases="r")
@utils.owner
async def remove(message: discord.Message, trigger: str):
    """ Remove a command. """
    assert trigger in lambdas.data, "Command `{}` does not exist.".format(trigger)

    # The command specified exists and we remove it
    del lambdas.data[trigger]
    lambdas.save()
    await client.say(message, "Command `{}` removed.".format(trigger))


@lambda_.command()
@utils.owner
async def enable(message: discord.Message, trigger: str):
    """ Enable a command. """
    # If the specified trigger is in the blacklist, we remove it
    if trigger in lambda_config.data["blacklist"]:
        lambda_config.data["blacklist"].remove(trigger)
        lambda_config.save()
        await client.say(message, "Command `{}` enabled.".format(trigger))
    else:
        assert trigger in lambdas.data, "Command `{}` does not exist.".format(trigger)

        # The command exists so surely it must be disabled
        await client.say(message, "Command `{}` is already enabled.".format(trigger))


@lambda_.command()
@utils.owner
async def disable(message: discord.Message, trigger: str):
    """ Disable a command. """
    # If the specified trigger is not in the blacklist, we add it
    if trigger not in lambda_config.data["blacklist"]:
        lambda_config.data["blacklist"].append(trigger)
        lambda_config.save()
        await client.say(message, "Command `{}` disabled.".format(trigger))
    else:
        assert trigger in lambdas.data, "Command `{}` does not exist.".format(trigger)

        # The command exists so surely it must be disabled
        await client.say(message, "Command `{}` is already disabled.".format(trigger))


def import_module(module: str, attr: str=None):
    """ Remotely import a module or attribute from module into code_globals. """
    # The name of the module in globals
    # If attr starts with :, it defines a new name for the module as whatever follows the colon
    # When nothing follows this colon, the name is set to the last subcommand in the given module
    name = attr or module
    if attr and attr.startswith(":"):
        name = attr[1:] or module.split(".")[-1].replace(" ", "")

    try:
        imported = importlib.import_module(module)
    except ImportError:
        e = "Unable to import module {}.".format(module)
        logging.error(e)
        raise ImportError(e)
    else:
        if attr and not attr.startswith(":"):
            if hasattr(imported, attr):
                code_globals[name] = getattr(imported, attr)
            else:
                e = "Module {} has no attribute {}".format(module, attr)
                logging.error(e)
                raise KeyError(e)
        else:
            code_globals[name] = imported

    return name


@lambda_.command(name="import")
@utils.owner
async def import_(message: discord.Message, module: str, attr: str=None):
    """ Import the specified module. Specifying `attr` will act like `from attr import module`.

    If the given attribute starts with a colon :, the name for the module will be defined as
    whatever follows the colon character. If nothing follows, the last subcommand in the module
    is used. """
    try:
        name = import_module(module, attr)
    except ImportError:
        await client.say(message, "Unable to import `{}`.".format(module))
    except KeyError:
        await client.say(message, "Unable to import `{}` from `{}`.".format(attr, module))
    else:
        # There were no errors when importing, so we add the name to our startup imports
        lambda_config.data["imports"].append((module, attr))
        lambda_config.save()
        await client.say(message, "Imported and setup `{}` for import.".format(name))


@lambda_.command()
async def source(message: discord.Message, trigger: str):
    """ Disable source of a command """
    assert trigger in lambdas.data, "Command `{}` does not exist.".format(trigger)

    # The command exists so we display the source
    await client.say(message, "```py\n{}```".format(lambdas.data[trigger]))


@plugins.command(hidden=True)
async def ping(message: discord.Message):
    """ Tracks the time spent parsing the command and sending a message. """
    # Track the time it took to receive a message and send it.
    start_time = datetime.now()
    first_message = await client.say(message, "Pong!")
    stop_time = datetime.now()

    # Edit our message with the tracked time (in ms)
    time_elapsed = (stop_time - start_time).microseconds / 1000
    await client.edit_message(first_message, "Pong! `{elapsed:.4f}ms`".format(elapsed=time_elapsed))


async def get_changelog(num: int):
    """ Get the latest commit messages from PCBOT. """
    since = datetime.utcnow() - timedelta(days=7)
    commits = await utils.download_json("https://api.github.com/repos/{}commits".format(config.github_repo),
                                        since=since.strftime("%Y-%m-%dT00:00:00"))
    changelog = []

    # Go through every commit and add "- " in front of the first line and "  " for all other lines
    # Also add dates after each commit
    for commit in commits[:num]:
        commit_message = commit["commit"]["message"]
        commit_date = commit["commit"]["committer"]["date"]

        formatted_commit = []

        for i, line in enumerate(commit_message.split("\n")):
            if not line == "":
                line = ("- " if i == 0 else "  ") + line

            formatted_commit.append(line)

        # Add the date as well as the
        changelog.append("\n".join(formatted_commit) + "\n  " + commit_date.replace("T", " ").replace("Z", ""))

    # Return formatted changelog
    return "```\n{}```".format("\n\n".join(changelog))


@plugins.command(name=config.name.lower())
async def bot_info(message: discord.Message):
    """ Display basic information. """
    app_info = await client.application_info()

    await client.say(message, "**{ver}** - **{name}** ```elm\n"
                              "Owner   : {owner}\n"
                              "Up      : {up} UTC\n"
                              "Servers : {servers}```"
                              "{desc}".format(
        ver=config.version, name=app_info.name,
        repo="https://github.com/{}".format(config.github_repo),
        owner=str(app_info.owner),
        up=client.time_started.strftime("%d-%m-%Y %H:%M:%S"),
        servers=len(client.servers),
        desc=app_info.description.replace("\\n", "\n")
    ))


@bot_info.command(name="changelog")
async def changelog_(message: discord.Message, num: utils.int_range(f=1)=3):
    """ Get `num` requests from the changelog. Defaults to 3. """
    await client.say(message, await get_changelog(num))


def init():
    """ Import any imports for lambdas. """
    # Add essential globals for "do", "eval" and "lambda" commands
    code_globals.update(dict(
        utils=utils, datetime=datetime, timedelta=timedelta,
        random=random, asyncio=asyncio, plugins=plugins,
        plugin=plugins.get_plugin, command=plugins.get_command, execute=plugins.execute
    ))

    # Import modules for "do", "eval" and "lambda" commands
    for module, attr in lambda_config.data["imports"]:
        # Let's not import any already existing modules
        if (attr or module) not in code_globals:
            try:
                import_module(module, attr)
            except (KeyError, ImportError):  # The module doesn't work, so we skip it
                pass
            else:
                continue

        # Something went wrong and we'll remove the module from the config
        lambda_config.data["imports"].remove([module, attr])
        lambda_config.save()


@plugins.event()
async def on_message(message: discord.Message):
    """ Perform lambda commands. """
    args = utils.split(message.content)

    # Check if the command is a lambda command and is not disabled (in the blacklist)
    if args[0] in lambdas.data and args[0] not in lambda_config.data["blacklist"]:
        def arg(i, default=0):
            if len(args) > i:
                return args[i]
            else:
                return default

        code_globals.update(dict(arg=arg, args=args, message=message, client=client,
                                 author=message.author, server=message.server, channel=message.channel))
        python_code = lambdas.data[args[0]]

        # Create an async function so that we can await it using the result of eval
        python_code = "async def lambda_session():\n    " + "\n    ".join(line for line in python_code.split("\n"))
        try:
            exec(python_code, code_globals)
        except SyntaxError as e:
            if utils.is_owner(message.author):
                await client.say(message, "```" + utils.format_syntax_error(e) + "```")
            else:
                logging.warning("An exception occurred when parsing lambda command:"
                                "\n{}".format(utils.format_syntax_error(e)))
            return True

        # Execute the command
        try:
            await eval("lambda_session()", code_globals)
        except AssertionError as e:  # Send assertion errors to the core module
            raise AssertionError(e)
        except Exception as e:
            if utils.is_owner(message.author):
                await client.say(message, "```" + utils.format_exception(e) + "```")
            else:
                logging.warning("An exception occurred when parsing lambda command:"
                                "\n{}".format(utils.format_exception(e)))

        return True


# Initialize the plugin's modules
init()
