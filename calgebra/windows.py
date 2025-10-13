"""Built-in time window generators for common patterns.

These timelines generate intervals for common recurring patterns using
two composable primitives: day-of-week and time-of-day filtering.
No external dependencies required.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import override
from zoneinfo import ZoneInfo

from calgebra.core import Timeline
from calgebra.interval import Interval

# Mapping from day names to Python weekday integers
_DAY_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


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


class DayOfWeek(_DailyPattern):
    """Generate intervals for specific day(s) of the week (all hours)."""

    def __init__(self, days: str | list[str], tz: str = "UTC"):
        """
        Initialize day-of-week timeline.

        Args:
            days: Single day name or list of day names (case-insensitive)
                  Valid: "monday", "tuesday", "wednesday", "thursday", "friday",
                         "saturday", "sunday"
            tz: IANA timezone name (e.g., "UTC", "US/Pacific")

        Example:
            >>> day_of_week("monday")
            >>> day_of_week(["monday", "wednesday", "friday"])
        """
        super().__init__(tz)

        # Normalize to list
        if isinstance(days, str):
            days = [days]

        # Convert to weekday integers
        self.target_weekdays: set[int] = set()
        for day in days:
            day_lower = day.lower()
            if day_lower not in _DAY_MAP:
                valid = ", ".join(_DAY_MAP.keys())
                raise ValueError(f"Invalid day '{day}'. Valid days: {valid}")
            self.target_weekdays.add(_DAY_MAP[day_lower])

    @override
    def _should_include_day(self, dt: datetime) -> bool:
        return dt.weekday() in self.target_weekdays

    @override
    def _day_window(self, dt: datetime) -> tuple[datetime, datetime]:
        # Full day
        return dt, dt.replace(hour=23, minute=59, second=59)

    @override
    def _fetch_name(self) -> str:
        return "DayOfWeek"


class TimeOfDay(_DailyPattern):
    """Generate intervals for specific time window each day (all days)."""

    def __init__(
        self, start_hour: float = 0, duration_hours: float = 24, tz: str = "UTC"
    ):
        """
        Initialize time-of-day timeline.

        Args:
            start_hour: Start hour (0-24), supports fractional hours (e.g., 9.5 = 9:30am)
            duration_hours: Duration in hours (supports fractional hours)
            tz: IANA timezone name (e.g., "UTC", "US/Pacific")

        Example:
            >>> time_of_day(start_hour=9, duration_hours=8)  # 9am-5pm
            >>> time_of_day(start_hour=9.5, duration_hours=0.5)  # 9:30am-10am
        """
        if not (0 <= start_hour < 24):
            raise ValueError(f"start_hour must be 0-24, got {start_hour}")
        if duration_hours <= 0:
            raise ValueError(f"duration_hours must be positive, got {duration_hours}")
        if start_hour + duration_hours > 24:
            raise ValueError(
                f"start_hour + duration_hours exceeds 24 hours: {start_hour} + {duration_hours} = {start_hour + duration_hours}"
            )

        super().__init__(tz)
        self.start_hour: float = start_hour
        self.duration_hours: float = duration_hours

    @override
    def _should_include_day(self, dt: datetime) -> bool:
        # Include all days
        return True

    @override
    def _day_window(self, dt: datetime) -> tuple[datetime, datetime]:
        # Calculate start time from fractional hour
        start_hour_int = int(self.start_hour)
        start_minute = int((self.start_hour - start_hour_int) * 60)
        start_second = int(
            ((self.start_hour - start_hour_int) * 60 - start_minute) * 60
        )

        window_start = dt.replace(
            hour=start_hour_int, minute=start_minute, second=start_second
        )

        # Calculate end time (inclusive, so subtract 1 second)
        duration_seconds = int(self.duration_hours * 3600) - 1
        window_end = window_start + timedelta(seconds=duration_seconds)

        return window_start, window_end

    @override
    def _fetch_name(self) -> str:
        return "TimeOfDay"


# Convenience functions
def day_of_week(days: str | list[str], tz: str = "UTC") -> Timeline[Interval]:
    """
    Return a timeline for specific day(s) of the week (all hours).

    Args:
        days: Single day name or list of day names (case-insensitive)
              Valid: "monday", "tuesday", "wednesday", "thursday", "friday",
                     "saturday", "sunday"
        tz: IANA timezone name (e.g., "UTC", "US/Pacific", "Europe/London")

    Returns:
        Timeline yielding intervals for the specified days

    Example:
        >>> from calgebra import day_of_week
        >>>
        >>> # All Mondays
        >>> mondays = day_of_week("monday", tz="US/Pacific")
        >>>
        >>> # Weekdays (Monday-Friday)
        >>> weekdays = day_of_week(
        ...     ["monday", "tuesday", "wednesday", "thursday", "friday"],
        ...     tz="US/Pacific"
        ... )
        >>>
        >>> # Weekends
        >>> weekends = day_of_week(["saturday", "sunday"], tz="UTC")
    """
    return DayOfWeek(days, tz)


def time_of_day(
    start_hour: float = 0, duration_hours: float = 24, tz: str = "UTC"
) -> Timeline[Interval]:
    """
    Return a timeline for a specific time window each day (all days).

    Args:
        start_hour: Start hour (0-24), supports fractional hours (e.g., 9.5 = 9:30am)
        duration_hours: Duration in hours (supports fractional hours)
        tz: IANA timezone name (e.g., "UTC", "US/Pacific", "Europe/London")

    Returns:
        Timeline yielding intervals for the specified time window

    Example:
        >>> from calgebra import time_of_day
        >>>
        >>> # 9am-5pm (8 hours)
        >>> work_hours = time_of_day(start_hour=9, duration_hours=8, tz="US/Pacific")
        >>>
        >>> # 9:30am-10am (30 minutes)
        >>> standup_time = time_of_day(start_hour=9.5, duration_hours=0.5, tz="US/Pacific")
        >>>
        >>> # Combine with day_of_week for business hours
        >>> from calgebra import day_of_week
        >>> business_hours = (
        ...     day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"])
        ...     & time_of_day(start_hour=9, duration_hours=8, tz="US/Pacific")
        ... )
    """
    return TimeOfDay(start_hour, duration_hours, tz)
