import os
import random
from unittest import mock

import gspread
import pytest
import pytz
from asynctest import patch
from disnake.ext import commands
from freezegun import freeze_time

# Must be before bot import
os.environ["TESTING"] = "true"

from bot import database, settings  # noqa:E402
from bot.exts.practices import practice  # noqa:E402

random.seed(1)


@pytest.fixture
async def mock_worksheet(monkeypatch, db):
    monkeypatch.setattr(settings, "GOOGLE_PRIVATE_KEY", "fake", raising=True)
    await db.execute(
        database.guild_settings.insert(), {"guild_id": 1234, "schedule_sheet_key": "abc"}
    )
    # Need to mock both of these since they get called in different files
    with patch(
        "bot.exts.practices.practice.get_practice_worksheet_for_guild"
    ) as mock_get_worksheet, patch(
        "bot.exts.practices._practice_sessions.get_practice_worksheet_for_guild"
    ) as mock_get_worksheet2:
        WorksheetMock = mock.Mock(spec=gspread.Worksheet)
        WorksheetMock.get_all_values.return_value = [
            ["docs", "more docs", ""],
            ["Start time", "Host (optional)", "Details (optional)", ""],
            ["Friday 5pm EDT", "Steve", "<@!12345>", "recurring", ""],
            ["Friday 6pm EDT", "Steve", "<@!12345>", "paused", "x"],
            ["Wed 6pm edt", "", "", "another recurring", ""],
            ["9/26 2pm PDT 2020", "Steve", "<@!12345>", "one time", ""],
            ["Sunday, September 27 02:00 PM EDT 2020", "", "", "another 1️⃣", ""],
            ["Nov 26 02:00 PM EDT 2020", "", "", "Turkey day PRACTICE", ""],
        ]
        mock_get_worksheet.return_value = mock_get_worksheet2.return_value = WorksheetMock
        yield WorksheetMock


@pytest.mark.parametrize(
    "when",
    (
        None,
        "today",
        "tomorrow",
        "saturday",
        "9/27",
    ),
)
@pytest.mark.asyncio
@freeze_time("2020-09-25 14:00:00")
async def test_schedule(snapshot, mock_worksheet, store, when):
    result = await practice.schedule_impl(1234, when)
    assert result == snapshot


@pytest.mark.asyncio
@freeze_time("2020-11-26 14:00:00")
async def test_schedule_on_a_holiday(snapshot, mock_worksheet, store):
    result = await practice.schedule_impl(1234, None)
    assert result == snapshot


@pytest.mark.asyncio
@freeze_time("2020-09-25 14:00:00")
async def test_schedule_no_practices(snapshot, mock_worksheet):
    result = await practice.schedule_impl(1234, "9/28/2020")
    embed = result["embed"]
    assert "September 28" in embed.description
    assert "There are no scheduled practices today" in embed.description
    assert (
        "To schedule a practice, edit the schedule below or use the" in embed.description
    )


@pytest.mark.parametrize(
    "start_time",
    (
        "2pm edt",
        "at 2pm edt",
        '2pm edt "chat and games! 🎉"',
        "9/24 1:45pm edt “around 45 min.-1 hour”",
        "tomorrow 2pm pdt",
        "sunday 10:30pm pdt",
        "9/27 9am cdt",
        '"games" 10am edt Sunday',
        '"games" at 10am edt on Sunday',
        '"games" at 10am edt on 9/27',
        '10am edt "games" on 9/27',
        '"classifiers" at 6pm pdt',
    ),
)
@freeze_time("2020-09-25 14:00:00")
@pytest.mark.asyncio
async def test_practice(snapshot, mock_worksheet, start_time, store):
    await practice.practice_impl(
        guild_id=1234,
        host="Steve",
        mention="<@!12345>",
        start_time=start_time,
        user_id=12345679,
    )
    mock_worksheet.append_row.assert_called_once()
    assert mock_worksheet.append_row.call_args[0][0] == snapshot


@pytest.mark.asyncio
async def test_practice_caches_timezone(mock_worksheet, store):
    await practice.practice_impl(
        guild_id=1234,
        host="Steve",
        mention="<@!12345>",
        start_time="tomorrow 8pm est",
        user_id=123,
    )
    timezone = await store.get_user_timezone(123)
    assert timezone == pytz.timezone("America/New_York")


@pytest.mark.asyncio
async def test_practice_errors_if_time_zone_cannot_be_parsed(mock_worksheet, store):
    with pytest.raises(commands.errors.BadArgument, match="Could not parse time zone"):
        await practice.practice_impl(
            guild_id=1234,
            host="Steve",
            mention="<@!12345>",
            start_time="tomorrow 8pm",
            user_id=321,
        )


@pytest.mark.asyncio
async def test_practice_nearby_date(snapshot, mock_worksheet, store):
    with freeze_time("2020-09-25 14:00:00"):
        await practice.practice_impl(
            guild_id=1234,
            host="Steve",
            mention="<@!12345>",
            start_time="10:30am edt",
            user_id=123,
        )

    mock_worksheet.append_row.assert_called_once()
    appended_row = mock_worksheet.append_row.call_args[0][0]
    assert appended_row == (
        "Friday, September 25 10:30 AM EDT 2020",
        "Steve",
        "<@!12345>",
        "",
    )


@pytest.mark.parametrize(
    "start_time",
    (
        "today",
        "tomorrow",
        "today edt",
        "today pdt",
    ),
)
@freeze_time("2020-09-25 14:00:00")
@pytest.mark.asyncio
async def test_practice_common_mistakes(snapshot, mock_worksheet, start_time):
    with pytest.raises(
        commands.errors.CommandError, match="️To schedule a practice, enter a time"
    ):
        await practice.practice_impl(
            guild_id=1234,
            host="Steve",
            mention="<@!12345>",
            start_time=start_time,
            user_id=123,
        )
    mock_worksheet.append_row.assert_not_called()


@freeze_time("2020-09-25 14:00:00")
@pytest.mark.asyncio
async def test_practice_invalid(mock_worksheet, store):
    with pytest.raises(
        commands.errors.CommandError,
        match='Could not parse "invalid" into a date or time. Make sure to include "am" or "pm" as well as a timezone',
    ):
        await practice.practice_impl(
            guild_id=1234,
            host="Steve",
            mention="<@!12345>",
            start_time="invalid",
            user_id=123,
        )
    mock_worksheet.append_row.assert_not_called()
