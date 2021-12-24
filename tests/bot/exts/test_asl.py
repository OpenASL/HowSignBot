import random

import pytest
from disnake.ext import commands
from syrupy.filters import props

from bot.exts import asl

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
    result = asl.sign_impl(word)
    assert result == snapshot


def test_sign_long_input():
    with pytest.raises(commands.errors.BadArgument, match="too long"):
        asl.sign_impl("a" * 101)


@pytest.mark.parametrize("name", ("random", "open8", "open9"))
def test_handshape(snapshot, name):
    result = asl.handshape_impl(name)
    assert result == snapshot(
        exclude=props(
            "fp",
        )
    )


def test_handshapes(snapshot):
    result = asl.handshapes_impl(prefix="!")
    assert result == snapshot
