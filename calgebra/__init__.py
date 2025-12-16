from dataclasses import dataclass
from importlib.resources import files

from .core import Filter, Timeline, flatten, intersection, union
from .interval import Interval, pprint
from .metrics import (
    count_intervals,
    coverage_ratio,
    max_duration,
    min_duration,
    total_duration,
)
from .mutable.memory import timeline
from .properties import (
    Property,
    days,
    end,
    field,
    has_all,
    has_any,
    hours,
    minutes,
    one_of,
    seconds,
    start,
)
from .recurrence import day_of_week, recurring, time_of_day
from .transform import buffer, merge_within
from .util import DAY, HOUR, MINUTE, SECOND, at_tz


@dataclass(frozen=True)
class Docs:
    """Programmatic access to calgebra documentation files."""

    readme: str
    tutorial: str
    api: str
    gcsa: str
    quick_start: str


# Load documentation files for programmatic access by agents and code-aware tools
_docs_path = files(__package__) / "docs"

docs = Docs(
    readme=(_docs_path / "README.md").read_text(),
    tutorial=(_docs_path / "TUTORIAL.md").read_text(),
    api=(_docs_path / "API.md").read_text(),
    gcsa=(_docs_path / "GCSA.md").read_text(),
    quick_start=(_docs_path / "QUICK-START.md").read_text(),
)

__all__ = [
    "Interval",
    "Timeline",
    "Filter",
    "Property",
    "timeline",
    "flatten",
    "union",
    "intersection",
    "one_of",
    "has_any",
    "has_all",
    "field",
    "days",
    "start",
    "end",
    "hours",
    "minutes",
    "seconds",
    "total_duration",
    "max_duration",
    "min_duration",
    "count_intervals",
    "coverage_ratio",
    "day_of_week",
    "time_of_day",
    "recurring",
    "buffer",
    "merge_within",
    "SECOND",
    "MINUTE",
    "HOUR",
    "DAY",
    "at_tz",
    "pprint",
    "docs",
    "Docs",
]
