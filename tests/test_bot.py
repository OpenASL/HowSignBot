import datetime as dt
import random
from unittest import mock

import gspread
import pytest
from discord.ext import commands
from freezegun import freeze_time
from syrupy.filters import props

import bot

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
def mock_worksheet(monkeypatch):
    monkeypatch.setattr(bot, "SCHEDULE_SHEET_KEYS", {1234: "abc"}, raising=True)
    monkeypatch.setattr(bot, "GOOGLE_PRIVATE_KEY", "fake", raising=True)
    with mock.patch("bot.get_practice_worksheet_for_guild") as mock_get_worksheet:
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
@freeze_time("2020-09-25 14:00:00")
def test_schedule(snapshot, mock_worksheet, when):
    result = bot.schedule_impl(1234, when)
    assert result == snapshot


@freeze_time("2020-09-25 14:00:00")
def test_schedule_no_practices(snapshot, mock_worksheet):
    result = bot.schedule_impl(1234, "9/28/2020")
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
def test_practice(snapshot, mock_worksheet, start_time):
    bot.practice_impl(guild_id=1234, host="Steve", start_time=start_time)
    mock_worksheet.append_row.assert_called_once()
    assert mock_worksheet.append_row.call_args[0][0] == snapshot


def test_practice_nearby_date(snapshot, mock_worksheet):
    with freeze_time("2020-09-25 14:00:00"):
        bot.practice_impl(guild_id=1234, host="Steve", start_time="10:30am edt")

    mock_worksheet.append_row.assert_called_once()
    appended_row = mock_worksheet.append_row.call_args[0][0]
    assert appended_row == ("Friday, September 25 07:30 AM PDT 2020", "Steve", "")


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
def test_practice_common_mistakes(snapshot, mock_worksheet, start_time):
    with pytest.raises(
        commands.errors.CommandError, match="️To schedule a practice, enter a time"
    ):
        bot.practice_impl(guild_id=1234, host="Steve", start_time=start_time)
    mock_worksheet.append_row.assert_not_called()


@freeze_time("2020-09-25 14:00:00")
def test_practice_invalid(snapshot, mock_worksheet):
    with pytest.raises(
        commands.errors.CommandError,
        match='Could not parse "invalid" into a date or time. Make sure to include "am" or "pm" as well as a timezone',
    ):
        bot.practice_impl(guild_id=1234, host="Steve", start_time="invalid")
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
def test_parse_human_readable_datetime(value):
    dtime = bot.parse_human_readable_datetime(value)
    assert dtime.tzinfo == dt.timezone.utc
