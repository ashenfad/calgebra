"""Transformation operations on timelines.

This module provides operations that modify the shape or structure of intervals
while preserving their identity and metadata.
"""

from collections.abc import Iterable
from dataclasses import replace
from typing import Generic, TypeVar

from typing_extensions import override

from .core import Timeline
from .interval import Interval

Ivl = TypeVar("Ivl", bound=Interval)


class _Buffered(Timeline[Ivl], Generic[Ivl]):
    """Timeline with buffered intervals."""

    def __init__(self, source: Timeline[Ivl], before: int, after: int):
        self.source: Timeline[Ivl] = source
        self.before: int = before
        self.after: int = after

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Ivl]:
        for interval in self.source.fetch(start, end):
            # Handle unbounded intervals (None values)
            buffered_start = (
                interval.start - self.before if interval.start is not None else None
            )
            buffered_end = (
                interval.end + self.after if interval.end is not None else None
            )
            yield replace(
                interval,
                start=buffered_start,
                end=buffered_end,
            )


class _MergedWithin(Timeline[Ivl], Generic[Ivl]):
    """Timeline with nearby intervals merged."""

    def __init__(self, source: Timeline[Ivl], gap: int):
        self.source: Timeline[Ivl] = source
        self.gap: int = gap

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Ivl]:
        current: Ivl | None = None

        for interval in self.source.fetch(start, end):
            if current is None:
                current = interval
            else:
                if current.end is None or interval.start is None:
                    can_merge = True
                else:
                    gap = interval.start - current.end - 1
                    can_merge = gap <= self.gap

                if can_merge:
                    # Merge: extend current to include the furthest end
                    new_end = current.end
                    if new_end is None or interval.end is None:
                        new_end = None
                    elif interval.end > new_end:
                        new_end = interval.end
                    current = replace(current, end=new_end)
                else:
                    # Gap too large, emit current and start new group
                    yield current
                    current = interval

        if current is not None:
            yield current


def buffer(
    timeline: Timeline[Ivl],
    *,
    before: int = 0,
    after: int = 0,
) -> Timeline[Ivl]:
    """Add buffer time before and/or after each interval.

    Useful for representing travel time, setup/teardown, or slack time
    around events. Each interval is expanded by the specified amounts
    without merging overlaps.

    Args:
        timeline: Source timeline to add buffers to
        before: Seconds to add before each interval start (default: 0, must be >= 0)
        after: Seconds to add after each interval end (default: 0, must be >= 0)

    Returns:
        Timeline with buffered intervals preserving original metadata

    Raises:
        ValueError: If before or after are negative

    Example:
        >>> from calgebra import buffer, HOUR, MINUTE
        >>>
        >>> # Flights need 2 hours of pre-travel time
        >>> blocked = buffer(flights, before=2*HOUR)
        >>>
        >>> # Meetings need 15 min buffer on each side
        >>> busy = buffer(meetings, before=15*MINUTE, after=15*MINUTE)
        >>>
        >>> # Check for conflicts with expanded times
        >>> conflicts = blocked & work_calendar
    """
    if before < 0:
        raise ValueError(f"before must be non-negative, got {before}.")
    if after < 0:
        raise ValueError(f"after must be non-negative, got {after}.")
    return _Buffered(timeline, before, after)


def merge_within(
    timeline: Timeline[Ivl],
    *,
    gap: int,
) -> Timeline[Ivl]:
    """Merge intervals separated by at most `gap` seconds.

    Coalesces intervals that are close together in time, treating them as a
    single continuous period. Intervals separated by more than `gap` seconds
    remain distinct. When merging, metadata from the first interval in each
    group is preserved.

    Useful for clustering related events (alarms into incidents) or grouping
    closely-scheduled activities into blocks.

    Args:
        timeline: Source timeline to merge
        gap: Maximum gap (in seconds) between intervals to merge across

    Returns:
        Timeline with nearby intervals merged, preserving first interval's metadata

    Example:
        >>> from calgebra import merge_within, MINUTE
        >>>
        >>> # Treat alarms within 15 min as one incident
        >>> incidents = merge_within(alarms, gap=15*MINUTE)
        >>>
        >>> # Group closely-scheduled meetings into busy blocks
        >>> busy_blocks = merge_within(meetings, gap=5*MINUTE)
        >>>
        >>> # Combine with other operations
        >>> daily_incidents = incidents & day_of_week("monday")

    Note:
        Unlike flatten(), merge_within() preserves metadata from the first
        interval in each merged group. Use flatten() when you don't need
        to preserve metadata and want all adjacent/overlapping intervals
        coalesced regardless of gap size.
    """
    return _MergedWithin(timeline, gap)
