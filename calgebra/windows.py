"""Built-in time window generators for common patterns.

These timelines generate intervals for common recurring patterns like
weekdays, weekends, and business hours without requiring external dependencies.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import override
from zoneinfo import ZoneInfo

from calgebra.core import Timeline
from calgebra.interval import Interval


class _DailyPattern(Timeline[Interval]):
    """Base class for timelines that generate daily intervals based on patterns."""

    def __init__(self, tz: str = "UTC"):
        self.zone: ZoneInfo = ZoneInfo(tz)

    def _should_include_day(self, dt: datetime) -> bool:
        """Return True if this day should be included in the timeline."""
        raise NotImplementedError

    def _day_window(self, dt: datetime) -> tuple[datetime, datetime]:
        """Return (start, end) datetime for the interval on this day."""
        raise NotImplementedError

    def _fetch_name(self) -> str:
        """Return the name of this pattern for error messages."""
        return self.__class__.__name__

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Interval]:
        """Yield intervals matching the pattern in the query range."""
        if start is None or end is None:
            raise ValueError(
                f"{self._fetch_name()} requires finite start and end bounds"
            )

        current = datetime.fromtimestamp(start, tz=self.zone)
        end_dt = datetime.fromtimestamp(end, tz=self.zone)

        # Normalize to start of day
        current = current.replace(hour=0, minute=0, second=0, microsecond=0)

        while current <= end_dt:
            if self._should_include_day(current):
                window_start, window_end = self._day_window(current)

                # Clamp to query bounds
                interval_start = max(int(window_start.timestamp()), start)
                interval_end = min(int(window_end.timestamp()), end)

                if interval_start <= interval_end:
                    yield Interval(start=interval_start, end=interval_end)

            # Move to next day
            current += timedelta(days=1)


class Weekdays(_DailyPattern):
    """Generate all weekday time (Monday-Friday, all hours) in a timezone."""

    def __init__(self, tz: str = "UTC"):
        """
        Initialize weekdays timeline.

        Args:
            tz: IANA timezone name (e.g., "UTC", "US/Pacific")
        """
        super().__init__(tz)

    @override
    def _should_include_day(self, dt: datetime) -> bool:
        # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
        return dt.weekday() < 5

    @override
    def _day_window(self, dt: datetime) -> tuple[datetime, datetime]:
        # Full day
        return dt, dt.replace(hour=23, minute=59, second=59)

    @override
    def _fetch_name(self) -> str:
        return "Weekdays"


class Weekends(_DailyPattern):
    """Generate all weekend time (Saturday-Sunday, all hours) in a timezone."""

    def __init__(self, tz: str = "UTC"):
        """
        Initialize weekends timeline.

        Args:
            tz: IANA timezone name (e.g., "UTC", "US/Pacific")
        """
        super().__init__(tz)

    @override
    def _should_include_day(self, dt: datetime) -> bool:
        # 5=Saturday, 6=Sunday
        return dt.weekday() >= 5

    @override
    def _day_window(self, dt: datetime) -> tuple[datetime, datetime]:
        # Full day
        return dt, dt.replace(hour=23, minute=59, second=59)

    @override
    def _fetch_name(self) -> str:
        return "Weekends"


class BusinessHours(_DailyPattern):
    """Generate business hours (weekdays, specific hours) in a timezone."""

    def __init__(self, tz: str = "UTC", start_hour: int = 9, end_hour: int = 17):
        """
        Initialize business hours timeline.

        Args:
            tz: IANA timezone name (e.g., "UTC", "US/Pacific")
            start_hour: Start hour (0-23), inclusive
            end_hour: End hour (0-23), exclusive (e.g., 17 means until 16:59:59)
        """
        if not (0 <= start_hour < 24):
            raise ValueError(f"start_hour must be 0-23, got {start_hour}")
        if not (0 <= end_hour <= 24):
            raise ValueError(f"end_hour must be 0-24, got {end_hour}")
        if start_hour >= end_hour:
            raise ValueError(
                f"start_hour must be less than end_hour, got {start_hour}>={end_hour}"
            )

        super().__init__(tz)
        self.start_hour: int = start_hour
        self.end_hour: int = end_hour

    @override
    def _should_include_day(self, dt: datetime) -> bool:
        # Only weekdays
        return dt.weekday() < 5

    @override
    def _day_window(self, dt: datetime) -> tuple[datetime, datetime]:
        # Business hours window for this day
        window_start = dt.replace(hour=self.start_hour, minute=0, second=0)
        window_end = dt.replace(hour=self.end_hour - 1, minute=59, second=59)
        return window_start, window_end

    @override
    def _fetch_name(self) -> str:
        return "BusinessHours"


# Convenience functions for common use cases
def weekdays(tz: str = "UTC") -> Timeline[Interval]:
    """
    Return a timeline of all weekday time (Monday-Friday, all hours).

    Args:
        tz: IANA timezone name (e.g., "UTC", "US/Pacific", "Europe/London")

    Returns:
        Timeline yielding intervals for all weekday time in the specified timezone

    Example:
        >>> from calgebra import weekdays
        >>> weekday_events = my_calendar & weekdays(tz="US/Pacific")
    """
    return Weekdays(tz)


def weekends(tz: str = "UTC") -> Timeline[Interval]:
    """
    Return a timeline of all weekend time (Saturday-Sunday, all hours).

    Args:
        tz: IANA timezone name (e.g., "UTC", "US/Pacific", "Europe/London")

    Returns:
        Timeline yielding intervals for all weekend time in the specified timezone

    Example:
        >>> from calgebra import weekends
        >>> weekend_events = my_calendar & weekends(tz="US/Pacific")
    """
    return Weekends(tz)


def business_hours(
    tz: str = "UTC", start_hour: int = 9, end_hour: int = 17
) -> Timeline[Interval]:
    """
    Return a timeline of business hours (weekdays, specific hours).

    Args:
        tz: IANA timezone name (e.g., "UTC", "US/Pacific", "Europe/London")
        start_hour: Start hour (0-23), inclusive. Default: 9 (9am)
        end_hour: End hour (0-24), exclusive. Default: 17 (ends at 4:59:59pm)

    Returns:
        Timeline yielding intervals for business hours in the specified timezone

    Example:
        >>> from calgebra import business_hours
        >>> # Standard 9-5 workday
        >>> workhours = business_hours(tz="US/Pacific")
        >>>
        >>> # Custom hours: 8am-6pm
        >>> extended = business_hours(tz="US/Pacific", start_hour=8, end_hour=18)
        >>>
        >>> # Find free time during work hours
        >>> free = workhours - my_calendar
    """
    return BusinessHours(tz, start_hour, end_hour)
