from dataclasses import dataclass
from typing import TypeVar


@dataclass(frozen=True, kw_only=True)
class Interval:
    start: int
    end: int

    def __str__(self) -> str:
        """Human-friendly string showing range and duration."""
        duration = self.end - self.start + 1
        return f"Interval({self.start}→{self.end}, {duration}s)"


IvlOut = TypeVar("IvlOut", bound="Interval", covariant=True)
IvlIn = TypeVar("IvlIn", bound="Interval", contravariant=True)
