import random

import pytest

from bot.exts import english

random.seed(1)


@pytest.mark.parametrize("spoil", (False, True))
def test_sentence(snapshot, spoil):
    result = english.sentence_impl(spoil)
    assert result == snapshot


@pytest.mark.parametrize("spoil", (False, True))
def test_idiom(snapshot, spoil):
    result = english.idiom_impl(spoil)
    assert result == snapshot
