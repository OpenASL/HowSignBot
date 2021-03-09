import itertools
import json
import random
from pathlib import Path
from typing import Optional

import yaml


HERE = Path(__file__).parent

with (HERE / "game_words.yaml").open("r") as fp:
    CATCHPHRASE = yaml.load(fp, Loader=yaml.SafeLoader)["catchphrase"]
with (HERE / "sentences.json").open("r") as fp:
    SENTENCES = json.load(fp)["data"]
with (HERE / "phrases.json").open("r") as fp:
    IDIOMS = json.load(fp)["data"]

CATEGORIES = list(CATCHPHRASE.keys())
ALL_WORDS = list(itertools.chain(*CATCHPHRASE.values()))


def catchphrase(category: Optional[str] = None):
    word_list = CATCHPHRASE[category] if category else ALL_WORDS
    return random.choice(word_list)


def sentence():
    return random.choice(SENTENCES)["sentence"]


def idiom():
    return random.choice(IDIOMS)
