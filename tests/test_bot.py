import datetime as dt
import random

import pytest
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
        "tomorrow 2pm pdt",
        "friday 2pm cst",
        "9/25 2:30 pm cdt",
    ),
)
def test_parse_human_readable_datetime(value):
    dtime = bot.parse_human_readable_datetime(value)
    assert dtime.tzinfo == dt.timezone.utc
