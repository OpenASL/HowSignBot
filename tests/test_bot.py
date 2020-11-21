import os
import datetime as dt
import random
from unittest import mock

import gspread
import pytest
import pytz
from asynctest import patch
from discord.ext import commands
from freezegun import freeze_time
from syrupy.filters import props

# Must be before bot import
os.environ["TESTING"] = "true"

import bot  # noqa:E402
import database  # noqa:E402

random.seed(1)


@pytest.mark.parametrize(
    "word",
    (
        "tiger",
        "||tiger||",
        "what's up",
        "||what's up||",
        "need, ask",
        "||need, ask||",
    ),
)
def test_sign(snapshot, word):
    result = bot.sign_impl(word)
    assert result == snapshot


@pytest.mark.parametrize("name", ("random", "open8", "open9"))
def test_handshape(snapshot, name):
    result = bot.handshape_impl(name)
    assert result == snapshot(
        exclude=props(
            "fp",
        )
    )


def test_handshapes(snapshot):
    result = bot.handshapes_impl()
    assert result == snapshot


@pytest.mark.parametrize("kind", ("any", "text", "gif"))
def test_clthat(snapshot, kind):
    result = bot.clthat_impl(kind)
    assert result == snapshot


def test_catchphrase(snapshot):
    result = bot.catchphrase_impl()
    assert result == snapshot


@pytest.mark.parametrize("category", ("categories", "food", "Hard"))
def test_catchphrase_categories(snapshot, category):
    result = bot.catchphrase_impl(category)
    assert result == snapshot


@pytest.mark.parametrize("spoiler", (None, "||"))
def test_sentence(snapshot, spoiler):
    result = bot.sentence_impl(spoiler)
    assert result == snapshot


@pytest.mark.parametrize("spoiler", (None, "||"))
def test_idiom(snapshot, spoiler):
    result = bot.idiom_impl(spoiler)
    assert result == snapshot


@pytest.fixture
async def mock_worksheet(monkeypatch, db):
    monkeypatch.setattr(bot, "GOOGLE_PRIVATE_KEY", "fake", raising=True)
    await db.execute(
        database.guild_settings.insert(), {"guild_id": 1234, "schedule_sheet_key": "abc"}
    )
    with patch("bot.get_practice_worksheet_for_guild") as mock_get_worksheet:
        WorksheetMock = mock.Mock(spec=gspread.Worksheet)
        WorksheetMock.get_all_values.return_value = [
            ["docs", "more docs", ""],
            ["Start time", "Host (optional)", "Notes (optional)", ""],
            ["Friday 5pm EDT", "Steve", "recurring", ""],
            ["Friday 6pm EDT", "Steve", "paused", "x"],
            ["Wed 6pm edt", "", "another recurring", ""],
            ["9/26 2pm PDT 2020", "Steve", "one time", ""],
            ["Sunday, September 27 02:00 PM EDT 2020", "", "another 1️⃣", ""],
        ]
        mock_get_worksheet.return_value = WorksheetMock
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
    result = await bot.schedule_impl(1234, when)
    assert result == snapshot


@pytest.mark.asyncio
@freeze_time("2020-11-26 14:00:00")
async def test_schedule_on_a_holiday(snapshot, mock_worksheet, store):
    result = await bot.schedule_impl(1234, None)
    assert result == snapshot


@pytest.mark.asyncio
@freeze_time("2020-09-25 14:00:00")
async def test_schedule_no_practices(snapshot, mock_worksheet):
    result = await bot.schedule_impl(1234, "9/28/2020")
    embed = result["embed"]
    assert "September 28" in embed.description
    assert "There are no scheduled practices yet" in embed.description
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
    await bot.practice_impl(
        guild_id=1234, host="Steve", start_time=start_time, user_id=12345679
    )
    mock_worksheet.append_row.assert_called_once()
    assert mock_worksheet.append_row.call_args[0][0] == snapshot


@pytest.mark.asyncio
async def test_practice_caches_timezone(mock_worksheet, store):
    await bot.practice_impl(
        guild_id=1234, host="Steve", start_time="tomorrow 8pm est", user_id=123
    )
    timezone = await store.get_user_timezone(123)
    assert timezone == pytz.timezone("America/New_York")


@pytest.mark.asyncio
async def test_practice_errors_if_time_zone_cannot_be_parsed(mock_worksheet, store):
    with pytest.raises(commands.errors.BadArgument, match="Could not parse time zone"):
        await bot.practice_impl(
            guild_id=1234, host="Steve", start_time="tomorrow 8pm", user_id=321
        )


@pytest.mark.asyncio
async def test_practice_nearby_date(snapshot, mock_worksheet, store):
    with freeze_time("2020-09-25 14:00:00"):
        await bot.practice_impl(
            guild_id=1234, host="Steve", start_time="10:30am edt", user_id=123
        )

    mock_worksheet.append_row.assert_called_once()
    appended_row = mock_worksheet.append_row.call_args[0][0]
    assert appended_row == ("Friday, September 25 10:30 AM EDT 2020", "Steve", "")


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
        await bot.practice_impl(
            guild_id=1234, host="Steve", start_time=start_time, user_id=123
        )
    mock_worksheet.append_row.assert_not_called()


@freeze_time("2020-09-25 14:00:00")
@pytest.mark.asyncio
async def test_practice_invalid(snapshot, mock_worksheet, store):
    with pytest.raises(
        commands.errors.CommandError,
        match='Could not parse "invalid" into a date or time. Make sure to include "am" or "pm" as well as a timezone',
    ):
        await bot.practice_impl(
            guild_id=1234, host="Steve", start_time="invalid", user_id=123
        )
    mock_worksheet.append_row.assert_not_called()


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ('today 2pm "chat"', ("today 2pm", "chat")),
        ('"chat" today 2pm', ("today 2pm", "chat")),
        ("today 2pm", ("today 2pm", None)),
        ('today 2pm ""', ("today 2pm", "")),
        ('today 2pm "steve\'s practice"', ("today 2pm", "steve's practice")),
        ("today 2pm “smart quotes 😞”", ("today 2pm", "smart quotes 😞")),
    ),
)
def test_get_and_strip_quoted_text(value, expected):
    assert bot.get_and_strip_quoted_text(value) == expected


@pytest.mark.parametrize(
    "value",
    (
        "today 8:25pm edt",
        "today 2pm edt",
        "today at 2pm edt",
        "tomorrow 2pm pdt",
        "on friday at 2pm cst",
        "9/25 2:30 pm cdt",
    ),
)
@freeze_time("2020-09-25 14:00:00")
def test_parse_human_readable_datetime(value, snapshot):
    dtime, _ = bot.parse_human_readable_datetime(value)
    assert dtime.tzinfo == dt.timezone.utc
    assert dtime.isoformat() == snapshot


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (pytz.timezone("America/New_York"), "EDT"),
        (pytz.timezone("America/Los_Angeles"), "PDT"),
    ),
)
def test_display_timezone(value, expected):
    dtime = dt.datetime(2020, 9, 25, tzinfo=dt.timezone.utc)
    assert bot.display_timezone(value, dtime) == expected


@freeze_time("2020-09-25 14:00:00")
def test_get_daily_handshape():
    todays_handshape = bot.get_daily_handshape()
    assert todays_handshape == bot.get_daily_handshape()
    assert todays_handshape != bot.get_daily_handshape(dt.datetime(2020, 9, 26))
