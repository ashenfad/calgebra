"""DataFrame conversion helpers for calgebra timelines.

Convert iterables of Intervals into pandas DataFrames with sensible defaults.

Requires: pip install calgebra[pandas]
"""

from collections.abc import Iterable
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except ImportError:
    pd = None  # type: ignore
    PANDAS_AVAILABLE = False

from calgebra.interval import Interval

# Core columns shown first (curated order)
_CORE_COLUMNS = ["day", "time", "duration"]

# Type-specific leading columns (before core columns)
_TYPE_LEADING: dict[str, list[str]] = {
    "ICalEvent": ["calendar_name"],
    "Event": ["calendar_summary"],  # gcsa.Event
    "Interval": [],
}

# Type-specific trailing columns (after core columns)
_TYPE_TRAILING: dict[str, list[str]] = {
    "ICalEvent": ["summary"],
    "Event": ["summary"],  # gcsa.Event
    "Interval": [],
}

# Fields to exclude from metadata
_EXCLUDED_FIELDS = {"start", "end", "finite_start", "finite_end"}


def _resolve_zone(tz: str) -> ZoneInfo:
    """Resolve a timezone name into a ZoneInfo object."""
    try:
        return ZoneInfo(tz)
    except Exception:
        return ZoneInfo("UTC")


def _format_day(ts: int | None, zone: ZoneInfo, is_all_day: bool = False) -> str:
    """Format the day portion of a timestamp.

    Shows relative dates:
    - 'Today' or 'Tomorrow' for nearby dates
    - 'Tue, Dec 7' for current year
    - 'Tue, Dec 7, 2025' for other years
    """
    if ts is None:
        return "—"

    if is_all_day:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    else:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(zone)

    now = datetime.now(tz=zone if not is_all_day else timezone.utc)
    today = now.date()
    event_date = dt.date()
    day_diff = (event_date - today).days

    if day_diff == 0:
        return "Today"
    elif day_diff == 1:
        return "Tomorrow"

    if event_date.year == today.year:
        # Use %d and strip leading zero for cross-platform compatibility
        day = dt.strftime("%d").lstrip("0")
        return dt.strftime(f"%a, %b {day}")
    else:
        day = dt.strftime("%d").lstrip("0")
        return dt.strftime(f"%a, %b {day}, %Y")


def _format_time(ts: int | None, zone: ZoneInfo, is_all_day: bool = False) -> str:
    """Format the time portion of a timestamp."""
    if ts is None:
        return "—"
    if is_all_day:
        return "All day"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(zone)
    # Use %I and strip leading zero for cross-platform compatibility
    hour = dt.strftime("%I").lstrip("0")
    return f"{hour}:{dt.strftime('%M%p').lower()}"


def _format_duration(start: int | None, end: int | None) -> str:
    """Format duration between two timestamps."""
    if start is None or end is None:
        return "—"
    seconds = max(0, end - start)
    units = [("d", 86_400), ("h", 3_600), ("m", 60)]
    for suffix, divisor in units:
        if seconds >= divisor:
            value = seconds / divisor
            return f"{value:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{seconds}s"


def _get_type_name(ivl: Interval) -> str:
    """Get the type name for column defaults lookup."""
    return type(ivl).__name__


def _is_all_day(ivl: Interval, zone: ZoneInfo) -> bool:
    """Check if interval represents an all-day event."""
    # Check for ICalEvent.is_all_day attribute first
    if hasattr(ivl, "is_all_day"):
        return bool(getattr(ivl, "is_all_day"))

    # Heuristic: starts and ends at midnight
    if ivl.start is None or ivl.end is None:
        return False
    start_dt = datetime.fromtimestamp(ivl.start, tz=timezone.utc).astimezone(zone)
    end_dt = datetime.fromtimestamp(ivl.end, tz=timezone.utc).astimezone(zone)
    return (
        start_dt.hour == 0
        and start_dt.minute == 0
        and end_dt.hour == 0
        and end_dt.minute == 0
    )


def _get_metadata_fields(ivl: Interval) -> list[str]:
    """Get dataclass field names excluding core interval fields."""
    if not is_dataclass(ivl):
        return []
    return [f.name for f in fields(ivl) if f.name not in _EXCLUDED_FIELDS]


def to_dataframe(
    intervals: Iterable[Interval],
    tz: str = "UTC",
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    raw: bool = False,
) -> "pd.DataFrame":
    """Convert intervals (or its subclasses) to a pandas DataFrame.

    Args:
        intervals: Iterable of Interval or subclass instances
        tz: Timezone for datetime formatting (default: "UTC")
        include: Explicit columns to include (overrides defaults)
        exclude: Columns to drop from defaults
        raw: If True, output raw datetime objects instead of formatted strings

    Returns:
        DataFrame with interval data. Column order:
        1. Core columns (day, time, duration)
        2. Type-specific columns (summary, location, etc.)
        3. Remaining metadata in definition order

    Raises:
        ImportError: If pandas is not installed

    Example:
        >>> from calgebra import to_dataframe
        >>> df = to_dataframe(calendar[start:end], tz="US/Pacific")
    """
    if not PANDAS_AVAILABLE:
        raise ImportError(
            "pandas is required for to_dataframe(). "
            "Install with: pip install calgebra[pandas]"
        )

    # Consume iterable into list
    items = list(intervals)
    if not items:
        return pd.DataFrame()

    zone = _resolve_zone(tz)
    sample = items[0]
    type_name = _get_type_name(sample)

    # Determine columns
    if include is not None:
        columns = list(include)
    else:
        # Leading + Core + Trailing (no auto-metadata)
        leading = _TYPE_LEADING.get(type_name, [])
        trailing = _TYPE_TRAILING.get(type_name, [])
        columns = leading + _CORE_COLUMNS + trailing

    if exclude:
        columns = [c for c in columns if c not in exclude]

    # Build rows
    rows: list[dict[str, Any]] = []
    for ivl in items:
        all_day = _is_all_day(ivl, zone)
        row: dict[str, Any] = {}

        for col in columns:
            if col == "day":
                if raw:
                    if ivl.start is not None:
                        row[col] = datetime.fromtimestamp(
                            ivl.start, tz=timezone.utc
                        ).astimezone(zone)
                    else:
                        row[col] = None
                else:
                    row[col] = _format_day(ivl.start, zone, is_all_day=all_day)
            elif col == "time":
                if raw:
                    if ivl.start is not None:
                        row[col] = datetime.fromtimestamp(
                            ivl.start, tz=timezone.utc
                        ).astimezone(zone)
                    else:
                        row[col] = None
                else:
                    row[col] = _format_time(ivl.start, zone, is_all_day=all_day)
            elif col == "duration":
                if raw:
                    row[col] = ivl.duration
                else:
                    row[col] = _format_duration(ivl.start, ivl.end)
            else:
                # Metadata field
                row[col] = getattr(ivl, col, None)

        rows.append(row)

    df = pd.DataFrame(rows, columns=columns)

    # Drop columns where all values are None or empty string
    def _is_empty(val: Any) -> bool:
        return val is None or val == "" or (isinstance(val, tuple) and len(val) == 0)

    empty_cols = [col for col in df.columns if df[col].apply(_is_empty).all()]
    df = df.drop(columns=empty_cols)

    return df
