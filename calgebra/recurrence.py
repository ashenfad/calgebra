"""Recurring interval generators using RFC 5545 recurrence rules.

This module provides a clean Python API for generating recurring time patterns,
backed by python-dateutil's battle-tested rrule implementation.
"""

from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Generic, Literal, TypeAlias, TypeVar
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
from calgebra.util import DAY, WEEK

IvlOut = TypeVar("IvlOut", bound=Interval)

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


class RecurringPattern(Timeline[IvlOut], Generic[IvlOut]):
    """Generate recurring intervals based on RFC 5545 recurrence rules.
    
    Supports both mask mode (no metadata) and rich mode (with interval_class and metadata).
    """

    @property
    @override
    def _is_mask(self) -> bool:
        """Mask only if using base Interval class with no metadata."""
        return self._interval_class is Interval and not self._metadata

    @property
    def recurrence_rule(self) -> Any:
        """Return the rrule for this recurring pattern.
        
        Reconstructs the rrule from stored parameters. This is used by
        MutableTimeline.add() to determine if a timeline can be written
        symbolically to a backend.
        """
        # Return a fresh rrule instance with our parameters
        # Note: No dtstart here, it's computed dynamically in fetch()
        return rrule(**self.rrule_kwargs)

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
        interval_class: type[IvlOut] = Interval,  # type: ignore
        **metadata: Any,
    ):
        """
        Initialize a recurring pattern.

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
            interval_class: Class to instantiate for each interval (default: Interval)
            **metadata: Additional metadata fields to apply to each interval
        """
        self.zone: ZoneInfo = ZoneInfo(tz)
        self.start_seconds: int = start
        self.duration_seconds: int = duration
        self.freq: str = freq
        self.interval: int = interval
        self._interval_class: type[IvlOut] = interval_class
        self._metadata: dict[str, Any] = metadata

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

        # Store original start date components for phase calculations
        # We assume the pattern "started" at epoch (1970-01-01) for phase alignment
        # unless otherwise specified. Since rrule doesn't have an explicit "start date"
        # in our API (only time-of-day), we align to 1970-01-01.
        self._epoch = datetime(1970, 1, 1, tzinfo=self.zone)

    def _get_safe_anchor(self, start_dt: datetime) -> datetime:
        """Calculate a phase-aligned start date for rrule near the target date.

        Ensures that the rrule sequence maintains its phase (e.g., "every 2 weeks")
        regardless of where we start generating.
        Derives the anchor from the Epoch to ensure stable defaults for unspecified
        fields (e.g., day of month, time of day).
        """
        # If interval is 1, we still need to align to Epoch to ensure stable defaults
        # (e.g. day of month) if they are not specified in rrule_kwargs.
        # However, if interval=1, any "aligned" date is valid phase-wise.
        # But to be safe against "random day of month" issues, we should always
        # align to the grid if possible.

        # Calculate offset from epoch in frequency units
        if self.freq == "daily":
            # Days since epoch
            delta_days = (start_dt.date() - self._epoch.date()).days
            offset = delta_days % self.interval
            # Anchor = Start - Offset (days)
            # But we want to preserve Epoch's time/etc.
            # So Anchor = Epoch + (TotalDays - Offset)
            aligned_days = delta_days - offset
            return self._epoch + timedelta(days=aligned_days)

        elif self.freq == "weekly":
            # Weeks since epoch (1970-01-01 was a Thursday)
            # We align to the Monday before epoch (1969-12-29) to match
            # rrule's ISO week boundaries
            epoch_monday = datetime(1969, 12, 29, tzinfo=self.zone)
            delta_days = (start_dt.date() - epoch_monday.date()).days
            weeks = delta_days // 7
            offset = weeks % self.interval
            aligned_weeks = weeks - offset
            return epoch_monday + timedelta(weeks=aligned_weeks)

        elif self.freq == "monthly":
            # Months since epoch
            delta_years = start_dt.year - self._epoch.year
            delta_months = start_dt.month - self._epoch.month
            total_months = delta_years * 12 + delta_months
            offset = total_months % self.interval

            # Logic: (Year * 12 + Month - 1) - offset
            target_total = total_months - offset
            # Reconstruct Year/Month (0-indexed month for math, then +1)
            # We add epoch year/month back in implicitly because total_months was delta
            abs_total = (self._epoch.year * 12 + self._epoch.month - 1) + target_total
            year = abs_total // 12
            month = (abs_total % 12) + 1
            # Use self._epoch to preserve day=1, time=00:00
            return self._epoch.replace(year=year, month=month)

        elif self.freq == "yearly":
            # Years since epoch
            delta_years = start_dt.year - self._epoch.year
            offset = delta_years % self.interval
            # Use self._epoch to preserve month=1, day=1
            return self._epoch.replace(year=start_dt.year - offset)

        return start_dt

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Interval]:
        """Generate recurring intervals using a single continuous rrule iterator.

        Supports unbounded end queries.
        """
        if start is None:
            raise ValueError(
                "Recurring timeline requires finite start, got start=None.\n"
                "Fix: Use explicit start when slicing: recurring(...)[start:]\n"
                "Example: list(mondays[1704067200:])"
            )

        # 1. Determine where to start looking (Lookback)
        # We need to start early enough to catch events that started before 'start'
        # but overlap with it.
        # Safe bet: Look back by duration + 1 interval period
        lookback_buffer = self.duration_seconds
        if self.freq == "daily":
            lookback_buffer += self.interval * DAY
        elif self.freq == "weekly":
            lookback_buffer += self.interval * WEEK
        elif self.freq == "monthly":
            lookback_buffer += self.interval * 32 * DAY  # Approx
        elif self.freq == "yearly":
            lookback_buffer += self.interval * 366 * DAY  # Approx

        lookback_start_ts = start - lookback_buffer
        lookback_start_dt = datetime.fromtimestamp(lookback_start_ts, tz=self.zone)

        # 2. Calculate Phase-Aligned Anchor
        # Find a valid start date for the rrule that preserves the cadence
        anchor_dt = self._get_safe_anchor(lookback_start_dt)

        # Ensure anchor starts at midnight to match rrule expectations
        anchor_dt = anchor_dt.replace(hour=0, minute=0, second=0, microsecond=0)

        # 3. Create Iterator
        # We use the anchor as dtstart. rrule will generate valid occurrences
        # from there.
        rules = rrule(dtstart=anchor_dt, **self.rrule_kwargs)

        # 4. Stream results
        for occurrence in rules:
            ivl = self._occurrence_to_interval(occurrence)

            # Fast-forward: Skip if it ends before our query window
            if ivl.end is not None and ivl.end < start:
                continue

            # Stop: If we've passed the query window
            # Note: rrule yields in order, so once we pass end, we're done.
            # fetch() end bound is inclusive, so we stop only if start > end
            if end is not None and ivl.start is not None and ivl.start > end:
                break

            yield ivl

    def _occurrence_to_interval(self, occurrence: datetime) -> IvlOut:
        """Convert an rrule occurrence to an Interval with time window and metadata applied."""
        start_hour_int = self.start_seconds // 3600
        remaining = self.start_seconds % 3600
        start_minute = remaining // 60
        start_second = remaining % 60

        window_start = occurrence.replace(
            hour=start_hour_int, minute=start_minute, second=start_second
        )
        # Intervals are now exclusive [start, end), so end = start + duration
        window_end = window_start + timedelta(seconds=self.duration_seconds)

        # Create interval with metadata
        base_interval = self._interval_class(
            start=int(window_start.timestamp()), 
            end=int(window_end.timestamp()),
            **self._metadata
        )
        
        return base_interval


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

    Supports unbounded end queries (e.g., recurring(...)[start:]) via infinite
    streaming.

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
    # Generate raw recurring intervals with lookback for overlaps
    raw = RecurringPattern(
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
