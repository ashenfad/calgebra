from typing import TypeVar

from .core import Timeline, flatten
from .interval import Interval

Ivl = TypeVar("Ivl", bound=Interval)


def total_duration(
    timeline: Timeline[Interval],
    start: int,
    end: int,
) -> int:
    """Return the inclusive duration covered by a timeline between two bounds."""
    if start > end:
        return 0

    total = 0
    for event in flatten(timeline)[start:end]:
        # Skip unbounded intervals (shouldn't happen with finite bounds, but be safe)
        if event.start is None or event.end is None:
            continue
        total += event.end - event.start + 1

    return total


def max_duration(
    timeline: Timeline[Ivl],
    start: int,
    end: int,
) -> Ivl | None:
    """Return the longest interval within the slice."""
    if start > end:
        return None

    longest: Ivl | None = None
    longest_len = -1
    for event in timeline[start:end]:
        # Skip unbounded intervals (shouldn't happen with finite bounds, but be safe)
        if event.start is None or event.end is None:
            continue
        length = event.end - event.start + 1
        if length > longest_len:
            longest = event
            longest_len = length
    return longest


def min_duration(
    timeline: Timeline[Ivl],
    start: int,
    end: int,
) -> Ivl | None:
    """Return the shortest interval within the slice."""
    if start > end:
        return None

    shortest: Ivl | None = None
    shortest_len: int | None = None
    for event in timeline[start:end]:
        # Skip unbounded intervals (shouldn't happen with finite bounds, but be safe)
        if event.start is None or event.end is None:
            continue
        length = event.end - event.start + 1
        if shortest_len is None or length < shortest_len:
            shortest = event
            shortest_len = length
    return shortest


def count_intervals(
    timeline: Timeline[Ivl],
    start: int,
    end: int,
) -> int:
    """Count intervals returned by the timeline over the specified bounds."""
    if start > end:
        return 0
    return sum(1 for _ in timeline[start:end])


def coverage_ratio(
    timeline: Timeline[Ivl],
    start: int,
    end: int,
) -> float:
    """Return the fraction of the window covered by events (between 0 and 1)."""
    if start > end:
        return 0.0
    span = end - start + 1
    if span <= 0:
        return 0.0
    return total_duration(timeline, start, end) / span
