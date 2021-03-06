import random

import pytest

from bot.exts import games

random.seed(1)


def test_catchphrase(snapshot):
    result = games.catchphrase_impl()
    assert result == snapshot


@pytest.mark.parametrize("category", ("categories", "food", "Hard"))
def test_catchphrase_categories(snapshot, category):
    result = games.catchphrase_impl(category)
    assert result == snapshot
