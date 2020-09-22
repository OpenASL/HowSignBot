import asyncio
import datetime as dt
import difflib
import logging
import random
import re
from contextlib import suppress
from typing import Optional, NamedTuple, List, Callable, Union
from urllib.parse import quote_plus

import discord
import dateparser
import gspread
from aiohttp import web
from discord.ext import commands, tasks
from discord.ext.commands import Context
from environs import Env
from google.auth.crypt._python_rsa import RSASigner
from google.oauth2.service_account import Credentials
import pytz

import handshapes
import cuteid
import catchphrase
import meetings

# -----------------------------------------------------------------------------

__version__ = "20.50.1"

env = Env(eager=False)
env.read_env()

LOG_LEVEL = env.log_level("LOG_LEVEL", logging.INFO)
DISCORD_TOKEN = env.str("DISCORD_TOKEN", required=True)
OWNER_ID = env.int("OWNER_ID", required=True)
SECRET_KEY = env.str("SECRET_KEY", required=True)
COMMAND_PREFIX = env.str("COMMAND_PREFIX", "?")

GOOGLE_PROJECT_ID = env.str("GOOGLE_PROJECT_ID", required=True)
GOOGLE_PRIVATE_KEY = env.str("GOOGLE_PRIVATE_KEY", required=True)
GOOGLE_PRIVATE_KEY_ID = env.str("GOOGLE_PRIVATE_KEY_ID", required=True)
GOOGLE_CLIENT_EMAIL = env.str("GOOGLE_CLIENT_EMAIL", required=True)
GOOGLE_TOKEN_URI = env.str("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token")
FEEDBACK_SHEET_KEY = env.str("FEEDBACK_SHEET_KEY", required=True)
SCHEDULE_SHEET_KEYS = env.dict("SCHEDULE_SHEET_KEYS", required=True, subcast_key=int)
SCHEDULE_CHANNELS = env.dict(
    "SCHEDULE_CHANNELS", required=True, subcast_key=int, subcast=int
)


ZOOM_USER_ID = env.str("ZOOM_USER_ID", required=True)
ZOOM_JWT = env.str("ZOOM_JWT", required=True)

WATCH2GETHER_API_KEY = env.str("WATCH2GETHER_API_KEY", required=True)
# Default to 10 AM EDT
_daily_practice_send_time_raw = env.str("DAILY_PRACTICE_SEND_TIME", "14:00")
_hour, _min = _daily_practice_send_time_raw.split(":")
DAILY_PRACTICE_SEND_TIME = dt.time(hour=int(_hour), minute=int(_min))

env.seal()

logging.basicConfig(level=LOG_LEVEL)

logger = logging.getLogger("bot")

bot = commands.Bot(
    command_prefix=COMMAND_PREFIX, case_insensitive=True, owner_id=OWNER_ID
)

# -----------------------------------------------------------------------------

_spoiler_pattern = re.compile(r"\s*\|\|\s*(.*)\s*\|\|\s*")


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


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


STOP_SIGN = "🛑"


async def wait_for_stop_sign(message: discord.Message, *, replace_with: str):
    with suppress(Exception):
        await message.add_reaction(STOP_SIGN)

    def check(reaction, user):
        return (
            user.id != bot.user.id
            and reaction.message.id == message.id
            and str(reaction.emoji) == STOP_SIGN
        )

    await bot.wait_for("reaction_add", check=check)
    logger.info(f"replacing message with: {replace_with}")
    await message.edit(content=replace_with)


# -----------------------------------------------------------------------------


@bot.event
async def on_ready():
    activity = discord.Activity(
        name=f"{COMMAND_PREFIX}sign | {COMMAND_PREFIX}handshapes",
        type=discord.ActivityType.playing,
    )
    daily_practice_message.start()
    await bot.change_presence(activity=activity)


# -----------------------------------------------------------------------------

SIGN_TEMPLATE = """[👋 **Handspeak** - Search results]({handspeak})
[🧬 **Lifeprint** - Search results]({lifeprint})
[🤝 **SigningSavvy** - Sign for {word_uppercased}]({signingsavvy})
[🌐 **Spread The Sign** - {word_uppercased}]({spread_the_sign})
[📹 **YouGlish** - ASL videos with {word_uppercased}]({youglish})
"""

SIGN_SPOILER_TEMPLATE = """[👋 **Handspeak** - Search results]({handspeak})
[🧬 **Lifeprint** - Search results]({lifeprint})
[🤝 **SigningSavvy** - Sign for ||{word_uppercased}||]({signingsavvy})
[🌐 **Spread The Sign** - ||{word_uppercased}||]({spread_the_sign})
[📹 **YouGlish** - ASL videos with ||{word_uppercased}||]({youglish})
"""

SIGN_HELP = """Look up a word or phrase

If the word or phrase is sent in spoiler text, i.e. enclosed in `||`, the word will also be blacked out in the reply.
To search multiple words/phrases, separate the values with a comma.

Examples:
{COMMAND_PREFIX}sign tiger
{COMMAND_PREFIX}sign ||tiger||
{COMMAND_PREFIX}sign what's up
{COMMAND_PREFIX}sign church, chocolate, computer
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)


def word_display(word: str, *, has_spoiler: bool):
    quoted_word = quote_plus(word)
    template = SIGN_SPOILER_TEMPLATE if has_spoiler else SIGN_TEMPLATE
    return template.format(
        word_uppercased=word.upper(),
        lifeprint=f"https://www.google.com/search?&q=site%3Alifeprint.com+{quoted_word}",
        handspeak=f"https://www.google.com/search?&q=site%3Ahandspeak.com+{quoted_word}",
        signingsavvy=f"https://www.signingsavvy.com/search/{quoted_word}",
        spread_the_sign=f"https://www.spreadthesign.com/en.us/search/?q={quoted_word}",
        youglish=f"https://youglish.com/pronounce/{quoted_word}/signlanguage/asl",
    )


def sign_impl(word: str):
    logger.info(f"sending links for: '{word}'")
    spoiler = get_spoiler_text(word)
    word = spoiler if spoiler else word
    has_multiple = "," in word
    if has_multiple:
        words = word.split(",")
        embed = discord.Embed()
        for word in words:
            word = word.strip()
            title = f"||{word.upper()}||" if spoiler else word.upper()
            embed.add_field(name=title, value=word_display(word, has_spoiler=spoiler))
    else:
        title = f"||{word.upper()}||" if spoiler else word.upper()
        embed = discord.Embed(
            title=title,
            description=word_display(word, has_spoiler=spoiler),
        )

    return {"embed": embed}


@bot.command(name="sign", aliases=("howsign",), help=SIGN_HELP)
async def sign_command(ctx: Context, *, word: str):
    # TODO: Remove. This is just for identifying guild and channel IDs for the daily schedule
    if ctx.guild:
        logger.info(
            f"sign command invoked in guild {ctx.guild.id} ({ctx.guild.name}), channel {ctx.channel.id} (#{ctx.channel.name})"
        )
    await ctx.send(**sign_impl(word))


@sign_command.error
async def sign_error(ctx, error):
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


# -----------------------------------------------------------------------------

EASTERN = pytz.timezone("US/Eastern")
PACIFIC = pytz.timezone("US/Pacific")
TIME_FORMAT = "%-I:%M %p %Z"
TIME_FORMAT_NO_MINUTES = "%-I %p %Z"


def parse_human_readable_datetime(dstr: str) -> Optional[dt.datetime]:
    parsed = dateparser.parse(dstr)
    if not parsed:
        return None
    # Use Pacific time if timezone can't be parsed; return a UTC datetime
    if not parsed.tzinfo:
        parsed = PACIFIC.localize(parsed)
    return parsed.astimezone(dt.timezone.utc)


class PracticeSession(NamedTuple):
    dtime: Optional[dt.datetime]
    host: str
    notes: str


def get_practice_worksheet_for_guild(guild_id: int):
    logger.info(f"fetching practice worksheet {guild_id}")
    client = get_gsheet_client()
    sheet = client.open_by_key(SCHEDULE_SHEET_KEYS[guild_id])
    return sheet.get_worksheet(0)


def get_practice_sessions(
    guild_id: int, dtime: dt.datetime, *, worksheet=None
) -> List[PracticeSession]:
    worksheet = worksheet or get_practice_worksheet_for_guild(guild_id)
    all_values = worksheet.get_all_values()
    sessions = [
        PracticeSession(
            dtime=parse_human_readable_datetime(row[0]),
            host=row[1],
            notes=row[2],
        )
        for row in all_values[2:]
        if row
    ]
    return sorted(
        [
            session
            for session in sessions
            # Assume pacific time when filtering to include all of US
            if session.dtime
            and session.dtime.astimezone(PACIFIC).date()
            == dtime.astimezone(PACIFIC).date()
        ],
        key=lambda s: s.dtime,
    )


def format_multi_time(dtime: dt.datetime) -> str:
    time_format = TIME_FORMAT if dtime.minute != 0 else TIME_FORMAT_NO_MINUTES
    pacific_dstr = dtime.astimezone(PACIFIC).strftime(time_format)
    eastern_dstr = dtime.astimezone(EASTERN).strftime(time_format)
    return f"{pacific_dstr} / {eastern_dstr}"


NO_PRACTICES = """

*There are no scheduled practices yet!*

To schedule a practice, edit the schedule below or use the `{COMMAND_PREFIX}practice` command.
Example: `{COMMAND_PREFIX}practice today at 2pm PDT`
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)


def make_practice_session_embed(
    guild_id: int, sessions: List[PracticeSession], *, dtime: dt.datetime
):
    now_pacific = utcnow().astimezone(PACIFIC)
    dtime_pacific = dtime.astimezone(PACIFIC)
    description = dtime_pacific.strftime("%A, %B %-d")
    if dtime_pacific.date() == now_pacific.date():
        description = f"Today - {description}"
    elif (dtime_pacific.date() - now_pacific.date()).days == 1:
        description = f"Tomorrow - {description}"
    embed = discord.Embed(
        description=description,
        color=discord.Color.orange(),
    )
    if not sessions:
        embed.description += NO_PRACTICES
    else:
        for session in sessions:
            title = format_multi_time(session.dtime)
            value = ""
            if session.host:
                value += f"Host: {session.host}"
            if session.notes:
                value += f"\nNotes: {session.notes}"
            embed.add_field(name=title, value=value or "Practice", inline=False)
    sheet_key = SCHEDULE_SHEET_KEYS[guild_id]
    embed.add_field(
        name="🗓",
        value=f"[Schedule or edit a practice](https://docs.google.com/spreadsheets/d/{sheet_key}/edit)",
    )
    return embed


def make_practice_sessions_today_embed(guild_id: int):
    now = utcnow()
    sessions = get_practice_sessions(guild_id, dtime=now)
    return make_practice_session_embed(guild_id, sessions, dtime=now)


async def is_in_guild(ctx: Context):
    return bool(ctx.guild)


async def send_refreshable_message(
    ctx: Union[Context, discord.TextChannel], make_kwargs: Callable[[], dict]
):
    kwargs = await make_kwargs()
    message = await ctx.send(**kwargs)

    with suppress(Exception):
        await message.add_reaction("🔄")

    def check(reaction, user):
        return (
            user.id != bot.user.id
            and reaction.message.id == message.id
            and reaction.emoji == "🔄"
        )

    while True:
        try:
            done, pending = await asyncio.wait(
                (
                    bot.wait_for("reaction_add", check=check),
                    bot.wait_for("reaction_remove", check=check),
                ),
                return_when=asyncio.FIRST_COMPLETED,
            )
            reaction, user = done.pop().result()
            for future in pending:
                future.cancel()
        except asyncio.TimeoutError:
            # Try to remove the reactions. Fail silently if the bot doesn't have permission.
            with suppress(Exception):
                await message.clear_reactions()
            return
        logger.info("refreshing message")
        kwargs = await make_kwargs()
        await message.edit(**kwargs)
        # Try to remove the reaction. Fail silently if the bot doesn't have permission.
        with suppress(Exception):
            await message.remove_reaction(reaction, user)


@bot.command(
    name="schedule",
    aliases=("practices",),
    help="List today's practice schedule for the current server",
)
@commands.check(is_in_guild)
async def schedule_command(ctx: Context):
    guild = ctx.guild

    async def make_kwargs():
        return {"embed": make_practice_sessions_today_embed(guild.id)}

    await send_refreshable_message(ctx, make_kwargs)


@bot.command(
    name="practice",
    help="Schedule a practice session",
)
@commands.check(is_in_guild)
async def practice_command(ctx: Context, *, start_time: str):
    logger.info(f"scheduling new practice session: {start_time}")
    guild = ctx.guild
    dtime = parse_human_readable_datetime(start_time)
    if not dtime:
        await ctx.send(f'⚠️Could not parse "{start_time}" into a datetime.')
        return
    host = getattr(ctx.author, "nick", ctx.author.name)
    notes = ""
    display_dtime = dtime.astimezone(PACIFIC).strftime("%A, %B %d %I:%M %p %Z %Y")
    row = (display_dtime, host, notes)
    logger.info(f"adding new practice session to sheet: {row}")
    worksheet = get_practice_worksheet_for_guild(guild.id)
    worksheet.append_row(row)
    dtime_pacific = dtime.astimezone(PACIFIC)
    short_display_date = f"{dtime_pacific:%a, %b %d} {format_multi_time(dtime)}"

    async def make_message_kwargs():
        sessions = get_practice_sessions(
            guild_id=guild.id, dtime=dtime, worksheet=worksheet
        )
        embed = make_practice_session_embed(
            guild_id=guild.id, sessions=sessions, dtime=dtime
        )
        return dict(
            content=f"🙌 New practice scheduled for *{short_display_date}*", embed=embed
        )

    await send_refreshable_message(ctx, make_message_kwargs)


@practice_command.error
@schedule_command.error
async def practices_error(ctx, error):
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.send(
            f"`{COMMAND_PREFIX}{ctx.invoked_with}` must be run within a server."
        )
    elif isinstance(error, commands.errors.MissingRequiredArgument):
        logger.info(f"missing argument to '{ctx.invoked_with}'")
        await ctx.send(
            f"⚠️To schedule a practice, enter a time after `{COMMAND_PREFIX}{ctx.invoked_with}`.\n"
            f"Example: `{COMMAND_PREFIX}{ctx.invoked_with} today at 2pm EDT`\n"
            f"Enter `{COMMAND_PREFIX}schedule` to see today's schedule."
        )
    else:
        logger.error(
            f"unexpected error when handling '{ctx.invoked_with}'", exc_info=error
        )


@tasks.loop(seconds=10.0)
async def daily_practice_message():
    now = utcnow()
    date = now.date()
    if now.time() > DAILY_PRACTICE_SEND_TIME:
        date = now.date() + dt.timedelta(days=1)
    then = dt.datetime.combine(date, DAILY_PRACTICE_SEND_TIME)
    logger.info(
        f"practice schedules for {len(SCHEDULE_CHANNELS)} channels will be sent at {then.isoformat()}"
    )
    await discord.utils.sleep_until(then)
    logger.info("sending daily practice schedules")
    for guild_id, channel_id in SCHEDULE_CHANNELS.items():
        try:
            logger.info(
                f"sending daily practice schedule for guild {guild_id}, channel {channel_id}"
            )
            guild = bot.get_guild(guild_id)
            channel = guild.get_channel(channel_id)

            async def make_kwargs():
                return {"embed": make_practice_sessions_today_embed(guild.id)}

            asyncio.ensure_future(send_refreshable_message(channel, make_kwargs))
        except Exception:
            logger.exception(
                f"could not send message to guild {guild_id}, channel {channel_id}"
            )


# -----------------------------------------------------------------------------


def post_feedback(username: str, feedback: str, guild: Optional[str]):
    client = get_gsheet_client()
    # Assumes rows are in the format (date, feedback, guild, version)
    sheet = client.open_by_key(FEEDBACK_SHEET_KEY)
    now = utcnow()
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


SENTENCE_HELP = """Display a random sentence

Enter {COMMAND_PREFIX}sentence || to display the sentence in spoiler text.
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)


def sentence_impl(spoiler: Optional[str]):
    sentence = catchphrase.sentence()
    should_spoil = spoiler and spoiler.startswith("||")
    if should_spoil:
        sentence = f"||{sentence}||"
    log = (
        f"sending random sentence in spoiler text: '{sentence}'"
        if should_spoil
        else f"sending random sentence: '{sentence}'"
    )
    logger.info(log)
    return {"content": sentence}


@bot.command(name="sentence", help=SENTENCE_HELP)
async def sentence_command(ctx, spoiler: Optional[str]):
    await ctx.send(**sentence_impl(spoiler=spoiler))


# -----------------------------------------------------------------------------


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


def idiom_impl(spoiler: Optional[str]):
    data = catchphrase.idiom()
    should_spoil = spoiler and spoiler.startswith("||")
    log = (
        f"sending random idiom in spoiler text: {data}"
        if should_spoil
        else f"sending random idiom: {data}"
    )
    logger.info(log)
    template = IDIOM_SPOILER_TEMPLATE if should_spoil else IDIOM_TEMPLATE
    content = template.format(idiom=data["phrase"], meaning=data["meaning"])
    return {
        "content": content,
    }


@bot.command(name="idiom", help=IDIOM_HELP)
async def idiom_command(ctx, spoiler: Optional[str]):
    await ctx.send(**idiom_impl(spoiler))


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
        content = f"{content}\n🚀 This meeting is happening now. Go practice!\n*After the meeting ends, click {STOP_SIGN} to remove this message.*"
        message = await ctx.send(content=content)

    await wait_for_stop_sign(message, replace_with=ZOOM_CLOSED_MESSAGE)


@zoom_command.error
async def zoom_error(ctx, error):
    if isinstance(error, commands.errors.CheckFailure):
        logger.info(f"unauthorized zoom access attempt by {ctx.author}")
        await ctx.send(
            f"⚠️ `{COMMAND_PREFIX}{ctx.invoked_with}` can only be used by the bot owner because it is using their Zoom account."
        )
    else:
        logger.error(
            f"unexpected error when handling '{ctx.invoked_with}'", exc_info=error
        )


# -----------------------------------------------------------------------------

MEET_CLOSED_MESSAGE = "✨ _Jitsi Meet ended_"


@bot.command(name="meet", aliases=("jitsi",), help="Start a Jitsi Meet meeting")
async def meet_command(ctx: Context, *, name: Optional[str]):
    meeting = meetings.create_jitsi_meet(name, secret=SECRET_KEY)
    content = (
        f"**Join URL**: <{meeting.join_url}>\n**Desktop App Link***: <{meeting.deeplink}>"
    )
    if name:
        content = f"{content}\n**Name**: {name}"
    content = f"{content}\n🚀 This meeting is happening now. Go practice!\n*Desktop App Link requires <https://github.com/jitsi/jitsi-meet-electron>\n*After the meeting ends, click {STOP_SIGN} to remove this message.*"
    logger.info("sending jitsi meet info")
    message = await ctx.send(content=content)

    await wait_for_stop_sign(message, replace_with=MEET_CLOSED_MESSAGE)


# -----------------------------------------------------------------------------

SPEAKEASY_CLOSED_MESSAGE = "✨ _Speakeasy event ended_"


@bot.command(name="speakeasy", help="Start a Speakeasy (https://speakeasy.co/) event")
async def speakeasy_command(ctx: Context, *, name: Optional[str]):
    join_url = meetings.create_speakeasy(name, secret=SECRET_KEY)
    content = f"️🍻 **Speakeasy**\nJoin URL: <{join_url}>"
    if name:
        content = f"{content}\n**Name**: {name}"
    content = f"{content}\n🚀 This event is happening now. Make a friend!\n*After the event ends, click {STOP_SIGN} to remove this message.*"
    logger.info("sending speakeasy info")
    message = await ctx.send(content=content)

    await wait_for_stop_sign(message, replace_with=SPEAKEASY_CLOSED_MESSAGE)


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
*When finished, click 🛑 to remove this message.*
"""

WATCH2GETHER_WITH_URL_TEMPLATE = """<{url}>
🚀 Watch videos together!
Queued video: <{video_url}>
*When finished, click 🛑 to remove this message.*
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


def make_teams(players):
    red, blue = [], []
    for player in reversed(players):
        if len(red) == len(blue):
            team = random.choice([red, blue])
        else:
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
    base_message = f"🕵️ **Codenames** 🕵️\n{url}\nClick 👍 to join a team. Click 🔀 to shuffle the teams."
    logger.info(f"starting codenames game at {url}")
    message = await ctx.send(base_message)

    with suppress(Exception):
        await message.add_reaction("👍")
        await message.add_reaction("🔀")

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
        if str(reaction.emoji) in ("👍", "🔀"):
            if str(reaction.emoji) == "🔀":
                logger.info("shuffling players")
                random.shuffle(players)
            else:
                players = [
                    player
                    for player in await reaction.users().flatten()
                    if player.id != bot.user.id
                ]
            red, blue = make_teams(players)
            logger.info(f"total players: {len(players)}")
            await message.edit(
                content=f"{base_message}\n🔴 Red: {format_team(red)}\n🔵 Blue: {format_team(blue)}"
            )


# -----------------------------------------------------------------------------

NUM_CATCHPHRASE_WORDS = 8

CATEGORIES_FORMATTED = ", ".join(catchphrase.CATEGORIES)


def catchphrase_impl(category: str = None):
    category = category.lower() if category else None
    if category == "categories":
        return {
            "content": f"{CATEGORIES_FORMATTED}\nEnter `{COMMAND_PREFIX}cp` or `{COMMAND_PREFIX}cp [category]` to generate a list of words/phrases."
        }

    if category and category not in catchphrase.CATEGORIES:
        logger.info(f"invalid category: {category}")
        suggestion = did_you_mean(category, catchphrase.CATEGORIES)
        if suggestion:
            return {
                "content": f'"{category}" is not a valid category. Did you mean "{suggestion}"?\nCategories: {CATEGORIES_FORMATTED}'
            }
        else:
            return {
                "content": f'"{category}" is not a valid category.\nCategories: {CATEGORIES_FORMATTED}'
            }
    words = "\n".join(
        f"||{catchphrase.catchphrase(category)}||" for _ in range(NUM_CATCHPHRASE_WORDS)
    )
    message = f"{words}\nEnter `{COMMAND_PREFIX}cp` or `{COMMAND_PREFIX}cp [category]` for more.\nCategories: {CATEGORIES_FORMATTED}"
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
    r"zoom\.us": ZOOM_CLOSED_MESSAGE,
    r"Could not create Zoom": ZOOM_CLOSED_MESSAGE,
    r"meet\.jit\.si": MEET_CLOSED_MESSAGE,
    r"Could not create watch2gether": WATCH2GETHER_CLOSED_MESSAGE,
    r"Watch videos together": WATCH2GETHER_CLOSED_MESSAGE,
    r"Speakeasy": SPEAKEASY_CLOSED_MESSAGE,
}


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if str(payload.emoji) == STOP_SIGN and payload.channel_id:
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


# -----------------------------------------------------------------------------

app = web.Application()


async def ping(request):
    return web.Response(body="", status=200)


app.add_routes([web.get("/ping", ping)])

# -----------------------------------------------------------------------------


async def start_bot():
    try:
        await bot.start(DISCORD_TOKEN)
    finally:
        await bot.close()


async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "", 5000)
    await site.start()


async def start():
    """Start the bot and the webserver."""
    asyncio.ensure_future(start_webserver())
    asyncio.ensure_future(start_bot())


if __name__ == "__main__":
    logger.info(f"starting bot version {__version__}")
    asyncio.ensure_future(start(), loop=bot.loop)
    bot.loop.run_forever()
