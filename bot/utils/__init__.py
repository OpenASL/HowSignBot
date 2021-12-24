import difflib
import re
from typing import Optional
from typing import Sequence
from typing import Tuple

_spoiler_pattern = re.compile(r"\s*\|\|\s*(.*)\s*\|\|\s*")
_quotes_pattern = re.compile(r"[\"“](.*?)[\"”]")


def get_spoiler_text(val: str) -> Optional[str]:
    """Return value within spoiler text if it exists, else return `None`."""
    match = _spoiler_pattern.match(val)
    if match:
        return match.groups()[0]
    return None


def get_and_strip_quoted_text(val: str) -> Tuple[str, Optional[str]]:
    """Return `val` with quoted text removed as well as as the quoted text."""
    match = _quotes_pattern.search(val)
    if match:
        stripped = _quotes_pattern.sub("", val).strip()
        quoted = match.groups()[0]
        return stripped, quoted
    return val, None


def truncate(s: str, max_len: int, *, trailing: str = "…"):
    if len(s) > max_len:
        return f"{s[:max_len]}{trailing}"
    return s


def get_close_matches(word: str, possibilities: Sequence[str]) -> Sequence[str]:
    return difflib.get_close_matches(word, possibilities, n=1, cutoff=0.5)


def did_you_mean(word: str, possibilities: Sequence[str]) -> Optional[str]:
    try:
        return get_close_matches(word, possibilities)[0]
    except IndexError:
        return None
