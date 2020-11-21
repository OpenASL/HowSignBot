import itertools
import json
from pathlib import Path
import random as _random


HERE = Path(__file__).parent

with (HERE / "text.json").open("r") as fp:
    TEXT = json.load(fp)
with (HERE / "gifs.json").open("r") as fp:
    GIFS = json.load(fp)

GIF_URLS = [each["url"] for each in GIFS]
ALL = list(itertools.chain(TEXT, GIF_URLS))


def random(rand=None):
    rand = rand or _random
    return rand.choice(ALL)


def text(rand=None):
    rand = rand or _random
    return rand.choice(TEXT)


def gif_url(rand=None):
    rand = rand or _random
    return rand.choice(GIF_URLS)
