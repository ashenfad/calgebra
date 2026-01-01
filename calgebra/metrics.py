from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any, Literal, TypeVar
from zoneinfo import ZoneInfo

from .core import Timeline, flatten
from .interval import Interval
from .mutable.memory import timeline as make_timeline

Ivl = TypeVar("Ivl", bound=Interval)

# Period types for windowing
Period = Literal["hour", "day", "week", "month", "year", "full"]

# Group-by types for cyclic aggregation
GroupBy = Literal[
    "hour_of_day", "day_of_week", "day_of_month", "week_of_year", "month_of_year"
]

# Valid period -> group_by mappings
_VALID_GROUP_BY: dict[str, set[str]] = {
    "hour": {"hour_of_day"},
    "day": {"day_of_week", "day_of_month"},
    "week": {"week_of_year"},
    "month": {"month_of_year"},
}


def _extract_group_key(dt: datetime, group_by: GroupBy) -> int:
    """Extract cyclic key from datetime for grouping."""
    match group_by:
        case "hour_of_day":
            return dt.hour
        case "day_of_week":
            return dt.weekday()
        case "day_of_month":
            return dt.day
        case "week_of_year":
            return dt.isocalendar()[1]
        case "month_of_year":
            return dt.month
        case _:
            raise ValueError(f"Unsupported group_by value: {group_by!r}")


def _validate_period_group_by(period: str, group_by: GroupBy | None) -> None:
    """Validate that period and group_by are compatible."""
    if group_by is None:
        return
    if period not in _VALID_GROUP_BY:
        raise ValueError(
            f"group_by requires period to be one of {list(_VALID_GROUP_BY.keys())}, "
            f"got period={period!r}"
        )
    if group_by not in _VALID_GROUP_BY[period]:
        valid = _VALID_GROUP_BY[period]
        raise ValueError(
            f"Invalid group_by={group_by!r} for period={period!r}. "
            f"Valid options: {valid}"
        )


def _coerce_bound(
    bound: date | datetime | int,
    tz: str,
) -> int:
    """Convert flexible bound types to Unix timestamp.

    Args:
        bound: Date (midnight in tz), datetime (must be tz-aware), or Unix timestamp
        tz: Timezone for date interpretation

    Returns:
        Unix timestamp (seconds since epoch)

    Raises:
        TypeError: If datetime is naive (missing timezone info)
    """
    if isinstance(bound, int):
        return bound
    elif isinstance(bound, date) and not isinstance(bound, datetime):
        # Date -> midnight in specified timezone
        zone = ZoneInfo(tz)
        dt = datetime.combine(bound, datetime.min.time(), tzinfo=zone)
        return int(dt.timestamp())
    elif isinstance(bound, datetime):
        if bound.tzinfo is None:
            raise TypeError(
                f"Naive datetime not allowed: {bound}\n"
                f"Use timezone-aware datetime (e.g., from at_tz()) or "
                f"pass a date object to interpret as midnight in tz={tz!r}"
            )
        return int(bound.timestamp())
    else:
        raise TypeError(
            f"Bound must be date, datetime, or int, got {type(bound).__name__}"
        )


def _period_windows(
    start_ts: int,
    end_ts: int,
    period: Period,
    tz: str,
) -> list[tuple[date, int, int]]:
    """Generate calendar-aligned period windows.

    Args:
        start_ts: Query start timestamp (inclusive)
        end_ts: Query end timestamp (exclusive)
        period: Period type for aggregation
        tz: Timezone for calendar alignment

    Returns:
        List of (period_label_date, window_start_ts, window_end_ts) tuples.
        Empty if start_ts >= end_ts.
    """
    # Use datetime-labeled version and convert to date labels
    windows = _period_windows_with_dt(start_ts, end_ts, period, tz)
    return [
        (dt.date() if isinstance(dt, datetime) else dt, ws, we)
        for dt, ws, we in windows
    ]


def _period_windows_with_dt(
    start_ts: int,
    end_ts: int,
    period: Period,
    tz: str,
) -> list[tuple[datetime, int, int]]:
    """Generate calendar-aligned period windows with datetime labels.

    Like _period_windows but returns datetime labels for group key extraction.
    """
    if start_ts >= end_ts:
        return []

    zone = ZoneInfo(tz)
    start_dt = datetime.fromtimestamp(start_ts, tz=zone)
    end_dt = datetime.fromtimestamp(end_ts, tz=zone)

    if period == "full":
        # Exact bounds, no snapping
        return [(start_dt, start_ts, end_ts)]

    windows: list[tuple[datetime, int, int]] = []

    if period == "hour":
        # Snap to hour boundaries
        current = datetime(
            start_dt.year, start_dt.month, start_dt.day, start_dt.hour, tzinfo=zone
        )
        while current < end_dt:
            next_hour = current + timedelta(hours=1)
            win_start = int(current.timestamp())
            win_end = int(next_hour.timestamp())
            windows.append((current, win_start, win_end))
            current = next_hour

    elif period == "day":
        # Snap to midnight-to-midnight
        current = datetime(start_dt.year, start_dt.month, start_dt.day, tzinfo=zone)
        while current < end_dt:
            next_day = current + timedelta(days=1)
            win_start = int(current.timestamp())
            win_end = int(next_day.timestamp())
            windows.append((current, win_start, win_end))
            current = next_day

    elif period == "week":
        # ISO weeks: Monday = 0, Sunday = 6
        # Snap to start of week (Monday)
        days_since_monday = start_dt.weekday()  # 0=Mon, 6=Sun
        week_start = datetime(
            start_dt.year, start_dt.month, start_dt.day, tzinfo=zone
        ) - timedelta(days=days_since_monday)

        current = week_start
        while current < end_dt:
            next_week = current + timedelta(weeks=1)
            win_start = int(current.timestamp())
            win_end = int(next_week.timestamp())
            windows.append((current, win_start, win_end))
            current = next_week

    elif period == "month":
        # Snap to start of month
        current = datetime(start_dt.year, start_dt.month, 1, tzinfo=zone)
        while current < end_dt:
            # Next month (handle year rollover)
            if current.month == 12:
                next_month = datetime(current.year + 1, 1, 1, tzinfo=zone)
            else:
                next_month = datetime(current.year, current.month + 1, 1, tzinfo=zone)
            win_start = int(current.timestamp())
            win_end = int(next_month.timestamp())
            windows.append((current, win_start, win_end))
            current = next_month

    elif period == "year":
        # Snap to start of year
        current = datetime(start_dt.year, 1, 1, tzinfo=zone)
        while current < end_dt:
            next_year = datetime(current.year + 1, 1, 1, tzinfo=zone)
            win_start = int(current.timestamp())
            win_end = int(next_year.timestamp())
            windows.append((current, win_start, win_end))
            current = next_year

    return windows


def _total_duration(tl: Timeline[Interval], win_start: int, win_end: int) -> int:
    """Compute total duration within window, flattening overlaps."""
    total = 0
    for ivl in flatten(tl)[win_start:win_end]:
        if ivl.start is None or ivl.end is None:
            continue
        # Clip to window bounds
        clipped_start = max(ivl.start, win_start)
        clipped_end = min(ivl.end, win_end)
        if clipped_start < clipped_end:
            total += clipped_end - clipped_start
    return total


def _extremum_duration(
    tl: Timeline[Ivl], win_start: int, win_end: int, find_max: bool
) -> Ivl | None:
    """Find longest or shortest interval within window.

    Args:
        tl: Timeline to search
        win_start: Window start timestamp
        win_end: Window end timestamp
        find_max: If True, find longest; if False, find shortest

    Returns:
        The extremum interval, or None if window is empty
    """
    extremum: Interval | None = None
    extremum_len: int | None = None

    for ivl in tl[win_start:win_end]:
        if ivl.start is None or ivl.end is None:
            continue
        duration = ivl.end - ivl.start

        if extremum_len is None:
            extremum = ivl
            extremum_len = duration
        elif find_max and duration > extremum_len:
            extremum = ivl
            extremum_len = duration
        elif not find_max and duration < extremum_len:
            extremum = ivl
            extremum_len = duration

    return extremum


def _windowed_agg(
    tl: Timeline[Ivl],
    start: date | datetime | int,
    end: date | datetime | int,
    tz: str,
    period: Period,
    agg: Callable[[Timeline[Ivl], int, int], Any],
) -> list[tuple[date, Any]]:
    """Helper to materialize timeline once and apply agg to each period.

    Args:
        tl: Source timeline to fetch from
        start: Query start bound (date | datetime | int)
        end: Query end bound (date | datetime | int)
        tz: Timezone for interpretation
        period: Period type
        agg: Function (timeline, start_ts, end_ts) -> value

    Returns:
        List of (period_label_date, agg_value) tuples
    """
    # Coerce bounds first
    start_ts = _coerce_bound(start, tz)
    end_ts = _coerce_bound(end, tz)

    # Materialize timeline data once
    cached_timeline = make_timeline(*tl[start_ts:end_ts])

    # Generate period windows
    windows = _period_windows(start_ts, end_ts, period, tz)

    # Apply agg to each window
    return [
        (label, agg(cached_timeline, win_start, win_end))
        for label, win_start, win_end in windows
    ]


def _grouped_agg(
    tl: Timeline[Ivl],
    start: date | datetime | int,
    end: date | datetime | int,
    tz: str,
    period: Period,
    group_by: GroupBy,
    agg: Callable[[Timeline[Ivl], int, int], Any],
    combiner: Callable[[list[Any]], Any],
) -> list[tuple[int, Any]]:
    """Helper to aggregate per-window values by cyclic group key.

    Args:
        tl: Source timeline to fetch from
        start: Query start bound
        end: Query end bound
        tz: Timezone for interpretation
        period: Period type (determines slicing granularity)
        group_by: Cyclic dimension to group by
        agg: Function (timeline, start_ts, end_ts) -> value per window
        combiner: Function to combine values in same group (e.g., sum for ints)

    Returns:
        List of (group_key, combined_value) tuples, sorted by key
    """
    # Coerce bounds
    start_ts = _coerce_bound(start, tz)
    end_ts = _coerce_bound(end, tz)

    # Materialize timeline data once
    cached_timeline = make_timeline(*tl[start_ts:end_ts])

    # Generate windows with datetime labels
    windows = _period_windows_with_dt(start_ts, end_ts, period, tz)

    # Aggregate per window, grouping by cyclic key
    buckets: dict[int, list[Any]] = defaultdict(list)
    for label_dt, win_start, win_end in windows:
        key = _extract_group_key(label_dt, group_by)
        value = agg(cached_timeline, win_start, win_end)
        buckets[key].append(value)

    # Combine values per bucket and return sorted by key
    return sorted((key, combiner(values)) for key, values in buckets.items())


def total_duration(
    timeline: Timeline[Interval],
    start: date | datetime | int,
    end: date | datetime | int,
    period: Period = "full",
    tz: str = "UTC",
    group_by: GroupBy | None = None,
) -> list[tuple[date, int]] | list[tuple[int, int]]:
    """Compute total duration covered by timeline over one or more periods.

    Materializes timeline data once, then computes total duration for each period.
    Period boundaries are aligned to calendar grid (hours, days, weeks, months, years).

    Args:
        timeline: Source timeline (fetched once for all periods)
        start: Window start (date → midnight in tz, datetime → as-is,
            int → Unix timestamp)
        end: Window end (exclusive, same interpretation rules)
        period: "hour", "day", "week" (ISO Mon-Sun), "month", "year", or "full"
            (exact bounds)
        tz: Timezone for date interpretation and period boundaries
        group_by: Optional cyclic grouping. When set, aggregates across periods
            with the same cyclic key (e.g., "hour_of_day" aggregates all 9am hours).
            Valid combinations:
            - period="hour" + group_by="hour_of_day" → 24 buckets
            - period="day" + group_by="day_of_week" → 7 buckets
            - period="day" + group_by="day_of_month" → 31 buckets
            - period="week" + group_by="week_of_year" → 53 buckets
            - period="month" + group_by="month_of_year" → 12 buckets

    Returns:
        Without group_by: List of (period_start_date, total_seconds) tuples.
        With group_by: List of (group_key, total_seconds) tuples sorted by key.
        Empty periods return 0.

    Example:
        >>> from datetime import date
        >>> from calgebra import timeline, Interval, total_duration
        >>>
        >>> # Daily duration for November
        >>> t = timeline(Interval(start=1730419200, end=1730505600))  # Nov 1 full day
        >>> daily = total_duration(
        ...     t,
        ...     start=date(2025, 11, 1),
        ...     end=date(2025, 11, 3),
        ...     period="day",
        ...     tz="UTC"
        ... )
        >>> # Returns [(date(2025,11,1), 86400), (date(2025,11,2), 0)]
        >>>
        >>> # Hour-of-day histogram
        >>> hourly = total_duration(
        ...     cal, start, end,
        ...     period="hour", group_by="hour_of_day", tz="US/Pacific"
        ... )
        >>> # Returns [(0, 3600), (1, 0), ..., (9, 54000), ...]
    """
    _validate_period_group_by(period, group_by)

    if group_by is not None:
        return _grouped_agg(
            timeline,
            start,
            end,
            tz,
            period,
            group_by,
            agg=_total_duration,
            combiner=sum,
        )

    return _windowed_agg(timeline, start, end, tz, period, _total_duration)


def max_duration(
    timeline: Timeline[Ivl],
    start: date | datetime | int,
    end: date | datetime | int,
    period: Literal["day", "week", "month", "year", "full"] = "full",
    tz: str = "UTC",
) -> list[tuple[date, Ivl | None]]:
    """Find the longest interval within each period.

    Args:
        timeline: Source timeline (fetched once for all periods)
        start: Window start (date → midnight in tz, datetime → as-is,
            int → Unix timestamp)
        end: Window end (exclusive)
        period: "day", "week", "month", "year", or "full"
        tz: Timezone for date interpretation and period boundaries

    Returns:
        List of (period_start_date, longest_interval) tuples.
        Empty periods return None.
    """

    def _agg(tl, win_start, win_end):
        return _extremum_duration(tl, win_start, win_end, find_max=True)

    return _windowed_agg(timeline, start, end, tz, period, _agg)


def min_duration(
    timeline: Timeline[Ivl],
    start: date | datetime | int,
    end: date | datetime | int,
    period: Literal["day", "week", "month", "year", "full"] = "full",
    tz: str = "UTC",
) -> list[tuple[date, Ivl | None]]:
    """Find the shortest interval within each period.

    Args:
        timeline: Source timeline (fetched once for all periods)
        start: Window start (date → midnight in tz, datetime → as-is,
            int → Unix timestamp)
        end: Window end (exclusive)
        period: "day", "week", "month", "year", or "full"
        tz: Timezone for date interpretation and period boundaries

    Returns:
        List of (period_start_date, shortest_interval) tuples.
        Empty periods return None.
    """

    def _agg(tl, win_start, win_end):
        return _extremum_duration(tl, win_start, win_end, find_max=False)

    return _windowed_agg(timeline, start, end, tz, period, _agg)


def count_intervals(
    timeline: Timeline[Ivl],
    start: date | datetime | int,
    end: date | datetime | int,
    period: Period = "full",
    tz: str = "UTC",
    group_by: GroupBy | None = None,
) -> list[tuple[date, int]] | list[tuple[int, int]]:
    """Count intervals within each period.

    Args:
        timeline: Source timeline (fetched once for all periods)
        start: Window start (date → midnight in tz, datetime → as-is,
            int → Unix timestamp)
        end: Window end (exclusive)
        period: "hour", "day", "week", "month", "year", or "full"
        tz: Timezone for date interpretation and period boundaries
        group_by: Optional cyclic grouping (see total_duration for valid combinations)

    Returns:
        Without group_by: List of (period_start_date, interval_count) tuples.
        With group_by: List of (group_key, interval_count) tuples sorted by key.
        Empty periods return 0.
    """
    _validate_period_group_by(period, group_by)

    def _agg(tl, win_start, win_end):
        return sum(1 for _ in tl[win_start:win_end])

    if group_by is not None:
        return _grouped_agg(
            timeline,
            start,
            end,
            tz,
            period,
            group_by,
            agg=_agg,
            combiner=sum,
        )

    return _windowed_agg(timeline, start, end, tz, period, _agg)


def coverage_ratio(
    timeline: Timeline[Ivl],
    start: date | datetime | int,
    end: date | datetime | int,
    period: Period = "full",
    tz: str = "UTC",
    group_by: GroupBy | None = None,
) -> list[tuple[date, float]] | list[tuple[int, float]]:
    """Compute coverage ratio (fraction of time covered) for each period.

    Materializes timeline data once, then computes coverage for each period.
    Period boundaries are aligned to calendar grid (hours, days, weeks, months, years).

    Args:
        timeline: Source timeline (fetched once for all periods)
        start: Window start (date → midnight in tz, datetime → as-is,
            int → Unix timestamp)
        end: Window end (exclusive, same interpretation rules)
        period: "hour", "day", "week" (ISO Mon-Sun), "month", "year", or "full"
            (exact bounds)
        tz: Timezone for date interpretation and period boundaries
        group_by: Optional cyclic grouping (see total_duration for valid combinations)

    Returns:
        Without group_by: List of (period_start_date, ratio) tuples.
        With group_by: List of (group_key, ratio) tuples sorted by key.
        Ratio is between 0.0 and 1.0. Empty periods return 0.0.

    Example:
        >>> from datetime import date
        >>> from calgebra import coverage_ratio
        >>>
        >>> # Daily coverage for November
        >>> daily = coverage_ratio(
        ...     cal_union,
        ...     start=date(2025, 11, 1),
        ...     end=date(2025, 12, 1),
        ...     period="day",
        ...     tz="US/Pacific"
        ... )
        >>> # Returns 30 tuples: [(date(2025,11,1), 0.73), (date(2025,11,2), 0.81), ...]
    """
    _validate_period_group_by(period, group_by)

    if group_by is not None:
        # For grouped coverage, we need to sum numerator and denominator
        # separately, then divide at the end
        def _agg_tuple(tl, win_start, win_end):
            span = win_end - win_start
            total = _total_duration(tl, win_start, win_end)
            return (total, span)  # (numerator, denominator)

        def _combine_ratios(tuples: list[tuple[int, int]]) -> float:
            total_num = sum(t[0] for t in tuples)
            total_denom = sum(t[1] for t in tuples)
            return total_num / total_denom if total_denom > 0 else 0.0

        return _grouped_agg(
            timeline,
            start,
            end,
            tz,
            period,
            group_by,
            agg=_agg_tuple,
            combiner=_combine_ratios,
        )

    def _agg(tl, win_start, win_end):
        span = win_end - win_start
        if span <= 0:
            return 0.0
        total = _total_duration(tl, win_start, win_end)
        return total / span

    return _windowed_agg(timeline, start, end, tz, period, _agg)
