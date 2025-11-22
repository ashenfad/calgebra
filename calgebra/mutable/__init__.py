"""Mutable timeline support for write operations.

This module provides the abstract base class for timelines that support
writing events, along with implementations for different backends.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from calgebra.recurrence import RecurringPattern

from calgebra.interval import Interval, IvlOut
from calgebra.core import Timeline


@dataclass(frozen=True)
class WriteResult:
    """Result of a write operation (add/remove).

    Attributes:
        success: True if the operation succeeded, False otherwise
        event: The written event (with backend-assigned ID) if successful, None if failed
        error: The exception that occurred if failed, None if successful
    """

    success: bool
    event: Interval | None
    error: Exception | None


class MutableTimeline(Timeline[IvlOut], ABC):
    """Abstract base class for timelines that support write operations.

    Provides generic dispatch logic for adding and removing events, with
    backend-specific implementations handling the actual writes.
    """

    def add(
        self,
        item: "Interval | Iterable[Interval] | RecurringPattern",
        **metadata: Any
    ) -> Iterable[WriteResult]:
        """Add events to this timeline.

        Args:
            item: Single interval, iterable of intervals, or timeline to add
            **metadata: Backend-specific metadata (e.g., summary, description, attendees)

        Returns:
            Iterator of WriteResult objects, one per item written

        Raises:
            ValueError: If passed a Timeline (not RecurringPattern) - must slice explicitly

        Examples:
            # Add single event with metadata
            results = cal.add(
                Interval(start=..., end=...),
                summary="Meeting",
                attendees=["alice@example.com"]
            )

            # Add symbolic pattern
            pattern = recurring(freq="weekly", day="monday", ...)
            results = cal.add(pattern, summary="Weekly Standup")

            # Add explicit slice (unroll)
            results = cal.add(
                complex_query[start:end],
                summary="Office Hours"
            )
        """
        # Single interval
        if isinstance(item, Interval):
            # Merge interval's own fields with metadata kwargs (kwargs override)
            merged_metadata = {**vars(item), **metadata}
            yield from self._add_interval(item, merged_metadata)

        # RecurringPattern (symbolic)
        else:
            # Import at runtime to avoid circular dependency
            from calgebra.recurrence import RecurringPattern

            if isinstance(item, RecurringPattern):
                yield from self._add_recurring(item, metadata)

            # Iterable of intervals or unsupported Timeline
            # Check if it's a Timeline (but not RecurringPattern)
            elif isinstance(item, Timeline):
                raise ValueError(
                    "Cannot add Timeline directly (only RecurringPattern is supported).\\n"
                    "This timeline has been composed/transformed and lost symbolic representation.\\n\\n"
                    "To add it, slice with explicit bounds to unroll into intervals:\\n"
                    "  cal.add(timeline[start:end], summary=...)\\n\\n"
                    "Or use RecurringPattern directly for recurring events:\\n"
                    "  from calgebra import recurring\\n"
                    "  cal.add(recurring(freq='weekly', day='monday'), summary='Standup')"
                )

            # Iterable of intervals (else)
            else:
                yield from self._add_many(item, metadata)

    def remove(
        self, items: Interval | Iterable[Interval]
    ) -> Iterable[WriteResult]:
        """Remove specific event instances by ID.

        Args:
            items: Single interval or iterable of intervals to remove

        Returns:
            Iterator of WriteResult objects

        Note:
            This removes individual instances. To remove an entire recurring series,
            use remove_series() instead.
        """
        if isinstance(items, Interval):
            yield from self._remove_interval(items)
        else:
            for item in items:
                yield from self._remove_interval(item)

    def remove_series(
        self, items: Interval | Iterable[Interval]
    ) -> Iterable[WriteResult]:
        """Remove entire recurring series by recurring_event_id.

        Args:
            items: Single interval or iterable of intervals whose series should be deleted

        Returns:
            Iterator of WriteResult objects

        Note:
            For non-recurring events, this behaves the same as remove().
        """
        if isinstance(items, Interval):
            yield from self._remove_series(items)
        else:
            for item in items:
                yield from self._remove_series(item)

    @abstractmethod
    def _add_interval(
        self, interval: Interval, metadata: dict[str, Any]
    ) -> Iterable[WriteResult]:
        """Backend-specific: write a single interval.

        Args:
            interval: The interval to write
            metadata: Merged metadata (interval fields + kwargs)

        Returns:
            Iterator yielding a single WriteResult
        """
        pass

    @abstractmethod
    def _add_recurring(
        self, pattern: "RecurringPattern", metadata: dict[str, Any]
    ) -> Iterable[WriteResult]:
        """Add a recurring pattern to backend storage.

        Args:
            pattern: RecurringPattern with rrule and optional metadata
            metadata: Additional metadata to apply (overrides pattern's metadata)

        Yields:
            WriteResult for the recurring series
        """
        pass

    def _add_many(
        self, intervals: Iterable[Interval], metadata: dict[str, Any]
    ) -> Iterable[WriteResult]:
        """Backend-specific: write multiple intervals.

        Args:
            intervals: Iterable of intervals to write
            metadata: Metadata to apply to all intervals

        Returns:
            Iterator of WriteResult objects
        """
        # Default implementation: loop and call _add_interval
        # Backends can override for batch APIs
        for interval in intervals:
            merged_metadata = {**vars(interval), **metadata}
            yield from self._add_interval(interval, merged_metadata)

    @abstractmethod
    def _remove_interval(self, interval: Interval) -> Iterable[WriteResult]:
        """Backend-specific: remove a single interval by ID.

        Args:
            interval: The interval to remove

        Returns:
            Iterator yielding a single WriteResult
        """
        pass

    @abstractmethod
    def _remove_series(self, interval: Interval) -> Iterable[WriteResult]:
        """Backend-specific: remove entire recurring series.

        Args:
            interval: An interval from the series to remove

        Returns:
            Iterator yielding a single WriteResult
        """
        pass


__all__ = ["MutableTimeline", "WriteResult"]
