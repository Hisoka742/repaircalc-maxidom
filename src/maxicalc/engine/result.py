from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Calc:
    """A calculated quantity with a human-readable (Russian) calculation trace."""

    value: Decimal
    unit: str
    explain: tuple[str, ...]
