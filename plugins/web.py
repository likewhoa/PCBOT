""" Plugin for web commands

Commands:
    define
"""

import discord

from pcbot import Annotate, utils
from plugins import command, client


@command()
async def define(message: discord.Message, term: Annotate.LowerCleanContent):
    """ Defines a term using Urban Dictionary. """
    json = await utils.download_json("http://api.urbandictionary.com/v0/define", term=term)
    assert json["list"], "Could not define `{}`.".format(term)

    definitions = json["list"]
    msg = ""

    # Send any valid definition (length of message < 2000 characters)
    for definition in definitions:
        # Format example in code if there is one
        if definition.get("example"):
            definition["example"] = "```{}```".format(definition["example"])

        # Format definition
        msg = "**{word}**:\n{definition}{example}".format(**definition)

        # If this definition fits in a message, break the loop so that we can send it
        if len(msg) <= 2000:
            break

    # Cancel if the message is too long
    assert len(msg) <= 2000, "Defining this word would be a bad idea."

    await client.say(message, msg)
