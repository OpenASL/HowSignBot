import asyncio
import datetime as dt
import difflib
import logging
import random
import re
from contextlib import suppress
from typing import Optional
from urllib.parse import quote_plus

import aiohttp
import discord
import gspread
from discord.ext import commands
from discord.ext.commands import Context
from environs import Env
from google.auth.crypt._python_rsa import RSASigner
from google.oauth2.service_account import Credentials

import handshapes
import cuteid
import catchphrase
import meetings

# -----------------------------------------------------------------------------

__version__ = "20.28.0"

env = Env(eager=False)
env.read_env()

LOG_LEVEL = env.log_level("LOG_LEVEL", logging.INFO)
DISCORD_TOKEN = env.str("DISCORD_TOKEN", required=True)
OWNER_ID = env.int("OWNER_ID", required=True)
COMMAND_PREFIX = env.str("COMMAND_PREFIX", "?")


GOOGLE_PROJECT_ID = env.str("GOOGLE_PROJECT_ID", required=True)
GOOGLE_PRIVATE_KEY = env.str("GOOGLE_PRIVATE_KEY", required=True)
GOOGLE_PRIVATE_KEY_ID = env.str("GOOGLE_PRIVATE_KEY_ID", required=True)
GOOGLE_CLIENT_EMAIL = env.str("GOOGLE_CLIENT_EMAIL", required=True)
GOOGLE_TOKEN_URI = env.str("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token")
FEEDBACK_SHEET_KEY = env.str("FEEDBACK_SHEET_KEY", required=True)

ZOOM_USER_ID = env.str("ZOOM_USER_ID", required=True)
ZOOM_JWT = env.str("ZOOM_JWT", required=True)

WATCH2GETHER_API_KEY = env.str("WATCH2GETHER_API_KEY", required=True)

env.seal()

logging.basicConfig(level=LOG_LEVEL)

logger = logging.getLogger("bot")

bot = commands.Bot(command_prefix=COMMAND_PREFIX, owner_id=OWNER_ID)

# -----------------------------------------------------------------------------

_spoiler_pattern = re.compile(r"\s*\|\|\s*(\S*)\s*\|\|\s*")


def get_spoiler_text(val: str) -> Optional[str]:
    """Return value within spoiler text if it exists, else return `None`."""
    match = _spoiler_pattern.match(val)
    if match:
        return match.groups()[0]
    return None


def did_you_mean(word, possibilities):
    try:
        return difflib.get_close_matches(word, possibilities, n=1, cutoff=0.5)[0]
    except IndexError:
        return None


async def wait_for_stop_sign(message: discord.Message, *, replace_with: str):
    def check(reaction, user):
        return reaction.message.id == message.id and str(reaction.emoji) == "🛑"

    try:
        await bot.wait_for("reaction_add", check=check)
    finally:
        logger.info(f"replacing message with: {replace_with}")
        await message.edit(content=replace_with)


# -----------------------------------------------------------------------------


@bot.event
async def on_ready():
    activity = discord.Activity(
        name=f"{COMMAND_PREFIX}howsign | {COMMAND_PREFIX}handshapes",
        type=discord.ActivityType.playing,
    )
    await bot.change_presence(activity=activity)


# -----------------------------------------------------------------------------

HOWSIGN_TEMPLATE = """{word_uppercased}
_Lifeprint_ : {lifeprint}
_YouGlish_: {youglish}
_Spread The Sign_: <{spread_the_sign}>
_SigningSavvy_: {signingsavvy}
"""

HOWSIGN_SPOILER_TEMPLATE = """||{word_uppercased}||
_Lifeprint_ : || {lifeprint} ||
_YouGlish_: || {youglish} ||
_Spread The Sign_: || <{spread_the_sign}> ||
_SigningSavvy_: || <{signingsavvy}> ||
"""

HOWSIGN_HELP = """Look up a word or phrase

If the word or phrase is sent in spoiler text, i.e. enclosed in `||`, the corresponding links will be blacked out.

Examples:
{COMMAND_PREFIX}howsign tiger
{COMMAND_PREFIX}howsign ||tiger||
{COMMAND_PREFIX}howsign what's up
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)


def howsign_impl(word: str):
    spoiler = get_spoiler_text(word)
    word = spoiler if spoiler else word
    template = HOWSIGN_SPOILER_TEMPLATE if spoiler else HOWSIGN_TEMPLATE
    log = (
        f"sending spoiler links for: '{word}'"
        if spoiler
        else f"sending links for: '{word}'"
    )
    logger.info(log)
    quoted_word = quote_plus(word)
    return {
        "content": template.format(
            word_uppercased=word.upper(),
            lifeprint=f"https://www.google.com/search?&q=site%3Alifeprint.com+{quoted_word}",
            signingsavvy=f"https://www.signingsavvy.com/search/{quoted_word}",
            spread_the_sign=f"https://www.spreadthesign.com/en.us/search/?q={quoted_word}",
            youglish=f"https://youglish.com/pronounce/{quoted_word}/signlanguage/asl",
        )
    }


@bot.command(name="howsign", aliases=("sign",), help=HOWSIGN_HELP)
async def howsign_command(ctx: Context, *, word: str):
    await ctx.send(**howsign_impl(word))


@howsign_command.error
async def howsign_error(ctx, error):
    if isinstance(error, commands.errors.MissingRequiredArgument):
        logger.info(f"missing argument to '{ctx.invoked_with}'")
        await ctx.send(
            f"Enter a word or phrase after `{COMMAND_PREFIX}{ctx.invoked_with}`"
        )
    else:
        logger.error(
            f"unexpected error when handling '{ctx.invoked_with}'", exc_info=error
        )


# -----------------------------------------------------------------------------


HANDSHAPE_HELP = """Show a random or specific handshape

Examples:
{COMMAND_PREFIX}handshape
{COMMAND_PREFIX}handshape claw5

Enter {COMMAND_PREFIX}handshapes to show a list of handshapes.
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)


def handshape_impl(name: str):
    logger.info(f"handshape: '{name}'")
    if name == "random":
        name = random.choice(tuple(handshapes.HANDSHAPES.keys()))
        logger.info(f"chose '{name}'")

    try:
        handshape = handshapes.get_handshape(name)
    except handshapes.HandshapeNotFoundError:
        logger.info(f"handshape '{name}' not found")
        suggestion = did_you_mean(name, tuple(handshapes.HANDSHAPES.keys()))
        if suggestion:
            return {
                "content": f'"{name}" not found. Did you mean "{suggestion}"? Enter `{COMMAND_PREFIX}handshapes` to see a list of handshapes.'
            }
        else:
            return {
                "content": f'"{name}" not found. Enter `{COMMAND_PREFIX}handshapes` to see a list of handshapes.'
            }

    filename = f"{handshape.name}.png"
    file_ = discord.File(handshape.path, filename=filename)
    embed = discord.Embed(title=handshape.name)
    embed.set_image(url=f"attachment://{filename}")
    return {
        "file": file_,
        "embed": embed,
    }


@bot.command(name="handshape", aliases=("shape",), help=HANDSHAPE_HELP)
async def handshape_command(ctx, name="random"):
    await ctx.send(**handshape_impl(name))


HANDSHAPES_TEMPLATE = """{handshapes}

Enter `{COMMAND_PREFIX}handshape` to display a random handshape or `{COMMAND_PREFIX}handshape [name]` to display a specific handshape.
"""

HANDSHAPES_HELP = """List handshapes

Enter {COMMAND_PREFIX}handshape to display a random handshape or {COMMAND_PREFIX}handshape [name] to display a specific handshape.
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)


def handshapes_impl():
    return {
        "content": HANDSHAPES_TEMPLATE.format(
            handshapes=", ".join(handshapes.HANDSHAPES.keys()),
            COMMAND_PREFIX=COMMAND_PREFIX,
        )
    }


@bot.command(name="handshapes", aliases=("shapes",), help=HANDSHAPES_HELP)
async def handshapes_command(ctx):
    logger.info("sending handshapes list")
    await ctx.send(**handshapes_impl())


# -----------------------------------------------------------------------------


def get_gsheet_client():
    signer = RSASigner.from_string(key=GOOGLE_PRIVATE_KEY, key_id=GOOGLE_PRIVATE_KEY_ID)
    credentials = Credentials(
        signer=signer,
        service_account_email=GOOGLE_CLIENT_EMAIL,
        token_uri=GOOGLE_TOKEN_URI,
        scopes=gspread.auth.DEFAULT_SCOPES,
        project_id=GOOGLE_PROJECT_ID,
    )
    return gspread.authorize(credentials)


def post_feedback(username: str, feedback: str, guild: Optional[str]):
    # Assumes rows are in the format (date, feedback, guild, version)
    client = get_gsheet_client()
    sheet = client.open_by_key(FEEDBACK_SHEET_KEY)
    now = dt.datetime.now(dt.timezone.utc)
    worksheet = sheet.get_worksheet(0)
    row = (now.isoformat(), feedback, guild or "", __version__)
    logger.info(f"submitting feedback: {row}")
    return worksheet.append_row(row)


@bot.command(name="feedback", help="Anonymously share an idea or report a bug")
async def feedback_command(ctx: Context, *, feedback):
    author = ctx.author
    username = ctx.author.name
    guild = author.guild.name if hasattr(author, "guild") else None
    post_feedback(username, feedback, guild)
    await ctx.send("🙌 Your feedback has been received! Thank you for your help.")


@feedback_command.error
async def feedback_error(ctx, error):
    if isinstance(error, commands.errors.MissingRequiredArgument):
        logger.info("missing argument to 'feedback'")
        await ctx.send(
            f"I ♥️ feedback! Enter a your feedback after `{COMMAND_PREFIX}feedback`"
        )
    else:
        logger.error(
            f"unexpected error when handling '{ctx.invoked_with}'", exc_info=error
        )


# -----------------------------------------------------------------------------


async def get_random_sentence() -> str:
    async with aiohttp.ClientSession() as client:
        resp = await client.get("https://randomwordgenerator.com/json/sentences.json")
    data = await resp.json()
    return random.choice(data["data"])["sentence"]


SENTENCE_HELP = """Display a random sentence

Enter {COMMAND_PREFIX}sentence || to display the sentence in spoiler text.
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)


@bot.command(name="sentence", help=SENTENCE_HELP)
async def sentence_command(ctx, spoiler: Optional[str]):
    sentence = await get_random_sentence()
    should_spoil = spoiler and spoiler.startswith("||")
    if should_spoil:
        sentence = f"||{sentence}||"
    log = (
        f"sending random sentence in spoiler text: '{sentence}'"
        if should_spoil
        else f"sending random sentence: '{sentence}'"
    )
    logger.info(log)
    await ctx.send(sentence)


# -----------------------------------------------------------------------------


async def get_random_idiom() -> dict:
    async with aiohttp.ClientSession() as client:
        resp = await client.get("https://randomwordgenerator.com/json/phrases.json")
    data = await resp.json()
    return random.choice(data["data"])


IDIOM_HELP = """Display a random English idiom

Enter {COMMAND_PREFIX}idiom || to display the idiom and its meaning in spoiler text.
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)

IDIOM_TEMPLATE = """**{idiom}**
Meaning: {meaning}
"""

IDIOM_SPOILER_TEMPLATE = """||**{idiom}**||
Meaning: ||{meaning}||
"""


@bot.command(name="idiom", help=IDIOM_HELP)
async def idiom_command(ctx, spoiler: Optional[str]):
    data = await get_random_idiom()
    should_spoil = spoiler and spoiler.startswith("||")
    log = (
        f"sending random idiom in spoiler text: {data}"
        if should_spoil
        else f"sending random idiom: {data}"
    )
    logger.info(log)
    template = IDIOM_SPOILER_TEMPLATE if should_spoil else IDIOM_TEMPLATE
    await ctx.send(template.format(idiom=data["phrase"], meaning=data["meaning"]))


# -----------------------------------------------------------------------------


ZOOM_CLOSED_MESSAGE = "✨ _Zoom meeting ended_"


@bot.command(name="zoom", help="BOT OWNER ONLY: Create a Zoom meeting")
@commands.is_owner()
async def zoom_command(ctx: Context, *, topic: Optional[str]):
    logger.info("creating zoom meeting")
    try:
        meeting = await meetings.create_zoom(
            token=ZOOM_JWT,
            user_id=ZOOM_USER_ID,
            topic=topic or "PRACTICE",
            settings={
                "host_video": False,
                "participant_video": False,
                "mute_upon_entry": True,
                "waiting_room": False,
            },
        )
    except Exception:
        logger.exception("could not create Zoom meeting")
        message = await ctx.send(
            content="🚨 _Could not create Zoom meeting. That's embarrassing._"
        )
    else:
        content = f"**Join URL**: <{meeting.join_url}>\n**Passcode**: {meeting.passcode}"
        if topic:
            content = f"{content}\n**Topic**: {topic}"
        content = f"{content}\n🚀 This meeting is happening now. Go practice!\n*After the meeting ends, react with 🛑 to remove this message.*"
        message = await ctx.send(content=content)

    await wait_for_stop_sign(message, replace_with=ZOOM_CLOSED_MESSAGE)


@zoom_command.error
async def zoom_error(ctx, error):
    if isinstance(error, commands.errors.CheckFailure):
        logger.info(f"unauthorized zoom access attempt by {ctx.author}")
    else:
        logger.error(
            f"unexpected error when handling '{ctx.invoked_with}'", exc_info=error
        )


# -----------------------------------------------------------------------------

MEET_TEMPLATE = """**Join URL**: <{join_url}>
🚀 This meeting is happening now. Go practice!
*After the meeting ends, react with 🛑 to remove this message.*
"""

MEET_CLOSED_MESSAGE = "✨ _Jitsi Meet ended_"


@bot.command(name="meet", aliases=("jitsi",), help="Start a Jitsi Meet meeting")
async def meet_command(ctx: Context):
    join_url = meetings.create_jitsi_meet()
    content = MEET_TEMPLATE.format(join_url=join_url)
    logger.info("sending jitsi meet info")
    message = await ctx.send(content=content)

    await wait_for_stop_sign(message, replace_with=MEET_CLOSED_MESSAGE)


# -----------------------------------------------------------------------------


WATCH2GETHER_HELP = """Create a new watch2gether room

You can optionally pass a URL to use for the first video.

Examples:
{COMMAND_PREFIX}w2g
{COMMAND_PREFIX}w2g https://www.youtube.com/watch?v=DaMjr4AfYA0
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)

WATCH2GETHER_TEMPLATE = """<{url}>
🚀 Watch videos together!
*React to this message with 🛑 to close the room.*
"""

WATCH2GETHER_WITH_URL_TEMPLATE = """<{url}>
🚀 Watch videos together!
Queued video: <{video_url}>
*React to this message with 🛑 to close the room.*
"""

WATCH2GETHER_CLOSED_MESSAGE = "✨ _watch2gether room closed_"


@bot.command(
    name="w2g",
    aliases=("wtg", "watch2gether"),
    help=WATCH2GETHER_HELP,
)
async def watch2gether_command(ctx: Context, video_url: str = None):
    logger.info("creating watch2gether meeting")
    try:
        url = await meetings.create_watch2gether(WATCH2GETHER_API_KEY, video_url)
    except Exception:
        logger.exception("could not create watch2gether room")
        message = await ctx.send(
            content="🚨 _Could not create watch2gether room. That's embarrassing._"
        )
    else:
        template = WATCH2GETHER_WITH_URL_TEMPLATE if video_url else WATCH2GETHER_TEMPLATE
        content = template.format(url=url, video_url=video_url)
        message = await ctx.send(content=content)

    await wait_for_stop_sign(message, replace_with=WATCH2GETHER_CLOSED_MESSAGE)


# -----------------------------------------------------------------------------

CODENAMES_CLOSED_MESSAGE = "✨ _Codenames game ended_"


def make_teams(players):
    red, blue = [], []
    for player in reversed(players):
        team = min(red, blue, key=len)
        team.append(player)
    return red, blue


def format_team(players):
    names = [getattr(each, "nick", None) or each.name for each in players]
    return ", ".join(names)


@bot.command(name="codenames", aliases=("cn",), help="Start a Codenames game")
async def codenames_command(ctx: Context, name: str = None):
    name = name or cuteid.cuteid()
    url = f"https://horsepaste.com/{name}"
    base_message = f"🕵️ **Codenames** 🕵️\n{url}\nReact with 👍 to join a team. React with 🛑 to end the game."
    logger.info(f"starting codenames game at {url}")
    message = await ctx.send(base_message)

    def check(reaction, user):
        return reaction.message.id == message.id

    players = []
    while True:
        done, pending = await asyncio.wait(
            (
                bot.wait_for("reaction_add", check=check),
                bot.wait_for("reaction_remove", check=check),
            ),
            return_when=asyncio.FIRST_COMPLETED,
        )
        reaction, _ = done.pop().result()
        for future in pending:
            future.cancel()
        if str(reaction.emoji) == "🛑":
            logger.info("scrubbing codenames info")
            await message.edit(content=CODENAMES_CLOSED_MESSAGE)
            break
        elif str(reaction.emoji) in ("👍", "🔄"):
            if str(reaction.emoji) == "🔄":
                logger.info("shuffling players")
                random.shuffle(players)
            else:
                players = await reaction.users().flatten()
            red, blue = make_teams(players)
            logger.info(f"total players: {len(players)}")
            await message.edit(
                content=f"{base_message}\n🔴 Red: {format_team(red)}\n🔵 Blue: {format_team(blue)}"
            )


# -----------------------------------------------------------------------------

NUM_CATCHPHRASE_WORDS = 8


def catchphrase_impl(category: str = None):
    category = category.lower() if category else None
    if category == "categories":
        categories = ", ".join(catchphrase.CATEGORIES)
        return {
            "content": f"{categories}\nEnter `{COMMAND_PREFIX}cp` or `{COMMAND_PREFIX}cp [category]` to generate a list of words/phrases."
        }

    if category and category not in catchphrase.CATEGORIES:
        logger.info(f"invalid category: {category}")
        categories = ", ".join(catchphrase.CATEGORIES)
        suggestion = did_you_mean(category, catchphrase.CATEGORIES)
        if suggestion:
            return {
                "content": f'"{category}" is not a valid category. Did you mean "{suggestion}"?\nCategories: {categories}'
            }
        else:
            return {
                "content": f'"{category}" is not a valid category.\nCategories: {categories}'
            }
    words = "\n".join(
        f"||{catchphrase.catchphrase(category)}||" for _ in range(NUM_CATCHPHRASE_WORDS)
    )
    message = f"{words}\nEnter `{COMMAND_PREFIX}cp` or `{COMMAND_PREFIX}cp [category]` for more."
    logger.info("sending catchphrase words/phrases")
    return {"content": message}


@bot.command(
    name="catchphrase",
    aliases=("cp",),
    help="Generate a list of random words and phrases",
)
async def catchphrase_command(ctx: Context, category: str = None):
    await ctx.send(**catchphrase_impl(category))


# -----------------------------------------------------------------------------

# Allow cleaning up Zoom, watch2gether, etc. rooms after bot restarts
# Need to use on_raw_reaction_add to handle messages that aren't in the cache

CLOSED_MESSAGE_MAP = {
    r"Could not create Zoom": ZOOM_CLOSED_MESSAGE,
    r"zoom\.us": ZOOM_CLOSED_MESSAGE,
    r"meet\.jit\.si": MEET_CLOSED_MESSAGE,
    r"Could not create watch2gether": WATCH2GETHER_CLOSED_MESSAGE,
    r"Watch videos together": WATCH2GETHER_CLOSED_MESSAGE,
    r"Codenames": CODENAMES_CLOSED_MESSAGE,
}


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if str(payload.emoji) == "🛑" and payload.channel_id:
        with suppress(discord.NotFound):
            channel = bot.get_channel(payload.channel_id)
            if not channel:
                return
            message = await channel.fetch_message(payload.message_id)
            if message.author.id != bot.user.id:
                return
            # Cached messages will already be handled
            for cached_message in bot.cached_messages:
                if message.id == cached_message.id:
                    return

            for pattern, close_message in CLOSED_MESSAGE_MAP.items():
                if re.search(pattern, message.content):
                    logger.info(f"cleaning up room with message: {close_message}")
                    await message.edit(content=close_message)
                    return


if __name__ == "__main__":
    logger.info("starting bot")
    bot.run(DISCORD_TOKEN)
