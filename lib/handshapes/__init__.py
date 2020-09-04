from dataclasses import dataclass
from pathlib import Path

from .case_insensitive_dict import CaseInsensitiveDict

ASSETS_PATH = Path(__file__).parent / "assets"
HANDSHAPES = CaseInsensitiveDict(
    {
        "1": ASSETS_PATH / "1.png",
        "3": ASSETS_PATH / "3.png",
        "Bent3": ASSETS_PATH / "Bent3.png",
        "4": ASSETS_PATH / "4.png",
        "5": ASSETS_PATH / "5.png",
        "Claw5": ASSETS_PATH / "Claw5.png",
        "6": ASSETS_PATH / "6.png",
        "7": ASSETS_PATH / "7.png",
        "8": ASSETS_PATH / "8.png",
        "Open8": ASSETS_PATH / "Open8.png",
        "9": ASSETS_PATH / "9.png",
        "Flat9": ASSETS_PATH / "Flat9.png",
        "A": ASSETS_PATH / "A.png",
        "OpenA": ASSETS_PATH / "OpenA.png",
        "B": ASSETS_PATH / "B.png",
        "BentB": ASSETS_PATH / "BentB.png",
        "FlatB": ASSETS_PATH / "FlatB.png",
        "OpenB": ASSETS_PATH / "OpenB.png",
        "C": ASSETS_PATH / "C.png",
        "FlatC": ASSETS_PATH / "FlatC.png",
        "SmallC": ASSETS_PATH / "SmallC.png",
        "D": ASSETS_PATH / "D.png",
        "E": ASSETS_PATH / "E.png",
        "G": ASSETS_PATH / "G.png",
        "H": ASSETS_PATH / "H.png",
        "I": ASSETS_PATH / "I.png",
        "K": ASSETS_PATH / "K.png",
        "L": ASSETS_PATH / "L.png",
        "M": ASSETS_PATH / "M.png",
        "OpenM": ASSETS_PATH / "OpenM.png",
        "N": ASSETS_PATH / "N.png",
        "OpenN": ASSETS_PATH / "OpenN.png",
        "O": ASSETS_PATH / "O.png",
        "FlatO": ASSETS_PATH / "FlatO.png",
        "SmallO": ASSETS_PATH / "SmallO.png",
        "R": ASSETS_PATH / "R.png",
        "S": ASSETS_PATH / "S.png",
        "T": ASSETS_PATH / "T.png",
        "V": ASSETS_PATH / "V.png",
        "BentV": ASSETS_PATH / "BentV.png",
        "X": ASSETS_PATH / "X.png",
        "OpenX": ASSETS_PATH / "OpenX.png",
        "Y": ASSETS_PATH / "Y.png",
        "ILY": ASSETS_PATH / "ILY.png",
        "Corna": ASSETS_PATH / "Corna.png",
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
