from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from gcsa.google_calendar import GoogleCalendar
from typing_extensions import override

from calgebra.core import Timeline
from calgebra.interval import Interval


@dataclass(frozen=True, kw_only=True)
class Event(Interval):
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
            duration = self.end - self.start + 1
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

    For end times, ensures inclusive semantics.
    """
    normalized = _normalize_datetime(dt, edge, zone)

    if edge == "start":
        return int(normalized.replace(microsecond=0).timestamp())

    # For end times: Google Calendar uses exclusive end times, but calgebra uses
    # inclusive
    # So we subtract 1 second to make the end inclusive
    if not isinstance(dt, datetime):
        # Date object: already at end of day, but normalize returns start of next day
        start_of_day = _normalize_datetime(dt, "start", zone)
        inclusive = start_of_day + timedelta(days=1, seconds=-1)
        return int(inclusive.replace(microsecond=0).timestamp())

    # Datetime object: subtract 1 second if on exact second boundary
    if normalized.microsecond == 0:
        normalized -= timedelta(seconds=1)

    return int(normalized.replace(microsecond=0).timestamp())


def _timestamp_to_datetime(ts: int) -> datetime:
    """Convert a Unix timestamp to a UTC datetime."""
    return datetime.fromtimestamp(ts, tz=timezone.utc)


class Calendar(Timeline[Event]):
    """Timeline backed by the Google Calendar API using local credentials.

    Events are converted to UTC timestamps. Each event's own timezone (if specified)
    is used when interpreting all-day events or naive datetimes from the API.
    """

    def __init__(
        self,
        calendar_id: str,
        calendar_summary: str,
        *,
        client: GoogleCalendar | None = None,
    ) -> None:
        """Initialize a Calendar timeline.

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

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Event]:
        start_dt = _timestamp_to_datetime(start) if start is not None else None
        # end bounds are inclusive; add a second so Google returns events
        # touching the end (Google uses exclusive end times)
        end_dt = _timestamp_to_datetime(end + 1) if end is not None else None

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


def calendars() -> list[Calendar]:
    """Return calendars accessible to the locally authenticated user."""
    client = GoogleCalendar()
    return [
        Calendar(e.id, e.summary, client=client)
        for e in client.get_calendar_list()
        if e.id is not None and e.summary is not None
    ]
