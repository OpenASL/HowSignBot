import random

import pytest

from bot.exts import english

random.seed(1)


@pytest.mark.parametrize("spoiler", (None, "||"))
def test_sentence(snapshot, spoiler):
    result = english.sentence_impl(spoiler)
    assert result == snapshot


@pytest.mark.parametrize("spoiler", (None, "||"))
def test_idiom(snapshot, spoiler):
    result = english.idiom_impl(spoiler)
    assert result == snapshot
