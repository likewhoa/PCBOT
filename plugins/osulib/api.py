""" API integration for osu!

    Adds Mods enums with raw value calculations and some
    request functions. """

from enum import Enum
import re

from pcbot import utils


api_url = "https://osu.ppy.sh/api/"
api_key = ""
requests_sent = 0

ripple_url = "https://ripple.moe/api/"
ripple_regex = re.compile(r"ripple:\s*(?P<data>.+)")


def set_api_key(s: str):
    """ Set the osu! API key. This simplifies every API function as they
    can exclude the "k" parameter. """
    global api_key
    api_key = s


class GameMode(Enum):
    """ Enum for gamemodes. """
    Standard = 0
    Taiko = 1
    Catch = 2
    Mania = 3

    @classmethod
    def get_mode(cls, mode: str):
        """ Return the mode with the specified string. """
        for enum in cls:
            if enum.name.lower().startswith(mode.lower()):
                return enum

        return None


class Mods(Enum):
    """ Enum for displaying mods. """
    NF = 0
    EZ = 1
    NV = 2
    HD = 3
    HR = 4
    SD = 5
    DT = 6
    RX = 7
    HT = 8
    NC = 9
    FL = 10
    AU = 11
    SO = 12
    AP = 13
    PF = 14
    Key4 = 15
    Key5 = 16
    Key6 = 17
    Key7 = 18
    Key8 = 19
    KeyMod = Key4 | Key5 | Key6 | Key7 | Key8         # ¯\_(ツ)_/¯
    FI = 20
    RD = 21
    LastMod = 22
    FreeModAllowed = NF | EZ | HD | HR | SD | FL | \
                     FI | RX | AP | SO | KeyMod       # ¯\_(ツ)_/¯
    Key9 = 24
    Key10 = 25
    Key1 = 26
    Key3 = 27
    Key2 = 28

    def __new__(cls, num):
        """ Convert the given value to 2^num. """
        obj = object.__new__(cls)
        obj._value_ = 2 ** num
        return obj

    @classmethod
    def list_mods(cls, bitwise: int):
        """ Return a list of mod enums from the given bitwise (enabled_mods in the osu! API) """
        bin_str = str(bin(bitwise))[2:]
        bin_list = [int(d) for d in bin_str[::-1]]
        mods_bin = (pow(2, i) for i, d in enumerate(bin_list) if d == 1)
        mods = [cls(mod) for mod in mods_bin]

        # Manual checks for multiples
        if Mods.DT in mods and Mods.NC in mods:
            mods.remove(Mods.DT)

        return mods

    @classmethod
    def format_mods(cls, mods):
        """ Return a string with the mods in a sorted format, such as DTHD.

        mods is either a bitwise or a list of mod enums. """
        if type(mods) is int:
            mods = cls.list_mods(mods)
        assert type(mods) is list

        return "".join((mod.name for mod in mods) if mods else ["Nomod"])


def def_section(api_name: str, first_element: bool=False):
    """ Add a section using a template to simplify adding API functions. """
    async def template(url=api_url, **params):
        global requests_sent

        if "u" in params:
            ripple = ripple_regex.match(params["u"])
            if ripple:
                params["u"] = ripple.group("data")
                url = ripple_url

        if url == api_url and "k" not in params:
            params["k"] = api_key

        # Download using a URL of the given API function name
        json = await utils.download_json(url + api_name, **params)
        requests_sent += 1

        if json is None:
            return None

        # Unless we want to extract the first element, return the entire object (usually a list)
        if not first_element:
            return json

        # If the returned value should be the first element, see if we can cut it
        if len(json) < 1:
            return None

        return json[0]

    # Set the correct name of the function and add simple docstring
    template.__name__ = api_name
    template.__doc__ = "Get " + ("list" if not first_element else "dict") + " using " + api_url + api_name
    return template


# Define all osu! API requests using the template
get_beatmaps = def_section("get_beatmaps")
get_user = def_section("get_user", first_element=True)
get_scores = def_section("get_scores")
get_user_best = def_section("get_user_best")
get_user_recent = def_section("get_user_recent")
get_match = def_section("get_match", first_element=True)
get_replay = def_section("get_replay")

beatmap_url_regex = re.compile(r"http[s]?://osu.ppy.sh/(?P<type>b|s)/(?P<id>\d+)")


async def beatmap_from_url(url: str, mode: GameMode=GameMode.Standard):
    """ Takes a url and returns the beatmap in the specified gamemode.
    If a url for a submission is given, it will find the most difficult map. """
    match = beatmap_url_regex.match(url)

    # If there was no match, the operation was unsuccessful
    if not match:
        raise SyntaxError("The given URL is invalid.")

    # Get the beatmap specified
    if match.group("type") == "b":
        difficulties = await get_beatmaps(b=match.group("id"), m=mode.value, limit=1)
    else:
        difficulties = await get_beatmaps(s=match.group("id"), m=mode.value)

    # If the beatmap doesn't exist, the operation was unsuccessful
    if not difficulties:
        raise LookupError("The beatmap with the given URL was not found.")

    # Find the most difficult beatmap
    beatmap = None
    highest = -1
    for diff in difficulties:
        stars = float(diff["difficultyrating"])
        if stars > highest:
            beatmap, highest = diff, stars

    return beatmap


async def beatmapset_from_url(url: str):
    """ Takes a url and returns the beatmapset of the specified beatmap. """
    match = beatmap_url_regex.match(url)

    # If there was no match, the operation was unsuccessful
    if not match:
        raise SyntaxError("The given URL is invalid.")

    if match.group("type") == "b":
        difficulty = await get_beatmaps(b=match.group("id"), limit=1)

        # If the beatmap doesn't exist, the operation was unsuccessful
        if not difficulty:
            raise LookupError("The beatmap with the given URL was not found.")

        beatmapset_id = difficulty[0]["beatmapset_id"]
    else:
        beatmapset_id = match.group("id")

    beatmapset = await get_beatmaps(s=beatmapset_id)

    # Also make sure we get the beatmap
    if not beatmapset:
        raise LookupError("The beatmap with the given URL was not found.")

    return beatmapset


def lookup_beatmap(beatmaps: list, **lookup):
    """ Finds and returns the first beatmap with the lookup specified.

    Beatmaps is a list of beatmaps and could be used with get_beatmaps()
    Lookup is any key stored in a beatmap from get_beatmaps() """
    if not beatmaps:
        return None

    for beatmap in beatmaps:
        match = True
        for key, value in lookup.items():
            if key.lower() not in beatmap:
                raise KeyError("The list of beatmaps does not have key: {}".format(key))

            if not beatmap[key].lower() == value.lower():
                match = False

        if match:
            return beatmap
    else:
        return None


def rank_from_events(events: dict, beatmap_id: str):
    """ Return the rank of the first score of given beatmap_id from a
    list of events gathered via get_user() or None. """
    for event in events:
        if event["beatmap_id"] == beatmap_id:
            match = re.search(r"rank\s#(?P<rank>\d+)(?:<|\s)", event["display_html"])

            if match:
                return int(match.group("rank"))
    else:
        return None
