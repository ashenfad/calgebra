"""In-memory mutable timeline implementation.

This module provides MemoryTimeline, a simple mutable timeline backed by
in-memory storage. It's useful for testing, prototyping, and ephemeral calendars.
"""

import bisect
import heapq
from collections.abc import Iterable
from dataclasses import replace
from typing import Any, Literal, cast

from sortedcontainers import SortedList
from typing_extensions import override

from calgebra.interval import Interval
from calgebra.mutable import MutableTimeline, WriteResult
from calgebra.recurrence import RecurringPattern


def _interval_sort_key(interval: Interval) -> tuple[int | float, int | float]:
    """Key function for sorting intervals by start and end."""
    return (interval.finite_start, interval.finite_end)


def _get_recurrence_params(
    pattern: RecurringPattern[Interval],
) -> dict[str, Any]:
    """Get recurrence parameters from a pattern.

    Returns a dict with day, week, day_of_month, month for use in creating
    a new RecurringPattern with merged metadata.
    """
    params: dict[str, Any] = {}

    if pattern.day is not None:
        params["day"] = pattern.day
    if pattern.week is not None:
        params["week"] = pattern.week
    if pattern.day_of_month is not None:
        params["day_of_month"] = pattern.day_of_month
    if pattern.month is not None:
        params["month"] = pattern.month

    return params


class MemoryTimeline(MutableTimeline[Interval]):
    """In-memory mutable timeline backed by composite storage.

    Stores recurring patterns and static intervals separately, composing them
    via union when fetching. This preserves symbolic recurrence rules.

    Attributes:
        _recurring_patterns: List of recurring pattern timelines
        _static_intervals: List of individual interval objects
    """

    def __init__(self, intervals: Iterable[Interval] = ()) -> None:
        """Initialize an empty or pre-populated memory timeline.

        Args:
            intervals: Optional initial intervals to add (creates static storage)
        """
        # Store recurring patterns with their unique IDs
        # Format: list of (recurring_event_id, RecurringPattern) tuples
        self._recurring_patterns: list[tuple[str, RecurringPattern[Interval]]] = []
        # Use SortedList for O(log n) inserts (stays sorted automatically)
        ivls = SortedList(key=_interval_sort_key)
        self._static_intervals: list[Interval] = ivls

        # Add any initial intervals
        for interval in intervals:
            # Consume the WriteResult iterator
            list(self._add_interval(interval, vars(interval)))

    @override
    def fetch(
        self, start: int | None, end: int | None, *, reverse: bool = False
    ) -> Iterable[Interval]:
        """Fetch intervals by unioning recurring patterns and static storage.

        Args:
            start: Start timestamp (inclusive), None for unbounded
            end: End timestamp (exclusive), None for unbounded
            reverse: If True, yield intervals in reverse chronological order

        Returns:
            Iterator of intervals in the given range
        """
        iterators: list[Iterable[Interval]] = []

        # 1. Recurring patterns
        for _, pattern in self._recurring_patterns:
            iterators.append(pattern.fetch(start, end, reverse=reverse))

        # 2. Static intervals (optimized fetch)
        if self._static_intervals:
            iterators.append(self._fetch_static(start, end, reverse=reverse))

        # Merge all streams while maintaining sort order
        # Note: heapq.merge expects sorted inputs, which we guarantee
        if reverse:
            return heapq.merge(
                *iterators, key=lambda x: (-x.finite_start, -x.finite_end)
            )
        return heapq.merge(*iterators, key=lambda x: x.finite_start)

    def _fetch_static(
        self, start: int | None, end: int | None, reverse: bool = False
    ) -> Iterable[Interval]:
        """Fetch from static intervals with binary search optimization."""
        if not self._static_intervals:
            return

        # Optimization: Binary search for the end bound
        # Intervals starting after query end can be skipped
        end_idx = len(self._static_intervals)
        if end is not None:
            # Find first interval with finite_start > end
            # SortedList supports bisect_right directly, but we use bisect module
            # for compatibility with standard lists if we swap implementation
            end_idx = bisect.bisect_right(
                self._static_intervals, end, key=lambda interval: interval.finite_start
            )

        # Collect matching intervals
        matching: list[Interval] = []
        for i in range(end_idx):
            interval = self._static_intervals[i]

            # Skip intervals that end before our start bound
            if start is not None and interval.finite_end <= start:
                continue

            matching.append(interval)

        if reverse:
            yield from reversed(matching)
        else:
            yield from matching

    @override
    def _add_interval(
        self, interval: Interval, metadata: dict[str, Any]
    ) -> list[WriteResult]:
        """Add a single interval to static storage.

        Args:
            interval: The interval to add
            metadata: Merged metadata (interval fields + kwargs)

        Returns:
            List containing single WriteResult
        """
        # For base Interval class, we can't add extra fields like 'id'
        # Just store the interval as-is
        # Subclasses with id field would work with replace()

        # Try to update with safe metadata
        if metadata:
            # Apply metadata overrides to the interval
            try:
                interval_with_metadata = replace(interval, **metadata)
            except TypeError:
                # If replace fails (e.g. invalid fields), just use the original
                # but maybe we should warn or error? For now, silent fallback.
                interval_with_metadata = interval
        else:
            interval_with_metadata = interval

        cast(SortedList, self._static_intervals).add(interval_with_metadata)

        return [WriteResult(success=True, event=interval_with_metadata, error=None)]

    @override
    def _add_recurring(
        self, pattern: RecurringPattern[Interval], metadata: dict[str, Any]
    ) -> list[WriteResult]:
        """Add a recurring pattern to recurring storage.

        Args:
            pattern: RecurringPattern with rrule and optional metadata
            metadata: Additional metadata to override pattern's metadata

        Returns:
            List containing single WriteResult
        """
        # Use pattern's object ID as recurring_event_id
        recurring_id = str(id(pattern))

        # Merge metadata with recurring_event_id (if interval class supports it)
        merged_metadata = {**pattern.metadata, **metadata}

        # Check if interval_class has recurring_event_id field
        # Only add it if the class supports it (not base Interval)
        interval_fields: set[str] = set()
        if hasattr(pattern.interval_class, "__annotations__"):
            interval_fields = set(pattern.interval_class.__annotations__.keys())
        if "recurring_event_id" in interval_fields:
            merged_metadata["recurring_event_id"] = recurring_id

        # Create new pattern with merged metadata
        enriched_pattern = RecurringPattern(
            freq=cast(Literal["daily", "weekly", "monthly", "yearly"], pattern.freq),
            interval=pattern.interval,
            duration=pattern.duration_seconds,
            # Preserve anchored start if provided; otherwise retain time-of-day start
            start=pattern.anchor_timestamp or pattern.start_seconds,
            tz=str(pattern.zone),
            interval_class=pattern.interval_class,
            exdates=pattern.exdates,
            **_get_recurrence_params(pattern),
            **merged_metadata,
        )

        # Store pattern with its ID
        self._recurring_patterns.append((recurring_id, enriched_pattern))

        return [WriteResult(success=True, event=None, error=None)]

    @override
    def _remove_interval(self, interval: Interval) -> list[WriteResult]:
        """Remove a single interval from the static list."""
        recurring_id = getattr(interval, "recurring_event_id", None)
        if recurring_id:
            return self._remove_recurring_instance(interval)

        try:
            self._static_intervals.remove(interval)
            return [WriteResult(success=True, event=interval, error=None)]
        except ValueError:
            return [
                WriteResult(
                    success=False,
                    event=interval,
                    error=ValueError(f"Interval {interval} not found in timeline"),
                )
            ]

    @override
    def _remove_series(self, interval: Interval) -> list[WriteResult]:
        """Remove a recurring series by recurring_event_id.

        Args:
            interval: An interval from the series to remove

        Returns:
            List containing WriteResult

        Note:
            For MemoryTimeline, this removes the entire recurring pattern
            that matches the recurring_event_id.
        """
        recurring_id = getattr(interval, "recurring_event_id", None)
        if recurring_id is None:
            # Not a recurring event - treat as single interval removal
            return self._remove_interval(interval)

        # Find and remove the recurring pattern by ID
        for i, (pattern_id, _) in enumerate(self._recurring_patterns):
            if pattern_id == recurring_id:
                self._recurring_patterns.pop(i)
                return [
                    WriteResult(
                        success=True,
                        event=None,  # Could return the pattern itself if needed
                        error=None,
                    )
                ]

        # Pattern not found
        return [
            WriteResult(
                success=False,
                event=None,
                error=ValueError(
                    f"Recurring series with ID '{recurring_id}' not found in timeline"
                ),
            )
        ]

    def _remove_recurring_instance(self, interval: Interval) -> list[WriteResult]:
        """Remove a single instance of a recurring pattern via exdate."""
        recurring_id = getattr(interval, "recurring_event_id", None)
        if recurring_id is None:
            return [
                WriteResult(
                    success=False,
                    event=interval,
                    error=ValueError("Interval does not have recurring_event_id"),
                )
            ]

        # Find the pattern
        for stored_id, pattern in self._recurring_patterns:
            if stored_id == recurring_id:
                # Add start time to exdates
                # Note: We modify the pattern in-place. Since RecurringPattern
                # is mutable (it has exdates set), this works.

                # Check if start is finite
                if interval.start is None:
                    return [
                        WriteResult(
                            success=False,
                            event=interval,
                            error=ValueError(
                                "Cannot remove unbounded interval instance"
                            ),
                        )
                    ]

                pattern.exdates.add(interval.start)
                return [WriteResult(success=True, event=interval, error=None)]

        return [
            WriteResult(
                success=False,
                event=interval,
                error=ValueError(f"Recurring pattern {recurring_id} not found"),
            )
        ]

    @override
    def _remove_many(self, intervals: Iterable[Interval]) -> list[WriteResult]:
        """Remove multiple intervals.

        For MemoryTimeline, this just loops through and calls _remove_interval.
        No special batch optimization needed since we're using in-memory structures.
        """
        results = []
        for interval in intervals:
            results.extend(self._remove_interval(interval))
        return results

    @override
    def _remove_many_series(self, intervals: Iterable[Interval]) -> list[WriteResult]:
        """Remove multiple recurring series.

        For MemoryTimeline, this just loops through and calls _remove_series.
        No special batch optimization needed since we're using in-memory structures.
        """
        results = []
        for interval in intervals:
            results.extend(self._remove_series(interval))
        return results


def timeline(*intervals: Interval) -> MemoryTimeline:
    """Create a mutable timeline from a collection of intervals.

    This is a convenience function for creating in-memory timelines without needing to
    instantiate MemoryTimeline directly. The returned timeline is mutable and sorts
    intervals by (start, end).

    Args:
        *intervals: Variable number of interval objects

    Returns:
        MemoryTimeline containing the provided intervals

    Example:
        >>> from calgebra.mutable.memory import timeline
        >>> from calgebra import Interval
        >>>
        >>> # Create a simple timeline
        >>> my_timeline = timeline(
        ...     Interval(start=1000, end=2000),
        ...     Interval(start=5000, end=6000),
        ... )
        >>>
        >>> # Can add more intervals later
        >>> list(my_timeline.add(Interval(start=3000, end=4000)))
        >>>
        >>> # Works with subclassed intervals too
        >>> from dataclasses import dataclass
        >>> @dataclass(frozen=True, kw_only=True)
        ... class Event(Interval):
        ...     title: str
        >>>
        >>> events = timeline(
        ...     Event(start=1000, end=2000, title="Meeting"),
        ...     Event(start=5000, end=6000, title="Lunch"),
        ... )
    """
    return MemoryTimeline(intervals)
