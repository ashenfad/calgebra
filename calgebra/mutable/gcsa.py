"""Google Calendar integration for mutable timelines.

This module provides GoogleCalendarTimeline, a MutableTimeline implementation
that reads from and writes to Google Calendar via the gcsa library.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from gcsa.google_calendar import GoogleCalendar
from typing_extensions import override

from calgebra.interval import Interval
from calgebra.mutable import MutableTimeline, WriteResult
from calgebra.recurrence import RecurringPattern


@dataclass(frozen=True, kw_only=True)
class Event(Interval):
    """Google Calendar event represented as an interval.

    Attributes:
        id: Google Calendar event ID
        calendar_id: ID of the calendar containing this event
        calendar_summary: Human-readable name of the calendar
        summary: Event title/summary
        description: Event description (optional)
    """

    id: str
    calendar_id: str
    calendar_summary: str
    summary: str
    description: str | None

    @override
    def __str__(self) -> str:
        """Human-friendly string showing event details and duration."""
        start_str = str(self.start) if self.start is not None else "-∞"
        end_str = str(self.end) if self.end is not None else "+∞"

        if self.start is not None and self.end is not None:
            duration = self.end - self.start
            return f"Event('{self.summary}', {start_str}→{end_str}, {duration}s)"
        else:
            return f"Event('{self.summary}', {start_str}→{end_str}, unbounded)"


def _normalize_datetime(
    dt: datetime | date, edge: Literal["start", "end"], zone: ZoneInfo | None
) -> datetime:
    """Normalize a datetime or date to a UTC datetime.

    For date objects, uses the provided zone (or UTC if none) to determine boundaries.
    For datetime objects, converts to UTC.
    """
    if not isinstance(dt, datetime):
        # Date object: convert to datetime at day boundary
        tz = zone if zone is not None else timezone.utc
        dt = datetime.combine(dt, time.min if edge == "start" else time.max)
        dt = dt.replace(tzinfo=tz)
    elif dt.tzinfo is None:
        # Naive datetime: assume provided zone or UTC
        tz = zone if zone is not None else timezone.utc
        dt = dt.replace(tzinfo=tz)
    else:
        # Timezone-aware datetime: convert to UTC
        dt = dt.astimezone(zone) if zone is not None else dt
    return dt.astimezone(timezone.utc)


def _to_timestamp(
    dt: datetime | date, edge: Literal["start", "end"], zone: ZoneInfo | None
) -> int:
    """Convert a datetime or date to a Unix timestamp.

    Both Google Calendar and calgebra now use exclusive end semantics.
    """
    normalized = _normalize_datetime(dt, edge, zone)

    # Both start and end can be directly converted
    # Google Calendar uses exclusive end times, and so does calgebra now
    return int(normalized.replace(microsecond=0).timestamp())


def _timestamp_to_datetime(ts: int) -> datetime:
    """Convert a Unix timestamp to a UTC datetime."""
    return datetime.fromtimestamp(ts, tz=timezone.utc)


class GoogleCalendarTimeline(MutableTimeline[Event]):
    """Timeline backed by the Google Calendar API using local credentials.

    Events are converted to UTC timestamps. Each event's own timezone (if specified)
    is used when interpreting all-day events or naive datetimes from the API.

    Currently implements read operations (Timeline). Write operations (MutableTimeline)
    will be implemented in Phase 3.
    """

    def __init__(
        self,
        calendar_id: str,
        calendar_summary: str,
        *,
        client: GoogleCalendar | None = None,
    ) -> None:
        """Initialize a Google Calendar timeline.

        Args:
            calendar_id: Calendar ID string
            calendar_summary: Calendar summary string
            client: Optional GoogleCalendar client instance (for testing/reuse)
        """
        self.calendar_id: str = calendar_id
        self.calendar_summary: str = calendar_summary
        self.calendar: GoogleCalendar = (
            client if client is not None else GoogleCalendar(self.calendar_id)
        )

    def __str__(self) -> str:
        return (
            f"GoogleCalendarTimeline(id='{self.calendar_id}', "
            f"summary='{self.calendar_summary}')"
        )

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Event]:
        start_dt = _timestamp_to_datetime(start) if start is not None else None
        # Both calgebra and Google Calendar now use exclusive end bounds
        end_dt = _timestamp_to_datetime(end) if end is not None else None

        events_iterable = (
            self.calendar.get_events(  # pyright: ignore[reportUnknownMemberType]
                time_min=start_dt,
                time_max=end_dt,
                single_events=True,
                order_by="startTime",
                calendar_id=self.calendar_id,
            )
        )

        for e in events_iterable:
            if e.id is None or e.summary is None or e.end is None:
                continue

            # Use event's own timezone if available, otherwise UTC
            event_zone = ZoneInfo(e.timezone) if e.timezone else None

            yield Event(
                id=e.id,
                calendar_id=self.calendar_id,
                calendar_summary=self.calendar_summary,
                summary=e.summary,
                description=e.description,
                start=_to_timestamp(e.start, "start", event_zone),
                end=_to_timestamp(e.end, "end", event_zone),
            )

    # MutableTimeline methods will be implemented in Phase 3
    # For now, these raise NotImplementedError to indicate they're not yet implemented

    @override
    def _add_interval(
        self, interval: Interval, metadata: dict[str, Any]
    ) -> list[WriteResult]:
        """Add a single interval to Google Calendar.

        Not yet implemented - will be added in Phase 3.
        """
        raise NotImplementedError("Write operations not yet implemented")

    @override
    def _add_recurring(
        self, pattern: RecurringPattern[Event], metadata: dict[str, Any]
    ) -> list[WriteResult]:
        """Add a recurring pattern to Google Calendar.

        Not yet implemented - will be added in Phase 3.
        """
        raise NotImplementedError("Write operations not yet implemented")

    @override
    def _remove_interval(self, interval: Interval) -> list[WriteResult]:
        """Remove a single interval from Google Calendar.

        Not yet implemented - will be added in Phase 3.
        """
        raise NotImplementedError("Write operations not yet implemented")

    @override
    def _remove_series(self, interval: Interval) -> list[WriteResult]:
        """Remove a recurring series from Google Calendar.

        Not yet implemented - will be added in Phase 3.
        """
        raise NotImplementedError("Write operations not yet implemented")

    @override
    def _remove_many(self, intervals: Iterable[Interval]) -> list[WriteResult]:
        """Remove multiple intervals from Google Calendar.

        Not yet implemented - will be added in Phase 3.
        """
        raise NotImplementedError("Write operations not yet implemented")

    @override
    def _remove_many_series(self, intervals: Iterable[Interval]) -> list[WriteResult]:
        """Remove multiple recurring series from Google Calendar.

        Not yet implemented - will be added in Phase 3.
        """
        raise NotImplementedError("Write operations not yet implemented")


def calendars() -> list[GoogleCalendarTimeline]:
    """Return calendars accessible to the locally authenticated user.

    Returns:
        List of GoogleCalendarTimeline instances, one per accessible calendar
    """
    client = GoogleCalendar()
    return [
        GoogleCalendarTimeline(e.id, e.summary, client=client)
        for e in client.get_calendar_list()
        if e.id is not None and e.summary is not None
    ]

