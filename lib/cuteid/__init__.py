import random
import json
from pathlib import Path

HERE = Path(__file__).parent

with (HERE / "adjectives.json").open("r") as fp:
    _adjectives = json.load(fp)
with (HERE / "animals.json").open("r") as fp:
    _animals = json.load(fp)


def cuteid():
    return f"{random.choice(_adjectives)}-{random.choice(_adjectives)}-{random.choice(_animals)}".lower()
