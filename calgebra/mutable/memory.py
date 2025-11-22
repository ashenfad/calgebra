"""In-memory mutable timeline implementation.

This module provides MemoryTimeline, a simple mutable timeline backed by
in-memory storage. It's useful for testing, prototyping, and ephemeral calendars.
"""

import bisect
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any, Generic

from calgebra.mutable import MutableTimeline, WriteResult
from calgebra.core import Union, Timeline
from calgebra.interval import Interval, IvlOut
from calgebra.recurrence import RecurringPattern


class _StaticTimeline(Timeline[IvlOut], Generic[IvlOut]):
    """Timeline backed by a static collection of intervals.

    Internal helper class used by MemoryTimeline for efficient querying.
    """

    def __init__(self, intervals: Sequence[IvlOut]):
        # Use finite properties for sorting to handle None (unbounded) values
        self._intervals: tuple[IvlOut, ...] = tuple(
            sorted(intervals, key=lambda e: (e.finite_start, e.finite_end))
        )

        # Build max-end prefix array for efficient query pruning
        # max_end_prefix[i] = max(interval.finite_end for interval in intervals[:i+1])
        self._max_end_prefix: list[int] = []
        max_so_far = float("-inf")
        for interval in self._intervals:
            max_so_far = max(max_so_far, interval.finite_end)
            self._max_end_prefix.append(int(max_so_far))

    def fetch(self, start: int | None, end: int | None) -> Iterable[IvlOut]:
        # Use binary search to narrow the range of intervals to check
        # Intervals are sorted by (finite_start, finite_end)

        if not self._intervals:
            return

        start_idx = 0
        end_idx = len(self._intervals)

        # Use max-end prefix to skip intervals that definitely can't overlap
        # Find first position where max_end >= start (all before can be skipped)
        if start is not None:
            start_idx = bisect.bisect_left(self._max_end_prefix, start)

        # Use binary search on starts to find where to stop iterating
        # Find first interval with finite_start > end
        if end is not None:
            end_idx = bisect.bisect_right(
                self._intervals, end, key=lambda interval: interval.finite_start
            )

        # Iterate only through the narrowed range
        for interval in self._intervals[start_idx:end_idx]:
            # Final filter: skip intervals that end before our start bound
            if start is not None and interval.finite_end <= start:
                continue
            yield interval


class MemoryTimeline(MutableTimeline[Interval]):
    """In-memory mutable timeline backed by composite storage.

    Stores recurring patterns and static intervals separately, composing them
    via union when fetching. This preserves symbolic recurrence rules.

    Attributes:
        _recurring_patterns: List of recurring pattern timelines
        _static_intervals: List of individual interval objects
        _next_id: Counter for assigning unique IDs to static intervals
    """

    def __init__(self, intervals: Iterable[Interval] = ()) -> None:
        """Initialize an empty or pre-populated memory timeline.

        Args:
            intervals: Optional initial intervals to add (creates static storage)
        """
        self._recurring_patterns: list[RecurringPattern] = []
        self._static_intervals: list[Interval] = []
        self._next_id: int = 0

        # Add any initial intervals
        for interval in intervals:
            # Consume the WriteResult iterator
            list(self._add_interval(interval, vars(interval)))

    def fetch(self, start: int | None, end: int | None) -> Iterable[Interval]:
        """Fetch intervals by unioning recurring patterns and static storage.

        Args:
            start: Start timestamp (inclusive), None for unbounded
            end: End timestamp (exclusive), None for unbounded

        Returns:
            Iterator of intervals in the given range
        """
        parts: list[RecurringPattern | _StaticTimeline] = []

        # Add all recurring patterns
        parts.extend(self._recurring_patterns)

        # Add static timeline if non-empty
        if self._static_intervals:
            parts.append(_StaticTimeline(self._static_intervals))

        if not parts:
            return iter([])

        # Union everything together
        if len(parts) == 1:
            return parts[0].fetch(start, end)
        else:
            combined = Union(*parts)
            return combined.fetch(start, end)

    def _add_interval(
        self, interval: Interval, metadata: dict[str, Any]
    ) -> Iterable[WriteResult]:
        """Add a single interval to static storage.

        Args:
            interval: The interval to add
            metadata: Merged metadata (interval fields + kwargs)

        Yields:
            WriteResult indicating success
        """
        # For base Interval class, we can't add extra fields like 'id'
        # Just store the interval as-is
        # Subclasses with id field would work with replace()
        
        # Filter metadata to only include fields the interval class supports
        interval_fields = set(vars(interval).keys())
        safe_metadata = {k: v for k, v in metadata.items() if k in interval_fields}
        
        # Try to update with safe metadata
        try:
            if safe_metadata != vars(interval):
                interval_with_metadata = replace(interval, **safe_metadata)
            else:
                interval_with_metadata = interval
        except (TypeError, ValueError):
            # If replace fails, just use the original interval
            interval_with_metadata = interval

        self._static_intervals.append(interval_with_metadata)

        yield WriteResult(
            success=True, event=interval_with_metadata, error=None
        )

    def _add_recurring(
        self, pattern: "RecurringPattern", metadata: dict[str, Any]
    ) -> Iterable[WriteResult]:
        """Add a recurring pattern to recurring storage.

        Args:
            pattern: RecurringPattern with rrule and optional metadata
            metadata: Additional metadata to override pattern's metadata

        Yields:
            WriteResult indicating success
        """
        # If metadata is provided, create a new pattern with merged metadata
        # Pattern's own metadata + override metadata
        if metadata:
            # Merge pattern's metadata with additional overrides
            from calgebra.recurrence import RecurringPattern
            
            merged_metadata = {**pattern._metadata, **metadata}
            
            # Create new pattern with merged metadata
            enriched_pattern = RecurringPattern(
                freq=pattern.freq,
                interval=pattern.interval,
                duration=pattern.duration_seconds,
                tz=str(pattern.zone),
                interval_class=pattern._interval_class,
                **merged_metadata
            )
            self._recurring_patterns.append(enriched_pattern)
        else:
            # Use pattern as-is
            self._recurring_patterns.append(pattern)

        yield WriteResult(success=True, event=None, error=None)

    def _remove_interval(self, interval: Interval) -> Iterable[WriteResult]:
        """Remove a specific interval from static storage.

        Args:
            interval: The interval to remove

        Yields:
            WriteResult indicating success or failure
        """
        # Try to match by ID if available
        if hasattr(interval, "id") and interval.id is not None:
            for i, stored in enumerate(self._static_intervals):
                if hasattr(stored, "id") and stored.id == interval.id:
                    removed = self._static_intervals.pop(i)
                    yield WriteResult(success=True, event=removed, error=None)
                    return
        
        # Otherwise, try to match by equality
        try:
            idx = self._static_intervals.index(interval)
            removed = self._static_intervals.pop(idx)
            yield WriteResult(success=True, event=removed, error=None)
            return
        except ValueError:
            pass

        # Not found
        yield WriteResult(
            success=False,
            event=None,
            error=ValueError(f"Interval not found in memory timeline"),
        )

    def _remove_series(self, interval: Interval) -> Iterable[WriteResult]:
        """Remove a recurring series by recurring_event_id.

        Args:
            interval: An interval from the series to remove

        Yields:
            WriteResult indicating success or failure

        Note:
            For MemoryTimeline, this removes the entire recurring pattern
            that matches the recurring_event_id.
        """
        if not hasattr(interval, "recurring_event_id"):
            # Not a recurring event - treat as single interval removal
            yield from self._remove_interval(interval)
            return

        recurring_id = interval.recurring_event_id
        if recurring_id is None:
            # No recurring ID - treat as single interval removal
            yield from self._remove_interval(interval)
            return

        # Find and remove the recurring pattern
        # This is simplified - real implementation would need to track recurring IDs
        yield WriteResult(
            success=False,
            event=None,
            error=NotImplementedError(
                "Removing recurring series not yet implemented for MemoryTimeline"
            ),
        )

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
