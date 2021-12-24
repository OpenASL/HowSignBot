import random
from dataclasses import dataclass
from pathlib import Path

from .case_insensitive_dict import CaseInsensitiveDict

ASSETS_PATH = Path(__file__).parent / "assets"
HANDSHAPE_NAMES = (
    "1",
    "3",
    "Bent3",
    "4",
    "5",
    "Claw5",
    "6",
    "7",
    "8",
    "Open8",
    "9",
    "Flat9",
    "A",
    "OpenA",
    "B",
    "BentB",
    "FlatB",
    "OpenB",
    "C",
    "FlatC",
    "SmallC",
    "D",
    "E",
    "G",
    "H",
    "I",
    "K",
    "L",
    "M",
    "OpenM",
    "N",
    "OpenN",
    "O",
    "FlatO",
    "SmallO",
    "R",
    "S",
    "T",
    "V",
    "BentV",
    "X",
    "OpenX",
    "Y",
    "ILY",
    "Corna",
)
HANDSHAPE_PATHS = CaseInsensitiveDict(
    {
        handshape_name: ASSETS_PATH / f"{handshape_name}.png"
        for handshape_name in HANDSHAPE_NAMES
    }
)


@dataclass
class Handshape:
    name: str
    path: Path


class HandshapeNotFoundError(KeyError):
    pass


def get_handshape(name):
    try:
        cased_name = HANDSHAPE_PATHS._store[name.lower()][0]
        path = HANDSHAPE_PATHS[name]
    except KeyError as error:
        raise HandshapeNotFoundError(
            f"Could not find handshape with name '{name}'"
        ) from error
    return Handshape(name=cased_name, path=path)


def get_random_handshape(rand=None):
    rand = rand or random
    name = rand.choice(HANDSHAPE_NAMES)
    return get_handshape(name)
