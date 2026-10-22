import re
import unicodedata
from decimal import Decimal, InvalidOperation

_WS = re.compile(r"\s+")
_CAT_SEP = re.compile(r"\s*>\s*|\s*\|\s*|\s+/\s+")


def normalize_text(s: str) -> str:
    """NFKC, all whitespace (incl. NBSP/tabs/newlines) collapsed to single spaces."""
    return _WS.sub(" ", unicodedata.normalize("NFKC", s)).strip()


def split_category_path(s: str) -> list[str]:
    """Split on '>', '|' or a spaced ' / '. An unspaced '/' is part of a name."""
    return [p for p in (normalize_text(x) for x in _CAT_SEP.split(s)) if p]


def parse_number(raw: str) -> Decimal:
    """'1 200,50' / NBSP-grouped / '1200.50' -> Decimal('1200.50'). Raises ValueError."""
    s = re.sub(r"[\s  ]", "", raw)
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    else:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError(f"не число: {raw!r}") from None
