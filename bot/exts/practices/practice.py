import datetime as dt
import logging
from contextlib import suppress
from typing import Any
from typing import Dict
from typing import Optional
from typing import Tuple

import discord
import pytz
from discord.ext import commands
from discord.ext.commands import Context

from ._practice_sessions import get_practice_sessions
from ._practice_sessions import get_practice_worksheet_for_guild
from ._practice_sessions import make_practice_session_embed
from bot import settings
from bot.database import store
from bot.utils import get_and_strip_quoted_text
from bot.utils.datetimes import display_timezone
from bot.utils.datetimes import EASTERN_CURRENT_NAME
from bot.utils.datetimes import format_multi_time
from bot.utils.datetimes import NoTimeZoneError
from bot.utils.datetimes import PACIFIC
from bot.utils.datetimes import PACIFIC_CURRENT_NAME
from bot.utils.datetimes import parse_human_readable_datetime
from bot.utils.datetimes import utcnow
from bot.utils.discord import display_name

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX


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
    settings: Optional[Dict[str, Any]]
    if when and when.strip().lower() != "today":
        now_pacific = utcnow().astimezone(PACIFIC)
        settings = {
            "PREFER_DATES_FROM": "future",
            # Workaround for https://github.com/scrapinghub/dateparser/issues/403
            "RELATIVE_BASE": now_pacific.replace(tzinfo=None),
        }
        dtime, _ = parse_human_readable_datetime(when, settings=settings) or utcnow()
        dtime = dtime or utcnow()
    else:
        settings = None
        dtime = utcnow()
    sessions = await get_practice_sessions(guild_id, dtime=dtime, parse_settings=settings)
    embed = await make_practice_session_embed(guild_id, sessions, dtime=dtime)
    return {"embed": embed}


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
) -> Tuple[Optional[dt.datetime], Optional[dt.tzinfo]]:
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
    except pytz.UnknownTimeZoneError:
        raise commands.errors.BadArgument("⚠️Invalid time zone. Please try again.")
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


class Practice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="practice", help=PRACTICE_HELP)
    async def practice_command(self, ctx: Context, *, start_time: str):
        await ctx.channel.trigger_typing()
        bot = self.bot

        is_dm = not bool(ctx.guild)
        if is_dm:
            guild_ids_with_schedules = await store.get_guild_ids_with_practice_schedules()
            members_and_guilds = []
            for guild_id in guild_ids_with_schedules:
                guild = bot.get_guild(guild_id)
                # Use fetch_member to check membership instead of get_member because cache might not be populated
                try:
                    member = await guild.fetch_member(ctx.author.id)
                except Exception:
                    pass
                else:
                    members_and_guilds.append((member, guild))
        else:
            has_practice_schedule = await store.guild_has_practice_schedule(ctx.guild.id)
            if not has_practice_schedule:
                raise commands.errors.CheckFailure(
                    "⚠️ No configured practice schedule for this server. If you think this is a mistake, contact the bot owner."
                )
            members_and_guilds = [(ctx.author, ctx.guild)]

        dm_response = None
        old_timezone, new_timezone = None, None
        channel_id, channel = None, None
        for member, guild in members_and_guilds:
            guild_id = guild.id
            ret = await practice_impl(
                guild_id=guild_id,
                host=display_name(member),
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
            if members_and_guilds:
                dm_response = (
                    "🙌  Thanks for scheduling a practice in the following servers:\n"
                )
                for _, guild in members_and_guilds:
                    dm_response += f"*{guild.name}*\n"
            else:
                dm_response = "⚠️ You are not a member of any servers that have a practice schedule."
        else:
            if str(old_timezone) != str(new_timezone):
                assert new_timezone is not None
                new_timezone_display = display_timezone(new_timezone, utcnow()).lower()
                dm_response = TIMEZONE_CHANGE_TEMPLATE.format(
                    new_timezone=new_timezone,
                    new_timezone_display=new_timezone_display,
                    COMMAND_PREFIX=COMMAND_PREFIX,
                )
            # message sent outside of practice schedule channel
            if channel_id and channel and ctx.channel.id != channel_id:
                await ctx.channel.send(f"🙌  New practice posted in {channel.mention}.")
        if dm_response:
            try:
                await ctx.author.send(dm_response)
            except discord.errors.Forbidden:
                logger.warn("cannot send DM to user. skipping...")

    @commands.command(name="schedule", aliases=("sched", "practices"), help=SCHEDULE_HELP)
    @commands.check(has_practice_schedule)
    async def schedule_command(self, ctx: Context, *, when: Optional[str]):
        await ctx.channel.trigger_typing()
        ret = await schedule_impl(guild_id=ctx.guild.id, when=when)
        await ctx.send(**ret)

    @practice_command.error
    @schedule_command.error
    async def practices_error(self, ctx: Context, error: Exception):
        if isinstance(error, commands.errors.MissingRequiredArgument):
            await ctx.send(PRACTICE_ERROR)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Practice(bot))
