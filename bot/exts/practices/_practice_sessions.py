import datetime as dt
import logging
from typing import List, NamedTuple, Optional

import disnake
import holiday_emojis

from bot import settings
from bot.database import store
from bot.utils import truncate
from bot.utils.datetimes import (
    PACIFIC,
    PACIFIC_CURRENT_NAME,
    format_datetime,
    parse_human_readable_datetime,
    utcnow,
)
from bot.utils.discord import THEME_COLOR
from bot.utils.gcal import create_gcal_url
from bot.utils.gsheets import get_gsheet_client

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX


class PracticeSession(NamedTuple):
    dtime: dt.datetime
    host: str
    mention: str
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
        (
            PracticeSession(
                dtime=session_dtime,
                host=row[1],
                mention=row[2],
                notes=row[3],
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
            and not bool(row[4])
        ),
        key=lambda s: s.dtime,
    )


NO_PRACTICES = """

*There are no scheduled practices today!*

To schedule a practice, edit the schedule below or use the `{COMMAND_PREFIX}practice` command.
Example: `{COMMAND_PREFIX}practice today 2pm {pacific}`
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX,
    pacific=PACIFIC_CURRENT_NAME.lower(),
)


def make_base_embed(dtime: dt.datetime) -> disnake.Embed:
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
    return disnake.Embed(description=description, color=THEME_COLOR)


async def make_practice_session_embed(
    guild_id: int, sessions: List[PracticeSession], *, dtime: dt.datetime
) -> disnake.Embed:
    embed = make_base_embed(dtime)
    sheet_key = await store.get_guild_schedule_sheet_key(guild_id)
    schedule_url = f"https://docs.google.com/spreadsheets/d/{sheet_key}/edit"
    if not sessions and embed.description:
        embed.description += NO_PRACTICES
    else:
        num_sessions = len(sessions)
        for session in sessions:
            title = format_datetime(session.dtime, format_type="t")
            gcal_event_title = (
                f"ASL Practice: {truncate(session.notes, 50)}"
                if session.notes
                else "ASL Practice"
            )
            gcal_url = create_gcal_url(
                gcal_event_title,
                start=session.dtime,
                description=f"See the full schedule here: {schedule_url}",
            )
            value = f"[+Google Calendar]({gcal_url})"
            if session.host:
                value += f"\n> Host: {session.mention or session.host}"
            if session.notes:
                limit = 800 // num_sessions
                trailing = f"…[More]({schedule_url})"
                value += (
                    f"\n> Details: {truncate(session.notes, limit, trailing=trailing)}"
                )
            embed.add_field(name=title, value=value, inline=False)
    embed.add_field(
        name="🗓 View or edit the schedule using the link below.",
        value=f"[Full schedule]({schedule_url})",
    )
    return embed


async def make_practice_sessions_today_embed(guild_id: int) -> disnake.Embed:
    now = utcnow()
    sessions = await get_practice_sessions(guild_id, dtime=now)
    return await make_practice_session_embed(guild_id, sessions, dtime=now)
