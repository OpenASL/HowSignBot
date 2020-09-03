import itertools
import random
from pathlib import Path

import yaml


HERE = Path(__file__).parent

with (HERE / "game_words.yaml").open("r") as fp:
    _game_words = yaml.load(fp, Loader=yaml.SafeLoader)

CATCHPHRASE = _game_words["catchphrase"]
CATEGORIES = list(CATCHPHRASE.keys())
ALL_WORDS = list(itertools.chain(*CATCHPHRASE.values()))


def catchphrase(category: str = None):
    word_list = CATCHPHRASE[category] if category else ALL_WORDS
    return random.choice(word_list)
