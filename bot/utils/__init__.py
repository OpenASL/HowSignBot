import difflib
import re
from typing import Optional
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


def truncate(s: str, max_len: int):
    if len(s) > max_len:
        return f"{s[:max_len]}..."
    return s


def did_you_mean(word, possibilities):
    try:
        return difflib.get_close_matches(word, possibilities, n=1, cutoff=0.5)[0]
    except IndexError:
        return None
