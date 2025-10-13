"""Recurring interval generators using RFC 5545 recurrence rules.

This module provides a clean Python API for generating recurring time patterns,
backed by python-dateutil's battle-tested rrule implementation.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any, Literal, TypeAlias, override
from zoneinfo import ZoneInfo

from dateutil.rrule import (
    DAILY,
    FR,
    MO,
    MONTHLY,
    SA,
    SU,
    TH,
    TU,
    WE,
    WEEKLY,
    YEARLY,
    rrule,
    weekday,
)

from calgebra.core import Timeline
from calgebra.interval import Interval

Day: TypeAlias = Literal[
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
]

# Mapping from day names to dateutil weekday constants
_DAY_MAP: dict[Day, weekday] = {
    "monday": MO,
    "tuesday": TU,
    "wednesday": WE,
    "thursday": TH,
    "friday": FR,
    "saturday": SA,
    "sunday": SU,
}

_FREQ_MAP = {
    "daily": DAILY,
    "weekly": WEEKLY,
    "monthly": MONTHLY,
    "yearly": YEARLY,
}


class RecurringTimeline(Timeline[Interval]):
    """Generate recurring intervals based on RFC 5545 recurrence rules."""

    def __init__(
        self,
        freq: Literal["daily", "weekly", "monthly", "yearly"],
        *,
        interval: int = 1,
        day: Day | list[Day] | None = None,
        week: int | None = None,
        day_of_month: int | list[int] | None = None,
        month: int | list[int] | None = None,
        start_hour: float = 0,
        duration_hours: float = 24,
        tz: str = "UTC",
    ):
        """
        Initialize a recurring timeline.

        Args:
            freq: Frequency - "daily", "weekly", "monthly", or "yearly"
            interval: Repeat every N units (default 1)
            day: Day(s) of week for weekly/monthly patterns ("monday" or ["monday", "wednesday"])
            week: Which week of month for monthly patterns (1=first, -1=last, 2=second, etc.)
            day_of_month: Day(s) of month (1-31, or -1 for last day)
            month: Month(s) for yearly patterns (1-12)
            start_hour: Start hour of each occurrence (supports fractional hours)
            duration_hours: Duration of each occurrence in hours
            tz: IANA timezone name

        Examples:
            >>> # Every Monday at 9:30am for 30 min
            >>> recurring(freq="weekly", day="monday", start_hour=9.5, duration_hours=0.5)
            >>>
            >>> # First Monday of each month at 10am for 1 hour
            >>> recurring(freq="monthly", week=1, day="monday", start_hour=10, duration_hours=1)
            >>>
            >>> # Every other Tuesday
            >>> recurring(freq="weekly", interval=2, day="tuesday")
            >>>
            >>> # 1st and 15th of every month
            >>> recurring(freq="monthly", day_of_month=[1, 15])
        """
        self.zone: ZoneInfo = ZoneInfo(tz)
        self.start_hour: float = start_hour
        self.duration_hours: float = duration_hours
        self.freq: str = freq

        # Build rrule kwargs
        rrule_kwargs: dict[str, Any] = {
            "freq": _FREQ_MAP[freq],
            "interval": interval,
        }

        # Handle day-of-week
        if day is not None:
            days = [day] if isinstance(day, str) else day
            weekdays: list[weekday] = []
            for d in days:
                d_lower = d.lower()
                if d_lower not in _DAY_MAP:
                    valid = ", ".join(sorted(_DAY_MAP.keys()))
                    raise ValueError(
                        f"Invalid day name: '{d}'\n"
                        f"Valid days: {valid}\n"
                        f"Example: day_of_week('monday') or day_of_week(['tuesday', 'thursday'])"
                    )

                wd = _DAY_MAP[d_lower]
                # If week is specified (for monthly), apply offset
                if week is not None:
                    wd = wd(week)
                weekdays.append(wd)

            rrule_kwargs["byweekday"] = weekdays

        # Handle day of month
        if day_of_month is not None:
            rrule_kwargs["bymonthday"] = (
                [day_of_month] if isinstance(day_of_month, int) else day_of_month
            )

        # Handle month
        if month is not None:
            rrule_kwargs["bymonth"] = [month] if isinstance(month, int) else month

        # Store rrule (without start date - we'll set that dynamically based on query)
        self.rrule_kwargs: dict[str, Any] = rrule_kwargs

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Interval]:
        """Generate recurring intervals within the query range."""
        if start is None or end is None:
            raise ValueError(
                f"RecurringTimeline requires finite bounds, got start={start}, end={end}.\n"
                f"Recurring patterns generate infinite sequences and need bounded queries.\n"
                f"Fix: Use explicit bounds when slicing: list(recurring(...)[start:end])\n"
                f"Example: list(mondays[1704067200:1735689599])"
            )

        # Convert bounds to datetime in timezone
        start_dt = datetime.fromtimestamp(start, tz=self.zone)
        end_dt = datetime.fromtimestamp(end, tz=self.zone)

        # Create rrule with dtstart at beginning of query range
        # Normalize to start of day for consistent behavior
        dtstart = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)

        r = rrule(dtstart=dtstart, until=end_dt, cache=True, **self.rrule_kwargs)

        # Generate intervals for each occurrence
        for occurrence in r:
            # Calculate time window for this occurrence
            start_hour_int = int(self.start_hour)
            start_minute = int((self.start_hour - start_hour_int) * 60)
            start_second = int(
                ((self.start_hour - start_hour_int) * 60 - start_minute) * 60
            )

            window_start = occurrence.replace(
                hour=start_hour_int, minute=start_minute, second=start_second
            )
            # Subtract 1 because intervals are inclusive of both start and end bounds
            # Example: 9am-10am is [9:00:00, 9:59:59] = 3600 seconds total
            duration_seconds = int(self.duration_hours * 3600) - 1
            window_end = window_start + timedelta(seconds=duration_seconds)

            # Clamp to query bounds
            interval_start = max(int(window_start.timestamp()), start)
            interval_end = min(int(window_end.timestamp()), end)

            if interval_start <= interval_end:
                yield Interval(start=interval_start, end=interval_end)


def recurring(
    freq: Literal["daily", "weekly", "monthly", "yearly"],
    *,
    interval: int = 1,
    day: Day | list[Day] | None = None,
    week: int | None = None,
    day_of_month: int | list[int] | None = None,
    month: int | list[int] | None = None,
    start_hour: float = 0,
    duration_hours: float = 24,
    tz: str = "UTC",
) -> Timeline[Interval]:
    """
    Create a timeline with recurring intervals based on frequency and constraints.

    Args:
        freq: Frequency - "daily", "weekly", "monthly", or "yearly"
        interval: Repeat every N units (e.g., interval=2 for bi-weekly). Default: 1
        day: Day(s) of week ("monday", ["tuesday", "thursday"], etc.)
        week: Which week of month (1=first, -1=last). Only for freq="monthly"
        day_of_month: Day(s) of month (1-31, or -1 for last day). For freq="monthly"
        month: Month(s) (1-12). For freq="yearly"
        start_hour: Start hour of each occurrence (supports fractional, e.g., 9.5 = 9:30am)
        duration_hours: Duration in hours (supports fractional)
        tz: IANA timezone name (e.g., "UTC", "US/Pacific")

    Returns:
        Timeline yielding recurring intervals

    Examples:
        >>> from calgebra import recurring
        >>>
        >>> # Every Monday at 9:30am for 30 minutes
        >>> monday_standup = recurring(
        ...     freq="weekly",
        ...     day="monday",
        ...     start_hour=9.5,
        ...     duration_hours=0.5,
        ...     tz="US/Pacific"
        ... )
        >>>
        >>> # First Monday of each month
        >>> first_monday = recurring(
        ...     freq="monthly",
        ...     week=1,
        ...     day="monday",
        ...     tz="UTC"
        ... )
        >>>
        >>> # Last Friday of each month at 4pm for 1 hour
        >>> monthly_review = recurring(
        ...     freq="monthly",
        ...     week=-1,
        ...     day="friday",
        ...     start_hour=16,
        ...     duration_hours=1,
        ...     tz="US/Pacific"
        ... )
        >>>
        >>> # Every other Tuesday (bi-weekly)
        >>> biweekly = recurring(
        ...     freq="weekly",
        ...     interval=2,
        ...     day="tuesday",
        ...     tz="UTC"
        ... )
        >>>
        >>> # 1st and 15th of every month
        >>> paydays = recurring(
        ...     freq="monthly",
        ...     day_of_month=[1, 15],
        ...     tz="UTC"
        ... )
        >>>
        >>> # Quarterly (every 3 months on the 1st)
        >>> quarterly = recurring(
        ...     freq="monthly",
        ...     interval=3,
        ...     day_of_month=1,
        ...     tz="UTC"
        ... )
    """
    return RecurringTimeline(
        freq,
        interval=interval,
        day=day,
        week=week,
        day_of_month=day_of_month,
        month=month,
        start_hour=start_hour,
        duration_hours=duration_hours,
        tz=tz,
    )


def day_of_week(days: Day | list[Day], tz: str = "UTC") -> Timeline[Interval]:
    """
    Convenience function for filtering by specific day(s) of the week.

    Generates intervals spanning entire days (00:00:00 to 23:59:59) for the
    specified weekday(s).

    Args:
        days: Single day name or list of day names (e.g., "monday", ["tuesday", "thursday"])
        tz: IANA timezone name for day boundaries

    Returns:
        Timeline yielding intervals for the specified day(s) of the week

    Example:
        >>> from calgebra import day_of_week
        >>>
        >>> # All Mondays
        >>> mondays = day_of_week("monday", tz="UTC")
        >>>
        >>> # Weekdays (Mon-Fri)
        >>> weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"])
    """
    return recurring(freq="weekly", day=days, tz=tz)


def time_of_day(
    start_hour: float = 0, duration_hours: float = 24, tz: str = "UTC"
) -> Timeline[Interval]:
    """
    Convenience function for filtering by time of day.

    Generates intervals for a specific time window repeated daily (e.g., 9am-5pm
    every day).

    Args:
        start_hour: Start hour (0-24), supports fractional hours (e.g., 9.5 = 9:30am)
        duration_hours: Duration in hours (supports fractional hours)
        tz: IANA timezone name for time boundaries

    Returns:
        Timeline yielding daily intervals for the specified time window

    Example:
        >>> from calgebra import time_of_day, flatten
        >>>
        >>> # 9am-5pm every day
        >>> work_hours = time_of_day(start_hour=9, duration_hours=8, tz="US/Pacific")
        >>>
        >>> # Combine with day_of_week for business hours
        >>> weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"])
        >>> business_hours = flatten(weekdays & work_hours)
    """
    # Validate parameters
    if not (0 <= start_hour < 24):
        raise ValueError(
            f"start_hour must be in range [0, 24), got {start_hour}.\n"
            f"Use 0 for midnight, 12 for noon, 23 for 11pm.\n"
            f"Fractional hours are supported: 9.5 = 9:30am, 14.25 = 2:15pm"
        )
    if duration_hours <= 0:
        raise ValueError(
            f"duration_hours must be positive, got {duration_hours}.\n"
            f"Example: duration_hours=8 for an 8-hour window (like 9am-5pm)"
        )
    if start_hour + duration_hours > 24:
        raise ValueError(
            f"start_hour + duration_hours cannot exceed 24 hours.\n"
            f"Got: {start_hour} + {duration_hours} = {start_hour + duration_hours}\n"
            f"time_of_day() cannot span midnight. For overnight windows, use recurring():\n"
            f"  overnight = recurring(freq='daily', start_hour=20, duration_hours=5, tz='UTC')\n"
        )

    return recurring(
        freq="daily", start_hour=start_hour, duration_hours=duration_hours, tz=tz
    )
