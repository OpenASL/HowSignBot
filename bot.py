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
import holiday_emojis
import cuteid
import catchphrase
import meetings
import pytz_informal
import database
import clthat

# -----------------------------------------------------------------------------

__version__ = "20.88.0"

app = web.Application()  # web app for listening to webhooks

env = Env(eager=False)
env.read_env()

DATABASE_URL = database.DatabaseURL(env.str("DATABASE_URL", required=True))
TEST_DATABASE_URL = DATABASE_URL.replace(database="test_" + DATABASE_URL.database)
TESTING = env.bool("TESTING", cast=bool, default=False)
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
TOPICS_SHEET_KEY = env.str("TOPICS_SHEET_KEY", required=True)
FEEDBACK_SHEET_KEY = env.str("FEEDBACK_SHEET_KEY", required=True)

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

store = database.Store(
    database_url=TEST_DATABASE_URL if TESTING else DATABASE_URL, force_rollback=TESTING
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


def word_display(word: str, *, template: str = SIGN_TEMPLATE):
    quoted_word = quote_plus(word)
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
    template = SIGN_SPOILER_TEMPLATE if spoiler else SIGN_TEMPLATE
    if has_multiple:
        words = word.split(",")
        embed = discord.Embed()
        for word in words:
            word = word.strip()
            title = f"||{word.upper()}||" if spoiler else word.upper()
            embed.add_field(name=title, value=word_display(word, template=template))
    else:
        title = f"||{word.upper()}||" if spoiler else word.upper()
        embed = discord.Embed(
            title=title,
            description=word_display(word, template=template),
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
    try:
        if name == "random":
            handshape = handshapes.get_random_handshape()
        else:
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

CLTHAT_HELP = """Show a text or GIF prompt for classifier practice

Examples:
{COMMAND_PREFIX}clthat
{COMMAND_PREFIX}clthat gif
{COMMAND_PREFIX}clthat text
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)


def clthat_impl(kind: str):
    kind = kind.lower()
    logger.info(f"sending classifier practice, kind: {kind}")
    if kind not in {"any", "text", "gif"}:
        return {"content": "⚠️ `kind` must be one of: any, text, gif"}

    content = "_CL That!_\n"
    if kind == "any":
        content += clthat.random()
    elif kind == "text":
        content += clthat.text()
    else:
        content += clthat.gif_url()
    return {"content": content}


@bot.command(name="clthat", aliases=("cl",), help=HANDSHAPE_HELP)
async def clthat_command(ctx, kind="any"):
    await ctx.send(**clthat_impl(kind))


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


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


PACIFIC = pytz.timezone("America/Los_Angeles")
MOUNTAIN = pytz.timezone("America/Denver")
CENTRAL = pytz.timezone("America/Chicago")
EASTERN = pytz.timezone("America/New_York")

# EDT and PDT change to EST and PST during the winter
# Show the current name in docs
EASTERN_CURRENT_NAME = utcnow().astimezone(EASTERN).strftime("%Z")
PACIFIC_CURRENT_NAME = utcnow().astimezone(PACIFIC).strftime("%Z")

# Timezone is omitted because it is computed using tzinfo.tzname
TIME_FORMAT = "%-I:%M %p "
TIME_FORMAT_NO_MINUTES = "%-I %p "


def normalize_timezone(dtime: dt.datetime) -> dt.datetime:
    """Normalizes informal N. American timezones ("EST", "PST") to
    the IANA timezones ("America/Los_Angeles", "America/New_York")
    """
    tzinfo = dtime.tzinfo
    assert tzinfo is not None
    naive = dtime.replace(tzinfo=None)
    tzname = tzinfo.tzname(naive)
    assert tzname is not None
    tzone = pytz_informal.timezone(tzname)
    return tzone.localize(naive)


class NoTimeZoneError(ValueError):
    pass


def parse_human_readable_datetime(
    dstr: str,
    settings: Optional[dict] = None,
    user_timezone: Optional[pytz.BaseTzInfo] = None,
    # By default, use Pacific time if timezone can't be parsed
    fallback_timezone: Optional[pytz.BaseTzInfo] = PACIFIC,
) -> Tuple[Optional[dt.datetime], Optional[pytz.BaseTzInfo]]:
    parsed = dateparser.parse(dstr, settings=settings)
    if parsed is None:
        return None, None
    if not parsed.tzinfo:
        if user_timezone is not None:
            parsed = user_timezone.localize(parsed)
        else:
            if not fallback_timezone:
                raise NoTimeZoneError(f"Time zone could not be parsed from {dstr}.")
            parsed = fallback_timezone.localize(parsed)
    parsed = normalize_timezone(parsed)
    used_timezone = parsed.tzinfo
    return parsed.astimezone(dt.timezone.utc), used_timezone


class PracticeSession(NamedTuple):
    dtime: dt.datetime
    host: str
    notes: str


async def get_practice_worksheet_for_guild(guild_id: int):
    logger.info(f"fetching practice worksheet {guild_id}")
    client = get_gsheet_client()
    sheet_key = await store.get_guild_schedule_sheet_key(guild_id)
    assert sheet_key is not None
    sheet = client.open_by_key(sheet_key)
    return sheet.get_worksheet(0)


async def get_practice_sessions(
    guild_id: int,
    dtime: dt.datetime,
    *,
    worksheet=None,
    parse_settings: Optional[dict] = None,
) -> List[PracticeSession]:
    worksheet = worksheet or await get_practice_worksheet_for_guild(guild_id)
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
                )[0]
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


def display_timezone(tzinfo: dt.tzinfo, dtime: dt.datetime) -> str:
    ret = tzinfo.tzname(dtime.replace(tzinfo=None))
    assert ret is not None
    return ret


def display_time(dtime: dt.datetime, time_format: str, tzinfo: pytz.BaseTzInfo) -> str:
    return dtime.astimezone(tzinfo).strftime(time_format) + display_timezone(
        tzinfo, dtime
    )


def format_multi_time(dtime: dt.datetime) -> str:
    time_format = TIME_FORMAT if dtime.minute != 0 else TIME_FORMAT_NO_MINUTES
    pacific_dstr = display_time(dtime, time_format, tzinfo=PACIFIC)
    mountain_dstr = display_time(dtime, time_format, tzinfo=MOUNTAIN)
    central_dstr = display_time(dtime, time_format, tzinfo=CENTRAL)
    eastern_dstr = display_time(dtime, time_format, tzinfo=EASTERN)
    return " / ".join((pacific_dstr, mountain_dstr, central_dstr, eastern_dstr))


NO_PRACTICES = """

*There are no scheduled practices yet!*

To schedule a practice, edit the schedule below or use the `{COMMAND_PREFIX}practice` command.
Example: `{COMMAND_PREFIX}practice today 2pm {pacific}`
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX,
    pacific=PACIFIC_CURRENT_NAME.lower(),
)


async def make_practice_session_embed(
    guild_id: int, sessions: List[PracticeSession], *, dtime: dt.datetime
) -> discord.Embed:
    now_pacific = utcnow().astimezone(PACIFIC)
    dtime_pacific = dtime.astimezone(PACIFIC)
    description = dtime_pacific.strftime("%A, %B %-d")
    if dtime_pacific.date() == now_pacific.date():
        description = f"Today - {description}"
    elif (dtime_pacific.date() - now_pacific.date()).days == 1:
        description = f"Tomorrow - {description}"
    holiday = holiday_emojis.get(dtime_pacific.date())
    if holiday and holiday.emoji:
        description += f" {holiday.emoji}"
    sheet_key = await store.get_guild_schedule_sheet_key(guild_id)
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


async def make_practice_sessions_today_embed(guild_id: int) -> discord.Embed:
    now = utcnow()
    sessions = await get_practice_sessions(guild_id, dtime=now)
    return await make_practice_session_embed(guild_id, sessions, dtime=now)


async def is_in_guild(ctx: Context) -> bool:
    if not bool(ctx.guild):
        raise commands.errors.CheckFailure(
            f"⚠️ `{COMMAND_PREFIX}{ctx.invoked_with}` must be run within a server (not a DM)."
        )
    return True


async def has_practice_schedule(ctx: Context) -> bool:
    await is_in_guild(ctx)
    has_practice_schedule = await store.guild_has_practice_schedule(ctx.guild.id)
    if not has_practice_schedule:
        raise commands.errors.CheckFailure(
            "⚠️ No configured practice schedule for this server. If you think this is a mistake, contact the bot owner."
        )
    return True


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


async def schedule_impl(guild_id: int, when: Optional[str]):
    settings: Optional[Dict[str, str]]
    if when and when.strip().lower() != "today":
        settings = {"PREFER_DATES_FROM": "future"}
        dtime, _ = parse_human_readable_datetime(when, settings=settings) or utcnow()
        dtime = dtime or utcnow()
    else:
        settings = None
        dtime = utcnow()
    sessions = await get_practice_sessions(guild_id, dtime=dtime, parse_settings=settings)
    embed = await make_practice_session_embed(guild_id, sessions, dtime=dtime)
    return {"embed": embed}


@bot.command(name="schedule", aliases=("sched", "practices"), help=SCHEDULE_HELP)
@commands.check(has_practice_schedule)
async def schedule_command(ctx: Context, *, when: Optional[str]):
    await ctx.channel.trigger_typing()
    ret = await schedule_impl(guild_id=ctx.guild.id, when=when)
    await ctx.send(**ret)


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


def parse_practice_time(
    human_readable_datetime: str, user_timezone: Optional[pytz.BaseTzInfo] = None
) -> Tuple[Optional[dt.datetime], Optional[pytz.BaseTzInfo]]:
    # First try current_period to capture dates in the near future
    dtime, used_timezone = parse_human_readable_datetime(
        human_readable_datetime,
        settings={"PREFER_DATES_FROM": "current_period"},
        user_timezone=user_timezone,
        fallback_timezone=None,  # Error if time zone can't be parsed
    )
    # Can't parse into datetime, return early
    if dtime is None:
        return None, None
    # If date is in the past, prefer future dates
    if dtime < utcnow():
        dtime, used_timezone = parse_human_readable_datetime(
            human_readable_datetime,
            settings={"PREFER_DATES_FROM": "future"},
            user_timezone=user_timezone,
            fallback_timezone=None,  # Error if time zone can't be parsed
        )
    return dtime, used_timezone


async def practice_impl(*, guild_id: int, host: str, start_time: str, user_id: int):
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
    user_timezone = await store.get_user_timezone(user_id=user_id)
    try:
        dtime, used_timezone = parse_practice_time(
            human_readable_datetime, user_timezone=user_timezone
        )
    except NoTimeZoneError:
        raise commands.errors.BadArgument(
            f'⚠️Could not parse time zone from "{start_time}". Make sure to include a time zone, e.g. "{PACIFIC_CURRENT_NAME.lower()}".'
        )
    if not dtime:
        raise commands.errors.BadArgument(
            f'⚠️Could not parse "{start_time}" into a date or time. Make sure to include "am" or "pm" as well as a timezone, e.g. "{PACIFIC_CURRENT_NAME.lower()}".'
        )
    assert used_timezone is not None
    if dtime < utcnow():
        raise commands.errors.BadArgument(
            "⚠Parsed date or time is in the past. Try again with a future date or time."
        )
    notes = quoted or ""
    dtime_local = dtime.astimezone(used_timezone)
    display_dtime = " ".join(
        (
            dtime_local.strftime("%A, %B %d %I:%M %p"),
            display_timezone(used_timezone, dtime),
            dtime_local.strftime("%Y"),
        )
    )
    row = (display_dtime, host, notes)
    logger.info(f"adding new practice session to sheet: {row}")
    worksheet = await get_practice_worksheet_for_guild(guild_id)
    worksheet.append_row(row)
    dtime_pacific = dtime.astimezone(PACIFIC)
    short_display_date = f"{dtime_pacific:%a, %b %d} {format_multi_time(dtime)}"
    sessions = await get_practice_sessions(
        guild_id=guild_id, dtime=dtime, worksheet=worksheet
    )
    embed = await make_practice_session_embed(
        guild_id=guild_id, sessions=sessions, dtime=dtime
    )
    if str(used_timezone) != str(user_timezone):
        await store.set_user_timezone(user_id, used_timezone)
    return {
        "content": f"🙌 New practice scheduled for *{short_display_date}*",
        "embed": embed,
        # Return old and new timezone to send notification to user if they're different
        "old_timezone": user_timezone,
        "new_timezone": used_timezone,
    }


TIMEZONE_CHANGE_TEMPLATE = """🙌 Thanks for scheduling a practice! I'll remember your time zone (**{new_timezone}**) so you don't need to include a time zone when scheduling future practices.
Before: `{COMMAND_PREFIX}practice tomorrow 8pm {new_timezone_display}`
After: `{COMMAND_PREFIX}practice tomorrow 8pm`
To change your time zone, just schedule another practice with a different time zone.
"""


@bot.command(name="practice", help=PRACTICE_HELP)
async def practice_command(ctx: Context, *, start_time: str):
    await ctx.channel.trigger_typing()

    is_dm = not bool(ctx.guild)
    if is_dm:
        guild_ids_with_schedules = await store.get_guild_ids_with_practice_schedules()
        guild_ids = []
        for guild_id in guild_ids_with_schedules:
            guild = bot.get_guild(guild_id)
            # Use fetch_member to check membership instead of get_member because cache might not be populated
            try:
                await guild.fetch_member(ctx.author.id)
            except Exception:
                pass
            else:
                guild_ids.append(guild_id)
    else:
        has_practice_schedule = await store.guild_has_practice_schedule(ctx.guild.id)
        if not has_practice_schedule:
            raise commands.errors.CheckFailure(
                "⚠️ No configured practice schedule for this server. If you think this is a mistake, contact the bot owner."
            )
        guild_ids = [ctx.guild.id]
    host = getattr(ctx.author, "nick", None) or ctx.author.name

    dm_response = None
    old_timezone, new_timezone = None, None
    for guild_id in guild_ids:
        ret = await practice_impl(
            guild_id=guild_id,
            host=host,
            start_time=start_time,
            user_id=ctx.author.id,
        )
        old_timezone = ret.pop("old_timezone")
        new_timezone = ret.pop("new_timezone")
        channel_id = await store.get_guild_daily_message_channel_id(guild_id)
        channel = bot.get_channel(channel_id)
        message = await channel.send(**ret)
        with suppress(Exception):
            await message.add_reaction("✅")
    if is_dm:
        if guild_ids:
            dm_response = "🙌 Thanks for scheduling a practice in the following servers:\n"
            for guild_id in guild_ids:
                guild = bot.get_guild(guild_id)
                dm_response += f"*{guild.name}*\n"
        else:
            dm_response = (
                "⚠️ You are not a member of any servers that have a practice schedule."
            )
    else:
        if str(old_timezone) != str(new_timezone):
            assert new_timezone is not None
            new_timezone_display = display_timezone(new_timezone, utcnow()).lower()
            dm_response = TIMEZONE_CHANGE_TEMPLATE.format(
                new_timezone=new_timezone,
                new_timezone_display=new_timezone_display,
                COMMAND_PREFIX=COMMAND_PREFIX,
            )
    if dm_response:
        try:
            await ctx.author.send(dm_response)
        except discord.errors.Forbidden:
            logger.warn("cannot send DM to user. skipping...")


@practice_command.error
@schedule_command.error
async def practices_error(ctx, error):
    if isinstance(error, (commands.errors.CheckFailure, commands.errors.BadArgument)):
        await ctx.send(error.args[0])
    elif isinstance(error, commands.errors.MissingRequiredArgument):
        await ctx.send(PRACTICE_ERROR)
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
    channel_ids = list(await store.get_daily_message_channel_ids())
    logger.info(
        f"practice schedules for {len(channel_ids)} channels will be sent at {then.isoformat()}"
    )
    await discord.utils.sleep_until(then.astimezone(dt.timezone.utc))
    for channel_id in channel_ids:
        try:
            asyncio.create_task(send_daily_message(channel_id))
        except Exception:
            logger.exception(f"could not send to channel {channel_id}")


def get_today_random(dtime: Optional[dt.datetime] = None) -> random.Random:
    dtime = dtime or utcnow()
    return random.Random(dtime.date().isoformat())


def get_daily_handshape(dtime: Optional[dt.datetime] = None) -> handshapes.Handshape:
    return handshapes.get_random_handshape(get_today_random(dtime))


def get_daily_topics(dtime: Optional[dt.datetime] = None) -> Tuple[str, str]:
    client = get_gsheet_client()
    sheet = client.open_by_key(TOPICS_SHEET_KEY)
    worksheet = sheet.get_worksheet(0)
    rows = worksheet.get_all_records()

    rand = get_today_random(dtime)

    return (rand.choice(rows)["content"], rand.choice(rows)["content"])


def get_daily_clthat(dtime: Optional[dt.datetime] = None) -> handshapes.Handshape:
    return clthat.text(get_today_random(dtime))


TOPIC_DAYS = {0, 2, 4, 6}  # M W F Su
CLTHAT_DAYS = {1, 3, 5}  # Tu Th Sa


async def send_daily_message(channel_id: int, dtime: Optional[dt.datetime] = None):
    channel = bot.get_channel(channel_id)
    guild = channel.guild
    logger.info(f'sending daily message for guild: "{guild.name}" in #{channel.name}')
    guild_id = guild.id
    dtime = dtime or utcnow()
    sessions = await get_practice_sessions(guild_id, dtime=dtime)
    embed = await make_practice_session_embed(guild_id, sessions, dtime=dtime)
    file_ = None

    settings = await store.get_guild_settings(guild.id)

    holiday = holiday_emojis.get(dtime.date())
    if holiday and holiday.term is not None:
        embed.add_field(
            name=holiday.term.upper(),
            value=word_display(holiday.term),
            inline=False,
        )
    elif settings.get("include_handshape_of_the_day"):
        # Handshape of the Day
        handshape = get_daily_handshape(dtime)
        filename = f"{handshape.name}.png"
        file_ = discord.File(handshape.path, filename=filename)
        embed.set_thumbnail(url=f"attachment://{filename}")
        embed.add_field(
            name="Handshape of the Day", value=f'"{handshape.name}"', inline=False
        )

    if not holiday:
        # Topics of the Day
        weekday = dtime.weekday()
        if settings.get("include_topics_of_the_day") and weekday in TOPIC_DAYS:
            topic, topic2 = get_daily_topics(dtime)
            embed.add_field(
                name="Discuss...", value=f'"{topic}"\n\n"{topic2}"', inline=False
            )

        # CL That
        if settings.get("include_clthat") and weekday in CLTHAT_DAYS:
            embed.add_field(
                name="CL That!",
                value=f'How would you sign: "{get_daily_clthat(dtime)}"',
                inline=False,
            )

    await channel.send(file=file_, embed=embed)


@bot.command(
    name="send_daily_message",
    help="BOT OWNER ONLY: Manually send a daily practice schedule for a channel",
)
@commands.is_owner()
async def send_daily_message_command(
    ctx: Context, channel_id: int, when: Optional[str] = None
):
    await ctx.channel.trigger_typing()
    channel_ids = set(await store.get_daily_message_channel_ids())
    if channel_id not in channel_ids:
        await ctx.send(f"⚠️ Schedule channel not configured for Channel ID {channel_id}")
        return
    dtime = (
        parse_human_readable_datetime(
            when, settings={"PREFER_DATES_FROM": "future"}, user_timezone=EASTERN
        )[0]
        if when
        else utcnow().astimezone(EASTERN)
    )
    assert dtime is not None
    send_dtime = EASTERN.localize(dt.datetime.combine(dtime, DAILY_PRACTICE_SEND_TIME))
    await send_daily_message(channel_id, send_dtime)

    channel = bot.get_channel(channel_id)
    guild = channel.guild
    await ctx.send(f'🗓 Daily message sent to "{guild.name}", #{channel.name}')


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
    await ctx.channel.trigger_typing()
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

WATCH2GETHER_CLOSED_MESSAGE = "✨ _watch2gether room closed_"


def make_watch2gether_embed(url: str, video_url: Optional[str]) -> discord.Embed:
    description = "🚀 Watch videos together!"
    if video_url:
        description += f"\nQueued video: <{video_url}>"
    description += "\n*When finished, click 🛑 to remove this message.*"
    return discord.Embed(title=url, description=description, color=discord.Color.gold())


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
        message = await ctx.send(embed=make_watch2gether_embed(url, video_url))

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


# -----------------------------------------------------------------------------

# Allow cleaning up Zoom, watch2gether, etc. rooms after bot restarts
# Need to use on_raw_reaction_add to handle messages that aren't in the cache

CLOSED_MESSAGE_MAP = {
    r"zoom\.us": ZOOM_CLOSED_MESSAGE,
    r"Could not create Zoom": ZOOM_CLOSED_MESSAGE,
    r"meet\.jit\.si": MEET_CLOSED_MESSAGE,
    r"Could not create watch2gether": WATCH2GETHER_CLOSED_MESSAGE,
    r"w2g\.tv": WATCH2GETHER_CLOSED_MESSAGE,
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
    await store.connect()


async def on_shutdown(app):
    app["bot_task"].cancel()
    await app["bot_task"]
    await store.disconnect()


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
