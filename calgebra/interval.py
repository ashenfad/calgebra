from dataclasses import dataclass
from typing import TypeVar


@dataclass(frozen=True, kw_only=True)
class Interval:
    start: int
    end: int


IvlOut = TypeVar("IvlOut", bound="Interval", covariant=True)
IvlIn = TypeVar("IvlIn", bound="Interval", contravariant=True)
