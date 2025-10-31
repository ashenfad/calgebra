"""Recurring interval generators using RFC 5545 recurrence rules.

This module provides a clean Python API for generating recurring time patterns,
backed by python-dateutil's battle-tested rrule implementation.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any, Literal, TypeAlias
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
from typing_extensions import override

from calgebra.core import Timeline, flatten, solid
from calgebra.interval import Interval
from calgebra.util import DAY, MONTH, WEEK, YEAR

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

_FREQ_SIZE = {
    DAILY: DAY,
    WEEKLY: WEEK,
    MONTHLY: MONTH,
    YEARLY: YEAR,
}

# Page sizes for unbounded queries (in seconds)
_PAGE_SIZES = {
    "daily": 365 * DAY,  # 1 year for daily patterns
    "weekly": 2 * 365 * DAY,  # 2 years for weekly patterns
    "monthly": 5 * 365 * DAY,  # 5 years for monthly patterns
    "yearly": 10 * 365 * DAY,  # 10 years for yearly patterns
}


class _RawRecurringTimeline(Timeline[Interval]):
    """Generate recurring intervals based on RFC 5545 recurrence rules."""

    @property
    @override
    def _is_mask(self) -> bool:
        """RecurringTimeline always yields mask Interval objects."""
        return True

    def __init__(
        self,
        freq: Literal["daily", "weekly", "monthly", "yearly"],
        *,
        interval: int = 1,
        day: Day | list[Day] | None = None,
        week: int | None = None,
        day_of_month: int | list[int] | None = None,
        month: int | list[int] | None = None,
        start: int = 0,
        duration: int = DAY,
        tz: str = "UTC",
    ):
        """
        Initialize a recurring timeline.

        Args:
            freq: Frequency - "daily", "weekly", "monthly", or "yearly"
            interval: Repeat every N units (default 1)
            day: Day(s) of week for weekly/monthly patterns
                ("monday" or ["monday", "wednesday"])
            week: Which week of month for monthly patterns
                (1=first, -1=last, 2=second, etc.)
            day_of_month: Day(s) of month (1-31, or -1 for last day)
            month: Month(s) for yearly patterns (1-12)
            start: Start time of each occurrence in seconds from midnight (default 0)
            duration: Duration of each occurrence in seconds (default DAY = full day)
            tz: IANA timezone name

        Examples:
            >>> from calgebra import HOUR, MINUTE
            >>> # Every Monday at 9:30am for 30 min
            >>> recurring(
            ...     freq="weekly", day="monday",
            ...     start=9*HOUR + 30*MINUTE, duration=30*MINUTE
            ... )
            >>>
            >>> # First Monday of each month at 10am for 1 hour
            >>> recurring(
            ...     freq="monthly", week=1, day="monday",
            ...     start=10*HOUR, duration=HOUR
            ... )
            >>>
            >>> # Every other Tuesday (full day)
            >>> recurring(freq="weekly", interval=2, day="tuesday")
            >>>
            >>> # 1st and 15th of every month (full day)
            >>> recurring(freq="monthly", day_of_month=[1, 15])
        """
        self.zone: ZoneInfo = ZoneInfo(tz)
        self.start_seconds: int = start
        self.duration_seconds: int = duration
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
                        f"Invalid day name: '{d}'\n" f"Valid days: {valid}\n"
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
        """Generate raw recurring intervals with paging and lookback.

        Supports unbounded end queries via automatic paging.
        Generates intervals that may extend beyond query bounds (no clamping).
        """
        if start is None:
            raise ValueError(
                "Recurring timeline requires finite start, got start=None.\n"
                "Fix: Use explicit start when slicing: recurring(...)[start:]\n"
                "Example: list(mondays[1704067200:])"
            )

        # Determine page size based on frequency
        page_size = _PAGE_SIZES[self.freq]

        # Page through time
        page_start = start
        while True:
            # Calculate page end (bounded by query end if provided)
            page_end = page_start + page_size - 1
            if end is not None:
                page_end = min(page_end, end)

            # Generate raw intervals for this page
            yield from self._generate_page(page_start, page_end)

            # Stop if we've covered bounded range
            if end is not None and page_end >= end:
                break

            page_start = page_end + 1

    def _occurrence_to_interval(self, occurrence: datetime) -> Interval:
        """Convert an rrule occurrence to an Interval with time window applied."""
        start_hour_int = self.start_seconds // 3600
        remaining = self.start_seconds % 3600
        start_minute = remaining // 60
        start_second = remaining % 60

        window_start = occurrence.replace(
            hour=start_hour_int, minute=start_minute, second=start_second
        )
        # Subtract 1 because intervals are inclusive of both start and end bounds
        window_end = window_start + timedelta(seconds=self.duration_seconds - 1)

        return Interval(
            start=int(window_start.timestamp()), end=int(window_end.timestamp())
        )

    def _generate_page(self, page_start: int, page_end: int) -> Iterable[Interval]:
        """Generate raw intervals for a single page with lookback.

        Creates rrule with dtstart at page start, then looks back for overlapping
        events.
        For lookback, creates a second rrule with dtstart moved back by interval periods
        to maintain phase consistency.
        """
        start_dt = datetime.fromtimestamp(page_start, tz=self.zone)
        end_dt = datetime.fromtimestamp(page_end, tz=self.zone)

        # Main rrule starts at page start (preserves original phase behavior)
        dtstart = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        r = rrule(dtstart=dtstart, until=end_dt, cache=True, **self.rrule_kwargs)

        # For lookback: go back enough to capture overlapping events
        # Move back by duration AND enough interval periods to ensure we catch
        # everything
        interval = self.rrule_kwargs.get("interval", 1)

        # Calculate how far back to look
        period_seconds = _FREQ_SIZE[self.rrule_kwargs["freq"]] * interval

        # Go back by duration + one interval period (to catch all overlaps)
        lookback_seconds = self.duration_seconds + period_seconds
        lookback_dt = start_dt - timedelta(seconds=lookback_seconds)
        lookback_dtstart = lookback_dt.replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Create separate rrule for lookback
        r_lookback = rrule(
            dtstart=lookback_dtstart, until=dtstart, cache=True, **self.rrule_kwargs
        )

        # Yield lookback intervals that overlap with page_start
        for occurrence in r_lookback:
            interval = self._occurrence_to_interval(occurrence)
            # Only yield if this interval extends into the page
            if interval.end is not None and interval.end >= page_start:
                yield interval

        # Yield main intervals
        for occurrence in r:
            yield self._occurrence_to_interval(occurrence)


def recurring(
    freq: Literal["daily", "weekly", "monthly", "yearly"],
    *,
    interval: int = 1,
    day: Day | list[Day] | None = None,
    week: int | None = None,
    day_of_month: int | list[int] | None = None,
    month: int | list[int] | None = None,
    start: int = 0,
    duration: int = DAY,
    tz: str = "UTC",
) -> Timeline[Interval]:
    """
    Create a timeline with recurring intervals based on frequency and constraints.

    Supports unbounded end queries (e.g., recurring(...)[start:]) via automatic paging.

    Args:
        freq: Frequency - "daily", "weekly", "monthly", or "yearly"
        interval: Repeat every N units (e.g., interval=2 for bi-weekly). Default: 1
        day: Day(s) of week ("monday", ["tuesday", "thursday"], etc.)
        week: Which week of month (1=first, -1=last). Only for freq="monthly"
        day_of_month: Day(s) of month (1-31, or -1 for last day). For freq="monthly"
        month: Month(s) (1-12). For freq="yearly"
        start: Start time of each occurrence in seconds from midnight (default 0)
        duration: Duration of each occurrence in seconds (default DAY = full day)
        tz: IANA timezone name (e.g., "UTC", "US/Pacific")

    Returns:
        Timeline yielding recurring intervals

    Examples:
        >>> from calgebra import recurring, HOUR, MINUTE
        >>>
        >>> # Every Monday at 9:30am for 30 minutes
        >>> monday_standup = recurring(
        ...     freq="weekly",
        ...     day="monday",
        ...     start=9*HOUR + 30*MINUTE,
        ...     duration=30*MINUTE,
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
        ...     start=16*HOUR,
        ...     duration=HOUR,
        ...     tz="US/Pacific"
        ... )
        >>>
        >>> # Every other Tuesday (bi-weekly, full day)
        >>> biweekly = recurring(
        ...     freq="weekly",
        ...     interval=2,
        ...     day="tuesday",
        ...     tz="UTC"
        ... )
        >>>
        >>> # 1st and 15th of every month (full day)
        >>> paydays = recurring(
        ...     freq="monthly",
        ...     day_of_month=[1, 15],
        ...     tz="UTC"
        ... )
        >>>
        >>> # Quarterly (every 3 months on the 1st, full day)
        >>> quarterly = recurring(
        ...     freq="monthly",
        ...     interval=3,
        ...     day_of_month=1,
        ...     tz="UTC"
        ... )
        >>>
        >>> # Unbounded queries (with itertools)
        >>> from itertools import islice
        >>> mondays = recurring(freq="weekly", day="monday", tz="UTC")
        >>> next_five = list(islice(mondays[start:], 5))
    """
    # Generate raw recurring intervals with paging and lookback
    raw = _RawRecurringTimeline(
        freq,
        interval=interval,
        day=day,
        week=week,
        day_of_month=day_of_month,
        month=month,
        start=start,
        duration=duration,
        tz=tz,
    )

    # Compose: merge recurring pattern, then clamp to query bounds
    return solid & flatten(raw)


def day_of_week(days: Day | list[Day], tz: str = "UTC") -> Timeline[Interval]:
    """
    Convenience function for filtering by specific day(s) of the week.

    Generates intervals spanning entire days (00:00:00 to 23:59:59) for the
    specified weekday(s).

    Args:
        days: Single day name or list of day names
            (e.g., "monday", ["tuesday", "thursday"])
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
        >>> weekdays = day_of_week(
        ...     ["monday", "tuesday", "wednesday", "thursday", "friday"]
        ... )
    """
    return recurring(freq="weekly", day=days, tz=tz)


def time_of_day(
    start: int = 0, duration: int = DAY, tz: str = "UTC"
) -> Timeline[Interval]:
    """
    Convenience function for filtering by time of day.

    Generates intervals for a specific time window repeated daily (e.g., 9am-5pm
    every day).

    Args:
        start: Start time in seconds from midnight (default 0)
        duration: Duration in seconds (default DAY = full day)
        tz: IANA timezone name for time boundaries

    Returns:
        Timeline yielding daily intervals for the specified time window

    Example:
        >>> from calgebra import time_of_day, HOUR
        >>>
        >>> # 9am-5pm every day (8 hours)
        >>> work_hours = time_of_day(start=9*HOUR, duration=8*HOUR, tz="US/Pacific")
        >>>
        >>> # Combine with day_of_week for business hours
        >>> weekdays = day_of_week(
        ...     ["monday", "tuesday", "wednesday", "thursday", "friday"]
        ... )
        >>> business_hours = weekdays & work_hours
    """
    # Validate parameters
    if not (0 <= start < DAY):
        raise ValueError(
            f"start must be in range [0, {DAY}), got {start}.\n"
            f"Use 0 for midnight, 12*HOUR for noon, 23*HOUR for 11pm.\n"
            f"Example: start=9*HOUR + 30*MINUTE for 9:30am"
        )
    if duration <= 0:
        raise ValueError(
            f"duration must be positive, got {duration}.\n"
            f"Example: duration=8*HOUR for an 8-hour window (like 9am-5pm)"
        )
    if start + duration > DAY:
        raise ValueError(
            f"start + duration cannot exceed 24 hours ({DAY} seconds).\n"
            f"Got: {start} + {duration} = {start + duration}\n"
            f"time_of_day() cannot span midnight. "
            f"For overnight windows, use recurring():\n"
            f"  from calgebra import recurring, HOUR\n"
            f"  overnight = recurring(\n"
            f"      freq='daily', start=20*HOUR, duration=5*HOUR, tz='UTC'\n"
            f"  )\n"
        )

    return recurring(freq="daily", start=start, duration=duration, tz=tz)
