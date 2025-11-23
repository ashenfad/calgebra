"""Google Calendar integration for mutable timelines.

This module provides GoogleCalendarTimeline, a MutableTimeline implementation
that reads from and writes to Google Calendar via the gcsa library.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from gcsa.event import Event as GcsaEvent
from gcsa.google_calendar import GoogleCalendar
from gcsa.reminders import EmailReminder, PopupReminder
from gcsa.reminders import Reminder as GcsaReminder
from typing_extensions import override

from calgebra.interval import Interval
from calgebra.mutable import MutableTimeline, WriteResult
from calgebra.recurrence import RecurringPattern


@dataclass(frozen=True)
class Reminder:
    """Google Calendar event reminder/notification.

    Attributes:
        method: Reminder method - "email" or "popup"
        minutes: Minutes before event start to trigger reminder
    """

    method: Literal["email", "popup"]
    minutes: int


@dataclass(frozen=True, kw_only=True)
class Event(Interval):
    """Google Calendar event represented as an interval.

    Attributes:
        id: Google Calendar event ID
        calendar_id: ID of the calendar containing this event
        calendar_summary: Human-readable name of the calendar
        summary: Event title/summary
        description: Event description (optional)
        recurring_event_id: ID of the master recurring event
            (None for standalone or master events)
        is_all_day: True if all-day event, False if timed event,
            None to auto-infer when writing
        reminders: List of reminders/notifications for this event
            (None = use calendar defaults)
    """

    id: str
    calendar_id: str
    calendar_summary: str
    summary: str
    description: str | None
    recurring_event_id: str | None = None
    is_all_day: bool | None = None
    reminders: list[Reminder] | None = None

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


def _is_all_day_event(gcsa_event: Any) -> bool:
    """Check if a gcsa event is an all-day event.

    Google Calendar uses start.date (not start.dateTime) for all-day events.
    """
    return (
        hasattr(gcsa_event, "start")
        and hasattr(gcsa_event.start, "date")
        and gcsa_event.start.date is not None
    )


def _extract_reminders(gcsa_event: Any) -> list[Reminder] | None:
    """Extract reminders from a gcsa event.

    Returns:
        List of Reminder objects if custom reminders are set,
        None if using calendar defaults or no reminders.
    """
    if not (
        hasattr(gcsa_event, "reminders") and hasattr(gcsa_event, "default_reminders")
    ):
        return None

    # If default_reminders is True, use None (calendar defaults)
    if gcsa_event.default_reminders:
        return None

    # If reminders list is empty, return None
    if not gcsa_event.reminders:
        return None

    # Convert gcsa Reminder objects to our Reminder dataclass
    reminders = []
    for gcsa_reminder in gcsa_event.reminders:
        if hasattr(gcsa_reminder, "method") and hasattr(
            gcsa_reminder, "minutes_before_start"
        ):
            method = gcsa_reminder.method
            minutes = gcsa_reminder.minutes_before_start
            if method in ("email", "popup") and minutes is not None:
                reminders.append(Reminder(method=method, minutes=minutes))

    return reminders if reminders else None


def _extract_start_datetime(gcsa_event: Any) -> datetime | date:
    """Extract the start datetime/date from a gcsa event.

    Google Calendar events have start.dateTime (for timed) or start.date (for all-day).
    """
    if hasattr(gcsa_event.start, "dateTime") and gcsa_event.start.dateTime is not None:
        return gcsa_event.start.dateTime
    elif hasattr(gcsa_event.start, "date") and gcsa_event.start.date is not None:
        return gcsa_event.start.date
    else:
        # Fallback: assume start is datetime/date directly
        return gcsa_event.start


def _extract_end_datetime(gcsa_event: Any) -> datetime | date:
    """Extract the end datetime/date from a gcsa event.

    Google Calendar events have end.dateTime (for timed) or end.date (for all-day).
    """
    if isinstance(gcsa_event.end, (datetime, date)):
        # end is already a datetime/date directly (from our stub)
        return gcsa_event.end
    elif hasattr(gcsa_event.end, "dateTime") and gcsa_event.end.dateTime is not None:
        # end is an object with .dateTime attribute (from Google Calendar API)
        return gcsa_event.end.dateTime
    elif hasattr(gcsa_event.end, "date") and gcsa_event.end.date is not None:
        # end is an object with .date attribute (from Google Calendar API)
        return gcsa_event.end.date
    else:
        # Fallback: assume end is datetime/date directly
        return gcsa_event.end


def _infer_is_all_day(start_ts: int, end_ts: int, calendar_tz: ZoneInfo | None) -> bool:
    """Infer if an event should be all-day based on timestamps.

    An event is all-day if:
    - Duration is exactly N * DAY (within 1 hour tolerance for DST)
    - Start and end are at midnight boundaries in calendar's timezone

    Args:
        start_ts: Start timestamp (UTC)
        end_ts: End timestamp (UTC)
        calendar_tz: Calendar's default timezone (None = UTC)

    Returns:
        True if event should be all-day, False otherwise
    """
    tz = calendar_tz if calendar_tz is not None else timezone.utc

    # Convert to calendar timezone
    start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc).astimezone(tz)
    end_dt = datetime.fromtimestamp(end_ts, tz=timezone.utc).astimezone(tz)

    # Check if both are at midnight
    if start_dt.time() != time.min or end_dt.time() != time.min:
        return False

    # Check if duration is whole days (within 1 hour tolerance for DST)
    duration = timedelta(seconds=end_ts - start_ts)
    days = duration.days
    remainder = duration - timedelta(days=days)

    # Allow up to 1 hour remainder (for DST transitions)
    if remainder > timedelta(hours=1):
        return False

    return True


def _convert_reminders_to_gcsa(
    reminders: list[Reminder] | None,
) -> list[GcsaReminder] | None:
    """Convert our Reminder objects to gcsa Reminder objects.

    Returns:
        List of gcsa Reminder objects, or None if reminders is None
    """
    if reminders is None:
        return None

    gcsa_reminders: list[GcsaReminder] = []
    for reminder in reminders:
        if reminder.method == "email":
            gcsa_reminders.append(EmailReminder(minutes_before_start=reminder.minutes))
        elif reminder.method == "popup":
            gcsa_reminders.append(PopupReminder(minutes_before_start=reminder.minutes))

    return gcsa_reminders if gcsa_reminders else None


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

    @override
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

            # Extract event data using helper functions
            is_all_day = _is_all_day_event(e)
            recurring_event_id = getattr(e, "recurring_event_id", None)
            reminders = _extract_reminders(e)
            start_dt = _extract_start_datetime(e)
            end_dt = _extract_end_datetime(e)

            yield Event(
                id=e.id,
                calendar_id=self.calendar_id,
                calendar_summary=self.calendar_summary,
                summary=e.summary,
                description=e.description,
                recurring_event_id=recurring_event_id,
                is_all_day=is_all_day,
                reminders=reminders,
                start=_to_timestamp(start_dt, "start", event_zone),
                end=_to_timestamp(end_dt, "end", event_zone),
            )

    # MutableTimeline methods will be implemented in Phase 3
    # For now, these raise NotImplementedError to indicate they're not yet implemented

    @override
    def _add_interval(
        self, interval: Interval, metadata: dict[str, Any]
    ) -> list[WriteResult]:
        """Add a single interval to Google Calendar.

        Converts an Event (Interval subclass) to a Google Calendar event
        and creates it via the gcsa API.

        Args:
            interval: Event to add (must be an Event instance)
            metadata: Additional metadata (currently unused)

        Returns:
            List containing a single WriteResult with the created event
        """
        if not isinstance(interval, Event):
            return [
                WriteResult(
                    success=False,
                    event=None,
                    error=TypeError(f"Expected Event, got {type(interval).__name__}"),
                )
            ]

        if interval.start is None or interval.end is None:
            return [
                WriteResult(
                    success=False,
                    event=None,
                    error=ValueError("Event must have finite start and end"),
                )
            ]

        try:
            # Determine if event is all-day
            is_all_day = interval.is_all_day
            if is_all_day is None:
                # Auto-infer: need calendar's default timezone
                # For now, use UTC (can be improved later with calendar settings)
                is_all_day = _infer_is_all_day(
                    interval.start, interval.end, calendar_tz=None
                )

            # Convert timestamps to datetime/date objects
            if is_all_day:
                # For all-day events, convert UTC timestamps to dates
                # Google Calendar uses dates in the calendar's timezone
                # For now, use UTC (can be improved with calendar settings)
                start_dt = _timestamp_to_datetime(interval.start).date()
                end_dt = _timestamp_to_datetime(interval.end).date()
            else:
                # For timed events, use UTC datetime objects
                start_dt = _timestamp_to_datetime(interval.start)
                end_dt = _timestamp_to_datetime(interval.end)

            # Convert reminders
            gcsa_reminders = _convert_reminders_to_gcsa(interval.reminders)

            # Create gcsa Event object
            gcsa_event = GcsaEvent(
                summary=interval.summary,
                start=start_dt,
                end=end_dt,
                timezone="UTC" if not is_all_day else None,
                description=interval.description,
                reminders=gcsa_reminders,
            )

            # Add event to Google Calendar
            created_event = self.calendar.add_event(
                gcsa_event, calendar_id=self.calendar_id
            )

            # Convert created event back to our Event format
            # We need to fetch it to get the full details, but for now
            # we'll create a new Event with the ID from the created event
            result_event = Event(
                id=created_event.id or "",
                calendar_id=self.calendar_id,
                calendar_summary=self.calendar_summary,
                summary=interval.summary,
                description=interval.description,
                recurring_event_id=None,  # Single events don't have recurring_event_id
                is_all_day=is_all_day,
                reminders=interval.reminders,
                start=interval.start,
                end=interval.end,
            )

            return [WriteResult(success=True, event=result_event, error=None)]

        except Exception as e:
            return [WriteResult(success=False, event=None, error=e)]

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
