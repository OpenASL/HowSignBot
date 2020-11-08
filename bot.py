import asyncio
import datetime as dt
import difflib
import logging
import random
import re
from contextlib import suppress
from typing import Optional, NamedTuple, List, Tuple, Set, Dict, Sequence, Union
from urllib.parse import quote_plus, urlencode

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

__version__ = "20.77.0"

app = web.Application()  # web app for listening to webhooks

env = Env(eager=False)
env.read_env()

LOG_LEVEL = env.log_level("LOG_LEVEL", logging.INFO)
DISCORD_TOKEN = env.str("DISCORD_TOKEN", required=True)
OWNER_ID = env.int("OWNER_ID", required=True)
SECRET_KEY = env.str("SECRET_KEY", required=True)
COMMAND_PREFIX = env.str("COMMAND_PREFIX", "?")
PORT = env.int("PORT", 5000)

GOOGLE_PROJECT_ID = env.str("GOOGLE_PROJECT_ID", required=True)
GOOGLE_PRIVATE_KEY = env.str("GOOGLE_PRIVATE_KEY", required=True)
GOOGLE_PRIVATE_KEY_ID = env.str("GOOGLE_PRIVATE_KEY_ID", required=True)
GOOGLE_CLIENT_EMAIL = env.str("GOOGLE_CLIENT_EMAIL", required=True)
GOOGLE_TOKEN_URI = env.str("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token")
FEEDBACK_SHEET_KEY = env.str("FEEDBACK_SHEET_KEY", required=True)
SCHEDULE_SHEET_KEYS = env.dict("SCHEDULE_SHEET_KEYS", required=True, subcast_key=int)
SCHEDULE_CHANNELS = env.list("SCHEDULE_CHANNELS", required=True, subcast=int)

ZOOM_USERS = env.dict("ZOOM_USERS", required=True)
ZOOM_JWT = env.str("ZOOM_JWT", required=True)
ZOOM_HOOK_TOKEN = env.str("ZOOM_HOOK_TOKEN", required=True)

WATCH2GETHER_API_KEY = env.str("WATCH2GETHER_API_KEY", required=True)
# When to send practice schedules (in Eastern time)
DAILY_PRACTICE_SEND_TIME = env.time("DAILY_PRACTICE_SEND_TIME", "10:00")

env.seal()

STOP_SIGN = "🛑"

logging.basicConfig(level=LOG_LEVEL)

logger = logging.getLogger("bot")

intents = discord.Intents.default()
intents.typing = False
intents.presences = False
intents.bans = False
intents.integrations = False
intents.webhooks = False
intents.invites = False

bot = commands.Bot(
    command_prefix=COMMAND_PREFIX,
    case_insensitive=True,
    owner_id=OWNER_ID,
    intents=intents,
)

# -----------------------------------------------------------------------------


@bot.event
async def on_ready():
    await set_default_presence()
    daily_practice_message.start()


async def set_default_presence():
    activity = discord.Activity(
        name=f"{COMMAND_PREFIX}sign | {COMMAND_PREFIX}{COMMAND_PREFIX}",
        type=discord.ActivityType.watching,
    )
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
            embed.add_field(
                name=title, value=word_display(word, has_spoiler=bool(spoiler))
            )
    else:
        title = f"||{word.upper()}||" if spoiler else word.upper()
        embed = discord.Embed(
            title=title,
            description=word_display(word, has_spoiler=bool(spoiler)),
        )

    return {"embed": embed}


@bot.command(name="sign", aliases=("howsign", COMMAND_PREFIX), help=SIGN_HELP)
async def sign_command(ctx: Context, *, word: str):
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


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


PACIFIC = pytz.timezone("US/Pacific")
MOUNTAIN = pytz.timezone("US/Mountain")
CENTRAL = pytz.timezone("US/Central")
EASTERN = pytz.timezone("US/Eastern")

# EDT and PDT change to EST and PST during the winter
# Show the current name in docs
EASTERN_CURRENT_NAME = utcnow().astimezone(EASTERN).strftime("%Z")
PACIFIC_CURRENT_NAME = utcnow().astimezone(PACIFIC).strftime("%Z")

TIME_FORMAT = "%-I:%M %p %Z"
TIME_FORMAT_NO_MINUTES = "%-I %p %Z"


def parse_human_readable_datetime(
    dstr: str, settings: Optional[dict] = None
) -> Optional[dt.datetime]:
    parsed = dateparser.parse(dstr, settings=settings)
    if not parsed:
        return None
    # Use Pacific time if timezone can't be parsed; return a UTC datetime
    if not parsed.tzinfo:
        parsed = PACIFIC.localize(parsed)
    return parsed.astimezone(dt.timezone.utc)


class PracticeSession(NamedTuple):
    dtime: dt.datetime
    host: str
    notes: str


def get_practice_worksheet_for_guild(guild_id: int):
    logger.info(f"fetching practice worksheet {guild_id}")
    client = get_gsheet_client()
    sheet = client.open_by_key(SCHEDULE_SHEET_KEYS[guild_id])
    return sheet.get_worksheet(0)


def get_practice_sessions(
    guild_id: int,
    dtime: dt.datetime,
    *,
    worksheet=None,
    parse_settings: Optional[dict] = None,
) -> List[PracticeSession]:
    worksheet = worksheet or get_practice_worksheet_for_guild(guild_id)
    all_values = worksheet.get_all_values()
    return sorted(
        [
            PracticeSession(
                dtime=session_dtime,
                host=row[1],
                notes=row[2],
            )
            for row in all_values[2:]  # First two rows are documentation and headers
            if row
            and (
                session_dtime := parse_human_readable_datetime(
                    row[0], settings=parse_settings
                )
            )
            # Compare within Pacific timezone to include all of US
            and (
                session_dtime.astimezone(PACIFIC).date()
                == dtime.astimezone(PACIFIC).date()
            )
            # Filter out paused sessions
            and not bool(row[3])
        ],
        key=lambda s: s.dtime,
    )


def format_multi_time(dtime: dt.datetime) -> str:
    time_format = TIME_FORMAT if dtime.minute != 0 else TIME_FORMAT_NO_MINUTES
    pacific_dstr = dtime.astimezone(PACIFIC).strftime(time_format)
    mountain_dstr = dtime.astimezone(MOUNTAIN).strftime(time_format)
    central_dstr = dtime.astimezone(CENTRAL).strftime(time_format)
    eastern_dstr = dtime.astimezone(EASTERN).strftime(time_format)
    return " / ".join((pacific_dstr, mountain_dstr, central_dstr, eastern_dstr))


NO_PRACTICES = """

*There are no scheduled practices yet!*

To schedule a practice, edit the schedule below or use the `{COMMAND_PREFIX}practice` command.
Example: `{COMMAND_PREFIX}practice today 2pm {pacific}`
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX,
    pacific=PACIFIC_CURRENT_NAME.lower(),
)


def make_practice_session_embed(
    guild_id: int, sessions: List[PracticeSession], *, dtime: dt.datetime
) -> discord.Embed:
    now_pacific = utcnow().astimezone(PACIFIC)
    dtime_pacific = dtime.astimezone(PACIFIC)
    description = dtime_pacific.strftime("%A, %B %-d")
    if dtime_pacific.date() == now_pacific.date():
        description = f"Today - {description}"
    elif (dtime_pacific.date() - now_pacific.date()).days == 1:
        description = f"Tomorrow - {description}"
    sheet_key = SCHEDULE_SHEET_KEYS[guild_id]
    schedule_url = f"https://docs.google.com/spreadsheets/d/{sheet_key}/edit"
    embed = discord.Embed(
        description=description,
        color=discord.Color.orange(),
    )
    if not sessions:
        embed.description += NO_PRACTICES
    else:
        for session in sessions:
            title = format_multi_time(session.dtime)
            gcal_event_title = (
                f"ASL Practice: {session.notes}" if session.notes else "ASL Practice"
            )
            gcal_url = create_gcal_url(
                gcal_event_title,
                start=session.dtime,
                description=f"See the full schedule here: {schedule_url}",
            )
            value = f"[Add to Google Calendar]({gcal_url})"
            if session.host:
                value += f"\nHost: {session.host}"
            if session.notes:
                value += f"\nNotes: {session.notes}"
            embed.add_field(name=title, value=value, inline=False)
    embed.add_field(
        name="🗓",
        value=f"[Schedule or edit a practice]({schedule_url})",
    )
    return embed


def make_practice_sessions_today_embed(guild_id: int) -> discord.Embed:
    now = utcnow()
    sessions = get_practice_sessions(guild_id, dtime=now)
    return make_practice_session_embed(guild_id, sessions, dtime=now)


async def is_in_guild(ctx: Context) -> bool:
    return bool(ctx.guild)


SCHEDULE_HELP = """List the practice schedule for this server

Defaults to sending today's schedule.
Must be used within a server (not a DM).

Examples:
{COMMAND_PREFIX}schedule
{COMMAND_PREFIX}schedule tomorrow
{COMMAND_PREFIX}schedule friday
{COMMAND_PREFIX}schedule Sept 29
{COMMAND_PREFIX}schedule 10/3
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)


def schedule_impl(guild_id: int, when: Optional[str]):
    settings: Optional[Dict[str, str]]
    if when and when.strip().lower() != "today":
        settings = {"PREFER_DATES_FROM": "future"}
        dtime = parse_human_readable_datetime(when, settings=settings) or utcnow()
    else:
        settings = None
        dtime = utcnow()
    sessions = get_practice_sessions(guild_id, dtime=dtime, parse_settings=settings)
    embed = make_practice_session_embed(guild_id, sessions, dtime=dtime)
    return {"embed": embed}


@bot.command(
    name="schedule",
    aliases=("practices",),
    help=SCHEDULE_HELP,
)
@commands.check(is_in_guild)
async def schedule_command(ctx: Context, *, when: Optional[str]):
    await ctx.send(**schedule_impl(guild_id=ctx.guild.id, when=when))


PRACTICE_HELP = """Schedule a practice session

This will add an entry to the practice spreadsheet (use ?schedule to get the link).
Must be used within a server (not a DM).

Tips:

* Don't forget to include "am" or "pm".
* Don't forget to include a timezone, e.g. "{pacific}".
* If you don't include a date, today is assumed.
* You may optionally add notes within double quotes.

Examples:
{COMMAND_PREFIX}practice today 2pm {pacific}
{COMMAND_PREFIX}practice tomorrow 5pm {eastern} "chat for ~1 hour"
{COMMAND_PREFIX}practice saturday 6pm {pacific} "Game night 🎉"
{COMMAND_PREFIX}practice 9/24 6pm {eastern} "watch2gether session"
{COMMAND_PREFIX}practice "classifiers" at 6pm {pacific}
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX,
    pacific=PACIFIC_CURRENT_NAME.lower(),
    eastern=EASTERN_CURRENT_NAME.lower(),
)

PRACTICE_ERROR = """⚠️To schedule a practice, enter a time after `{COMMAND_PREFIX}practice`.
Example: `{COMMAND_PREFIX}practice today at 2pm {eastern}`
Enter `{COMMAND_PREFIX}schedule` to see today's schedule.
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX, eastern=EASTERN_CURRENT_NAME.lower()
)


def parse_practice_time(human_readable_datetime: str) -> Optional[dt.datetime]:
    # First try current_period to capture dates in the near future
    dtime = parse_human_readable_datetime(
        human_readable_datetime, settings={"PREFER_DATES_FROM": "current_period"}
    )
    # Can't parse into datetime, return early
    if dtime is None:
        return dtime
    # If date is in the past, prefer future dates
    if dtime < utcnow():
        dtime = parse_human_readable_datetime(
            human_readable_datetime, settings={"PREFER_DATES_FROM": "future"}
        )
    return dtime


def practice_impl(*, guild_id: int, host: str, start_time: str):
    if start_time.lower() in {
        # Common mistakes: don't try to parse these into a datetime
        "today",
        "tomorrow",
        "today edt",
        "today est",
        "today cdt",
        "today cst",
        "today mdt",
        "today mst",
        "today mdt",
        "today mst",
        "today pdt",
        "today pst",
    }:
        logger.info(f"practice invoked with {start_time}. sending error message")
        raise commands.errors.BadArgument(PRACTICE_ERROR)
    logger.info(f"attempting to schedule new practice session: {start_time}")
    human_readable_datetime, quoted = get_and_strip_quoted_text(start_time)
    dtime = parse_practice_time(human_readable_datetime)
    if not dtime:
        raise commands.errors.BadArgument(
            f'⚠️Could not parse "{start_time}" into a date or time. Make sure to include "am" or "pm" as well as a timezone, e.g. "{PACIFIC_CURRENT_NAME.lower()}".'
        )
    if dtime < utcnow():
        raise commands.errors.BadArgument(
            "⚠Parsed date or time is in the past. Try again with a future date or time."
        )
    notes = quoted or ""
    display_dtime = dtime.astimezone(PACIFIC).strftime("%A, %B %d %I:%M %p %Z %Y")
    row = (display_dtime, host, notes)
    logger.info(f"adding new practice session to sheet: {row}")
    worksheet = get_practice_worksheet_for_guild(guild_id)
    worksheet.append_row(row)
    dtime_pacific = dtime.astimezone(PACIFIC)
    short_display_date = f"{dtime_pacific:%a, %b %d} {format_multi_time(dtime)}"

    sessions = get_practice_sessions(guild_id=guild_id, dtime=dtime, worksheet=worksheet)
    embed = make_practice_session_embed(guild_id=guild_id, sessions=sessions, dtime=dtime)
    return {
        "content": f"🙌 New practice scheduled for *{short_display_date}*",
        "embed": embed,
    }


@bot.command(name="practice", help=PRACTICE_HELP)
@commands.check(is_in_guild)
async def practice_command(ctx: Context, *, start_time: str):
    host = getattr(ctx.author, "nick", None) or ctx.author.name
    message = await ctx.send(
        **practice_impl(guild_id=ctx.guild.id, host=host, start_time=start_time)
    )
    with suppress(Exception):
        await message.add_reaction("✅")


@practice_command.error
@schedule_command.error
async def practices_error(ctx, error):
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.send(
            f"`{COMMAND_PREFIX}{ctx.invoked_with}` must be run within a server (not a DM)."
        )
    elif isinstance(error, commands.errors.MissingRequiredArgument):
        await ctx.send(PRACTICE_ERROR)
    elif isinstance(error, commands.errors.CommandError):
        await ctx.send(error.args[0])
    else:
        logger.error(
            f"unexpected error when handling '{ctx.invoked_with}'", exc_info=error
        )


@tasks.loop(seconds=10.0)
async def daily_practice_message():
    # DAILY_PRACTICE_SEND_TIME is defined in Eastern time
    now_eastern = dt.datetime.now(EASTERN)
    date = now_eastern.date()
    if now_eastern.time() > DAILY_PRACTICE_SEND_TIME:
        date = now_eastern.date() + dt.timedelta(days=1)
    then = EASTERN.localize(dt.datetime.combine(date, DAILY_PRACTICE_SEND_TIME))
    logger.info(
        f"practice schedules for {len(SCHEDULE_CHANNELS)} channels will be sent at {then.isoformat()}"
    )
    await discord.utils.sleep_until(then.astimezone(dt.timezone.utc))
    for channel_id in SCHEDULE_CHANNELS:
        try:
            channel = bot.get_channel(channel_id)
            guild = channel.guild
            logger.info(
                f'sending daily practice schedule for guild: "{guild.name}" in #{channel.name}'
            )
            asyncio.create_task(
                channel.send(embed=make_practice_sessions_today_embed(guild.id))
            )
        except Exception:
            logger.exception(f"could not send to channel {channel_id}")


@bot.command(
    name="send_schedule",
    help="BOT OWNER ONLY: Manually send daily practice schedule for a guild",
)
@commands.is_owner()
async def send_schedule_command(ctx: Context, channel_id: int):
    if channel_id not in SCHEDULE_CHANNELS:
        await ctx.send(f"⚠️ Schedule channel not configured for Channel ID {channel_id}")
    channel = bot.get_channel(channel_id)
    guild = channel.guild
    await channel.send(embed=make_practice_sessions_today_embed(guild.id))
    await ctx.send(f'🗓 Schedule sent to "{guild.name}", #{channel.name}')


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


class ZoomMeetingState(NamedTuple):
    channel_ids: Tuple[int]
    message_ids: Tuple[int]
    participant_ids: Set[str]
    meeting: meetings.ZoomMeeting


def make_zoom_embed(
    meeting: meetings.ZoomMeeting, num_participants: int
) -> discord.Embed:
    title = f"<{meeting.join_url}>"
    description = f"**Meeting ID:**: {meeting.id}\n**Passcode**: {meeting.passcode}"
    if meeting.topic:
        description = f"{description}\n**Topic**: {meeting.topic}"

    if num_participants:
        description += "\n" + "👤" * num_participants
    else:
        description += "\n"

    description += "\n🚀 This meeting is happening now. Go practice!\n*This message will be cleared when the meeting ends.*"
    return discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blue(),
    )


def is_allowed_zoom_access(ctx):
    if str(ctx.author) not in ZOOM_USERS:
        raise commands.errors.CheckFailure(
            f"⚠️ `{COMMAND_PREFIX}{ctx.invoked_with}` can only be used by authorized users under the bot owner's Zoom account."
        )
    return True


@bot.command(name="zoom", help="AUTHORIZED USERS ONLY: Create a Zoom meeting")
@commands.check(is_allowed_zoom_access)
async def zoom_command(ctx: Context, meeting_id: Optional[int] = None):
    zoom_user = ZOOM_USERS[str(ctx.author)]
    logger.info(f"creating zoom meeting for zoom user: {zoom_user}")
    if meeting_id in app["zoom_meeting_messages"]:
        state = app["zoom_meeting_messages"][meeting_id]
        message = await ctx.send(
            embed=make_zoom_embed(
                state.meeting, num_participants=len(state.participant_ids)
            )
        )
        logger.info(f"updating meeting state for meeting id {meeting_id}")
        next_state = ZoomMeetingState(
            channel_ids=state.channel_ids + (ctx.channel.id,),
            message_ids=state.message_ids + (message.id,),
            participant_ids=state.participant_ids,
            meeting=state.meeting,
        )
        app["zoom_meeting_messages"][meeting_id] = next_state
    else:
        try:
            meeting = await meetings.create_zoom(
                token=ZOOM_JWT,
                user_id=zoom_user,
                topic="",
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
            return
        else:
            message = await ctx.send(embed=make_zoom_embed(meeting, num_participants=0))
            meeting_state = ZoomMeetingState(
                channel_ids=(ctx.channel.id,),
                message_ids=(message.id,),
                participant_ids=set(),
                meeting=meeting,
            )
            app["zoom_meeting_messages"][meeting.id] = meeting_state
            logger.info(f"setting info for meeting {meeting.id}")

    await wait_for_stop_sign(
        message, add_reaction=False, replace_with=ZOOM_CLOSED_MESSAGE
    )

    with suppress(KeyError):
        del app["zoom_meeting_messages"][meeting.id]


@zoom_command.error
async def zoom_error(ctx, error):
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.send(error.args[0])
    else:
        logger.error(
            f"unexpected error when handling '{ctx.invoked_with}'", exc_info=error
        )


# -----------------------------------------------------------------------------

MEET_CLOSED_MESSAGE = "✨ _Jitsi Meet ended_"


def make_jitsi_embed(meeting: meetings.JitsiMeet):
    title = f"<{meeting.join_url}>"
    content = (
        f"**Join URL**: <{meeting.join_url}>\n**Desktop App Link***: <{meeting.deeplink}>"
    )
    if meeting.name:
        content = f"{content}\n**Name**: {meeting.name}"
    content = f"{content}\n\n🚀 This meeting is happening now. Go practice!\n*Desktop App Link requires <https://github.com/jitsi/jitsi-meet-electron>\n*After the meeting ends, click {STOP_SIGN} to remove this message.*"
    logger.info("sending jitsi meet info")
    return discord.Embed(
        title=title,
        description=content,
        color=discord.Color.blue(),
    )


@bot.command(name="meet", aliases=("jitsi",), help="Start a Jitsi Meet meeting")
async def meet_command(ctx: Context, *, name: Optional[str]):
    meeting = meetings.create_jitsi_meet(name, secret=SECRET_KEY)
    logger.info("sending jitsi meet info")
    message = await ctx.send(embed=make_jitsi_embed(meeting))

    await wait_for_stop_sign(message, replace_with=MEET_CLOSED_MESSAGE)


# -----------------------------------------------------------------------------

SPEAKEASY_CLOSED_MESSAGE = "✨ _Speakeasy event ended_"


@bot.command(name="speakeasy", help="Start a Speakeasy (https://speakeasy.co/) event")
async def speakeasy_command(ctx: Context, *, name: Optional[str]):
    join_url = meetings.create_speakeasy(name, secret=SECRET_KEY)
    content = f"️🍻 **Speakeasy**\nJoin URL: <{join_url}>"
    if name:
        content = f"{content}\n**Name**: {name}"
    content = f"{content}\n🚀 This event is happening now. Make a friend!"
    logger.info("sending speakeasy info")
    message = await ctx.send(content=content)

    await wait_for_stop_sign(
        message, add_reaction=False, replace_with=SPEAKEASY_CLOSED_MESSAGE
    )


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


@bot.command(name="w2g", aliases=("wtg", "watch2gether"), help=WATCH2GETHER_HELP)
async def watch2gether_command(ctx: Context, video_url: Optional[str] = None):
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


def format_team(players: Sequence[Union[discord.User, discord.Member]]):
    names = [getattr(each, "nick", None) or each.name for each in players]
    return ", ".join(names)


@bot.command(name="codenames", aliases=("cn",), help="Start a Codenames game")
async def codenames_command(ctx: Context, name: Optional[str] = None):
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

    players: List[Union[discord.User, discord.Member]] = []
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


def catchphrase_impl(category: Optional[str] = None):
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
async def catchphrase_command(ctx: Context, category: Optional[str] = None):
    await ctx.send(**catchphrase_impl(category))


# -----------------------------------------------------------------------------


def ActivityTypeConverter(argument) -> discord.ActivityType:
    if argument not in discord.ActivityType._enum_member_names_:
        raise commands.CommandError(f'⚠️"{argument}" is not a valid activity type.')
    return getattr(discord.ActivityType, argument)


@bot.command(name="presence", help="BOT OWNER ONLY: Change bot presense")
@commands.is_owner()
async def presence_command(ctx: Context, activity_type: Optional[ActivityTypeConverter] = None, name: str = ""):  # type: ignore[valid-type]
    if not activity_type:
        await set_default_presence()
        await ctx.send("Presence reset.")
        return
    activity = discord.Activity(
        name=name.format(p=COMMAND_PREFIX),
        type=activity_type,
    )
    logger.info(f"changing presence to {activity}")
    await bot.change_presence(activity=activity)
    await ctx.send(f"Changed presence to: `{activity}`")


@presence_command.error
async def presence_command_error(ctx, error):
    message = error.args[0]
    await ctx.send(content=message)


# Used for getting channel IDs for SCHEDULE_CHANNELS

CHANNEL_INFO_TEMPLATE = """Guild name: {ctx.guild.name}
Guild ID: {ctx.guild.id}
Channel name: {ctx.channel.name}
Channel ID: {ctx.channel.id}
"""


@bot.command(name="channelinfo")
@commands.is_owner()
async def channelinfo_command(ctx: Context):
    await ctx.author.send(
        embed=discord.Embed(
            title="Channel Information", description=CHANNEL_INFO_TEMPLATE.format(ctx=ctx)
        )
    )
    await ctx.send("ℹ️ _Channel info sent in DM_", delete_after=5)


# -----------------------------------------------------------------------------

HOMEPAGE_URL = "https://howsign.sloria.io"


@bot.command(name="invite", help="Invite HowSignBot to another Discord server")
async def invite_command(ctx: Context):
    await ctx.send(f"Add HowSignBot to another server here: {HOMEPAGE_URL}")


DONATE_URL = "https://liberapay.com/HowSignBot"


@bot.command(name="donate", help="Get the donation URL for HowSignBot")
async def donate_command(ctx: Context):
    await ctx.send(
        f"🙌 If you find HowSignBot useful, consider supporting the project with a donation: {DONATE_URL}"
    )


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
            if message.embeds:
                for embed in message.embeds:
                    if re.search(pattern, embed.title):
                        logger.info(f"cleaning up room with message: {close_message}")
                        await message.edit(content=close_message, embed=None)
                        return
            if re.search(pattern, message.content):
                logger.info(f"cleaning up room with message: {close_message}")
                await message.edit(content=close_message, embed=None)
                return


# -----------------------------------------------------------------------------


def empty_response():
    return web.Response(body="", status=200)


async def ping(request):
    return empty_response()


SUPPORTED_EVENTS = {
    "meeting.participant_joined",
    "meeting.participant_left",
    "meeting.ended",
}


async def handle_zoom_event(data: dict):
    event = data["event"]
    if event not in SUPPORTED_EVENTS:
        return
    meeting_id = int(data["payload"]["object"]["id"])
    try:
        state: ZoomMeetingState = app["zoom_meeting_messages"][meeting_id]
    except KeyError:
        return
    logging.info(f"handling zoom event {event} for meeting {meeting_id}")
    for channel_id, message_id in zip(state.channel_ids, state.message_ids):
        channel = bot.get_channel(channel_id)
        message = await channel.fetch_message(message_id)
        if event == "meeting.ended":
            logger.info(
                f"automatically ending meeting {meeting_id}, message {message_id}"
            )
            edit_kwargs = {"content": "✨ _Zoom meeting ended by host_", "embed": None}
        elif event == "meeting.participant_joined":
            participant_id = data["payload"]["object"]["participant"]["user_id"]
            next_state = ZoomMeetingState(
                channel_ids=state.channel_ids,
                message_ids=state.message_ids,
                participant_ids=state.participant_ids | {participant_id},
                meeting=state.meeting,
            )
            logger.info(
                f"adding new participant for meeting id {meeting_id}, message {message_id}"
            )
            app["zoom_meeting_messages"][meeting_id] = next_state
            embed = make_zoom_embed(
                next_state.meeting, num_participants=len(next_state.participant_ids)
            )
            edit_kwargs = {"embed": embed}
        elif event == "meeting.participant_left":
            participant_id = data["payload"]["object"]["participant"]["user_id"]
            next_state = ZoomMeetingState(
                channel_ids=state.channel_ids,
                message_ids=state.message_ids,
                participant_ids=state.participant_ids - {participant_id},
                meeting=state.meeting,
            )
            logger.info(
                f"removing participant for meeting id {meeting_id}, message {message_id}"
            )
            app["zoom_meeting_messages"][meeting_id] = next_state
            embed = make_zoom_embed(
                next_state.meeting, num_participants=len(next_state.participant_ids)
            )
            edit_kwargs = {"embed": embed}
        await message.edit(**edit_kwargs)

    if event == "meeting.ended":
        del app["zoom_meeting_messages"][meeting_id]


async def zoom(request):
    if request.headers["authorization"] != ZOOM_HOOK_TOKEN:
        return web.Response(body="", status=403)
    data = await request.json()
    # Zoom expects responses within 3 seconds, so run the handler logic asynchronously
    #   https://marketplace.zoom.us/docs/api-reference/webhook-reference#notification-delivery
    asyncio.create_task(handle_zoom_event(data))
    return empty_response()


app.add_routes([web.get("/ping", ping), web.post("/zoom", zoom)])


async def start_bot():
    try:
        await bot.start(DISCORD_TOKEN)
    finally:
        await bot.close()


async def on_startup(app):
    app["bot_task"] = asyncio.create_task(start_bot())
    app["bot"] = bot
    # Mapping of Zoom meeting IDs to a tuple of the form (channel_id, message_id, participant_count)
    app["zoom_meeting_messages"] = {}


async def on_shutdown(app):
    app["bot_task"].cancel()
    await app["bot_task"]


app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

# -----------------------------------------------------------------------------

_spoiler_pattern = re.compile(r"\s*\|\|\s*(.*)\s*\|\|\s*")
_quotes_pattern = re.compile(r"[\"“](.*?)[\"”]")


def get_spoiler_text(val: str) -> Optional[str]:
    """Return value within spoiler text if it exists, else return `None`."""
    match = _spoiler_pattern.match(val)
    if match:
        return match.groups()[0]
    return None


def get_and_strip_quoted_text(val: str) -> Tuple[str, Optional[str]]:
    """Return `val` with quoted text removed as well as as the quoted text."""
    match = _quotes_pattern.search(val)
    if match:
        stripped = _quotes_pattern.sub("", val).strip()
        quoted = match.groups()[0]
        return stripped, quoted
    return val, None


def did_you_mean(word, possibilities):
    try:
        return difflib.get_close_matches(word, possibilities, n=1, cutoff=0.5)[0]
    except IndexError:
        return None


def create_gcal_url(
    text,
    start: dt.datetime,
    end: Optional[dt.datetime] = None,
    description: Optional[str] = None,
):
    dt_format = "%Y%m%dT%H%M%SZ"
    base_url = "http://www.google.com/calendar/event"
    end = end or start + dt.timedelta(hours=1)
    params = {
        "action": "TEMPLATE",
        "text": text,
        "dates": "{}/{}".format(start.strftime(dt_format), end.strftime(dt_format)),
    }
    if description:
        params["details"] = description
    return "?".join((base_url, urlencode(params)))


async def wait_for_stop_sign(
    message: discord.Message, *, add_reaction: bool = True, replace_with: str
):
    if add_reaction:
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
    await message.edit(content=replace_with, embed=None)


# -----------------------------------------------------------------------------


if __name__ == "__main__":
    logger.info(f"starting bot version {__version__}")
    web.run_app(app, port=PORT)
