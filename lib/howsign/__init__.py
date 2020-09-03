from dataclasses import dataclass
from urllib.parse import quote_plus
from pathlib import Path

from .case_insensitive_dict import CaseInsensitiveDict

HANDSHAPES_PATH = Path(__file__).parent / "handshapes"
HANDSHAPES = CaseInsensitiveDict(
    {
        "1": HANDSHAPES_PATH / "1.png",
        "3": HANDSHAPES_PATH / "3.png",
        "Bent3": HANDSHAPES_PATH / "Bent3.png",
        "4": HANDSHAPES_PATH / "4.png",
        "5": HANDSHAPES_PATH / "5.png",
        "Claw5": HANDSHAPES_PATH / "Claw5.png",
        "6": HANDSHAPES_PATH / "6.png",
        "7": HANDSHAPES_PATH / "7.png",
        "8": HANDSHAPES_PATH / "8.png",
        "Open8": HANDSHAPES_PATH / "Open8.png",
        "9": HANDSHAPES_PATH / "9.png",
        "Flat9": HANDSHAPES_PATH / "Flat9.png",
        "A": HANDSHAPES_PATH / "A.png",
        "OpenA": HANDSHAPES_PATH / "OpenA.png",
        "B": HANDSHAPES_PATH / "B.png",
        "BentB": HANDSHAPES_PATH / "BentB.png",
        "FlatB": HANDSHAPES_PATH / "FlatB.png",
        "OpenB": HANDSHAPES_PATH / "OpenB.png",
        "C": HANDSHAPES_PATH / "C.png",
        "FlatC": HANDSHAPES_PATH / "FlatC.png",
        "SmallC": HANDSHAPES_PATH / "SmallC.png",
        "D": HANDSHAPES_PATH / "D.png",
        "E": HANDSHAPES_PATH / "E.png",
        "G": HANDSHAPES_PATH / "G.png",
        "H": HANDSHAPES_PATH / "H.png",
        "I": HANDSHAPES_PATH / "I.png",
        "K": HANDSHAPES_PATH / "K.png",
        "L": HANDSHAPES_PATH / "L.png",
        "M": HANDSHAPES_PATH / "M.png",
        "OpenM": HANDSHAPES_PATH / "OpenM.png",
        "N": HANDSHAPES_PATH / "N.png",
        "OpenN": HANDSHAPES_PATH / "OpenN.png",
        "O": HANDSHAPES_PATH / "O.png",
        "FlatO": HANDSHAPES_PATH / "FlatO.png",
        "SmallO": HANDSHAPES_PATH / "SmallO.png",
        "R": HANDSHAPES_PATH / "R.png",
        "S": HANDSHAPES_PATH / "S.png",
        "T": HANDSHAPES_PATH / "T.png",
        "V": HANDSHAPES_PATH / "V.png",
        "BentV": HANDSHAPES_PATH / "BentV.png",
        "X": HANDSHAPES_PATH / "X.png",
        "OpenX": HANDSHAPES_PATH / "OpenX.png",
        "Y": HANDSHAPES_PATH / "Y.png",
        "ILY": HANDSHAPES_PATH / "ILY.png",
        "Corna": HANDSHAPES_PATH / "Corna.png",
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
        cased_name = HANDSHAPES._store[name.lower()][0]
        path = HANDSHAPES[name]
    except KeyError as error:
        raise HandshapeNotFoundError(
            f"Could not find handshape with name '{name}'"
        ) from error
    return Handshape(name=cased_name, path=path)


def get_lifeprint_url(word):
    return f"https://www.google.com/search?&q=site%3Alifeprint.com+{quote_plus(word)}"


def get_youglish_url(word):
    return f"https://youglish.com/pronounce/{quote_plus(word)}/signlanguage/asl"


def get_signingsavvy_url(word):
    return f"https://www.signingsavvy.com/search/{quote_plus(word)}"


def get_spread_the_sign_url(word):
    return f"https://www.spreadthesign.com/en.us/search/?q={quote_plus(word)}"
