"""Mutable timeline support for write operations.

This module provides the abstract base class for timelines that support
writing events, along with implementations for different backends.
"""

from abc import abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Generic

from calgebra.core import Timeline
from calgebra.interval import Interval, IvlOut
from calgebra.recurrence import RecurringPattern


@dataclass(frozen=True)
class WriteResult:
    """Result of a write operation (add/remove).

    Attributes:
        success: True if operation succeeded, False otherwise
        event: The written event (with backend ID) if successful, None if failed
        error: The exception that occurred if failed, None if successful
    """

    success: bool
    event: Interval | None
    error: Exception | None


class MutableTimeline(Timeline[IvlOut], Generic[IvlOut]):
    """Abstract base class for timelines that support write operations.

    Provides generic dispatch logic for adding and removing events, with
    backend-specific implementations handling the actual writes.
    """

    def add(
        self,
        item: "Interval | Iterable[Interval] | RecurringPattern[IvlOut]",
        **metadata: Any,
    ) -> list[WriteResult]:
        """Add events to this timeline.

        Args:
            item: Single interval, iterable of intervals, or timeline to add
            **metadata: Backend-specific metadata (e.g., summary, attendees)

        Returns:
            List of WriteResult objects, one per item written

        Raises:
            ValueError: If passed a Timeline (not RecurringPattern)

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
        match item:
            case Interval():
                return self._add_interval(item, {**vars(item), **metadata})
            case RecurringPattern():
                return self._add_recurring(item, metadata)
            case _ if isinstance(item, Timeline):
                raise ValueError(
                    "Cannot add Timeline directly (only RecurringPattern is "
                    "supported)."
                )
            case _:
                return self._add_many(item, metadata)

    def remove(self, items: Interval | Iterable[Interval]) -> list[WriteResult]:
        """Remove specific event instances by ID.

        Args:
            items: Single interval or iterable of intervals to remove

        Returns:
            List of WriteResult objects

        Note:
            This removes individual instances. To remove an entire recurring series,
            use remove_series() instead.
        """
        match items:
            case Interval():
                return self._remove_interval(items)
            case _:
                return self._remove_many(items)

    def remove_series(self, items: Interval | Iterable[Interval]) -> list[WriteResult]:
        """Remove entire recurring series by recurring_event_id.

        Args:
            items: Single interval or iterable of intervals to remove series for

        Returns:
            List of WriteResult objects

        Note:
            For non-recurring events, this behaves the same as remove().
        """
        match items:
            case Interval():
                return self._remove_series(items)
            case _:
                return self._remove_many_series(items)

    @abstractmethod
    def _add_interval(
        self, interval: Interval, metadata: dict[str, Any]
    ) -> list[WriteResult]:
        """Backend-specific: write a single interval.

        Args:
            interval: The interval to write
            metadata: Merged metadata (interval fields + kwargs)

        Returns:
            List containing a single WriteResult
        """
        pass

    @abstractmethod
    def _add_recurring(
        self, pattern: RecurringPattern[IvlOut], metadata: dict[str, Any]
    ) -> list[WriteResult]:
        """Add a recurring pattern to backend storage.

        Args:
            pattern: RecurringPattern with rrule and optional metadata
            metadata: Additional metadata to apply (overrides pattern's metadata)

        Returns:
            List containing WriteResult for the recurring series
        """
        pass

    def _add_many(
        self, intervals: Iterable[Interval], metadata: dict[str, Any]
    ) -> list[WriteResult]:
        """Backend-specific: write multiple intervals.

        Args:
            intervals: Iterable of intervals to write
            metadata: Metadata to apply to all intervals

        Returns:
            List of WriteResult objects
        """
        # Default implementation: loop and call _add_interval
        # Backends can override for batch APIs
        results = []
        for interval in intervals:
            merged_metadata = {**vars(interval), **metadata}
            results.extend(self._add_interval(interval, merged_metadata))
        return results

    @abstractmethod
    def _remove_interval(self, interval: Interval) -> list[WriteResult]:
        """Backend-specific: remove a single interval by ID.

        Args:
            interval: The interval to remove

        Returns:
            List containing a single WriteResult
        """
        pass

    @abstractmethod
    def _remove_series(self, interval: Interval) -> list[WriteResult]:
        """Backend-specific: remove entire recurring series.

        Args:
            interval: An interval from the series to remove

        Returns:
            List containing a single WriteResult
        """
        pass

    def _remove_many(self, intervals: Iterable[Interval]) -> list[WriteResult]:
        """Backend-specific: remove multiple intervals.

        Args:
            intervals: Iterable of intervals to remove

        Returns:
            List of WriteResult objects

        Note:
            Default implementation loops and calls _remove_interval for each.
            Backends can override for batch APIs.
        """
        results = []
        for interval in intervals:
            results.extend(self._remove_interval(interval))
        return results

    def _remove_many_series(self, intervals: Iterable[Interval]) -> list[WriteResult]:
        """Backend-specific: remove multiple recurring series.

        Args:
            intervals: Iterable of intervals to remove series for

        Returns:
            List of WriteResult objects

        Note:
            Default implementation loops and calls _remove_series for each.
            Backends can override for batch APIs.
        """
        results = []
        for interval in intervals:
            results.extend(self._remove_series(interval))
        return results


__all__ = ["MutableTimeline", "WriteResult"]

# Google Calendar integration (optional dependency)
try:
    from calgebra.mutable.gcsa import (  # noqa: F401
        Event,
        GoogleCalendarTimeline,
        Reminder,
        calendars,
    )

    __all__.extend(["Event", "GoogleCalendarTimeline", "Reminder", "calendars"])
except ImportError:
    # gcsa not installed, skip exports
    pass
