import json
from pathlib import Path
from secrets import choice

HERE = Path(__file__).parent

with (HERE / "adjectives.json").open("r") as fp:
    _adjectives = json.load(fp)
with (HERE / "animals.json").open("r") as fp:
    _animals = json.load(fp)


def cuteid():
    return f"{choice(_adjectives)}-{choice(_adjectives)}-{choice(_animals)}".lower()
