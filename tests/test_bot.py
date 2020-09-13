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
