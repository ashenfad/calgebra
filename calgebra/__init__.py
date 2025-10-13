from importlib.resources import files

from .core import Filter, Timeline, flatten, intersection, union
from .interval import Interval
from .metrics import (
    count_intervals,
    coverage_ratio,
    max_duration,
    min_duration,
    total_duration,
)
from .properties import Property, days, end, hours, minutes, one_of, seconds, start
from .windows import business_hours, weekdays, weekends

# Load documentation files for programmatic access by agents and code-aware tools
_docs_path = files(__package__) / "docs"
docs = {
    "readme": (_docs_path / "README.md").read_text(),
    "tutorial": (_docs_path / "TUTORIAL.md").read_text(),
    "api": (_docs_path / "API.md").read_text(),
}

__all__ = [
    "Interval",
    "Timeline",
    "Filter",
    "Property",
    "flatten",
    "union",
    "intersection",
    "one_of",
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
    "business_hours",
    "weekdays",
    "weekends",
    "docs",
]
