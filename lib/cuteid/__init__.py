import json
from pathlib import Path
from secrets import choice

import emoji

HERE = Path(__file__).parent

with (HERE / "adjectives.json").open("r") as fp:
    _adjectives = json.load(fp)
with (HERE / "animals.json").open("r") as fp:
    _animals = json.load(fp)

_emoji = tuple(emoji.EMOJI_UNICODE_ENGLISH.values())  # type: ignore[attr-defined]


def cuteid():
    return f"{choice(_adjectives)}-{choice(_adjectives)}-{choice(_animals)}".lower()


def emojid(length=4):
    return "".join(choice(_emoji) for _ in range(length))
