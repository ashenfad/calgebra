"""Google Calendar integration for calgebra.

This module provides Calendar, a MutableTimeline implementation
that reads from and writes to Google Calendar via the gcsa library.

Example:
    >>> from calgebra.gcsa import calendars, Event, Calendar
    >>> from calgebra import at_tz
    >>>
    >>> # Get all accessible calendars
    >>> cals = calendars()
    >>> primary: Calendar = cals[0]
    >>>
    >>> # Read events
    >>> at = at_tz("US/Pacific")
    >>> events = list(primary[at("2025-01-01"):at("2025-01-31")])
    >>>
    >>> # Add an event
    >>> new_event = Event.from_datetimes(
    ...     start=at(2025, 1, 15, 14, 0),
    ...     end=at(2025, 1, 15, 15, 0),
    ...     summary="Team Meeting",
    ...     calendar_id=primary.calendar_id,
    ...     calendar_summary=primary.calendar_summary,
    ... )
    >>> primary.add(new_event)
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from functools import wraps
from typing import Any, Callable, Literal, TypeVar
from zoneinfo import ZoneInfo

from gcsa.event import Event as GcsaEvent
from gcsa.google_calendar import GoogleCalendar
from gcsa.reminders import EmailReminder, PopupReminder
from gcsa.reminders import Reminder as GcsaReminder
from typing_extensions import override

from calgebra.interval import Interval, IvlOut
from calgebra.mutable import MutableTimeline, WriteResult
from calgebra.recurrence import RecurringPattern
from calgebra.util import DAY

# Type variable for write operation methods
_F = TypeVar("_F", bound=Callable[..., list[WriteResult]])

# Constants
_UTC_TIMEZONE = "UTC"
_EXDATE_FORMAT = "%Y%m%dT%H%M%SZ"

# Re-export WriteResult for convenience
__all__ = ["Event", "Calendar", "Reminder", "WriteResult", "calendars"]


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
        id: Google Calendar event ID (optional for new events - auto-filled by Calendar)
        calendar_id: ID of the calendar containing this event
            (ignored on write - always uses target calendar's ID)
        calendar_summary: Human-readable name of the calendar
            (ignored on write - always uses target calendar's summary)
        summary: Event title/summary
        description: Event description (optional)
        recurring_event_id: ID of the master recurring event
            (None for standalone or master events)
        is_all_day: True if all-day event, False if timed event,
            None to auto-infer when writing
        reminders: List of reminders/notifications for this event
            (None = use calendar defaults)
    """

    id: str = ""  # Optional for new events (auto-filled by Calendar on add)
    calendar_id: str = ""  # Optional for new events (auto-filled by Calendar)
    calendar_summary: str = ""  # Optional for new events (auto-filled by Calendar)
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


def _normalize_datetime(dt: datetime | date, zone: ZoneInfo | None) -> datetime:
    """Normalize a datetime or date to a UTC datetime.

    For date objects, uses the provided zone (or UTC if none) to interpret the date
    as midnight in that timezone, then converts to UTC.

    For datetime objects, converts directly to UTC.
    """
    if not isinstance(dt, datetime):
        # Date object: interpret as midnight in the provided zone
        tz = zone if zone is not None else timezone.utc
        dt = datetime.combine(dt, time.min, tzinfo=tz)
    elif dt.tzinfo is None:
        # Naive datetime: assume provided zone or UTC
        tz = zone if zone is not None else timezone.utc
        dt = dt.replace(tzinfo=tz)
    # Convert to UTC (works for both naive-with-tz and aware datetimes)
    return dt.astimezone(timezone.utc)


def _to_timestamp(dt: datetime | date, zone: ZoneInfo | None) -> int:
    """Convert a datetime or date to a Unix timestamp.

    Both Google Calendar and calgebra use exclusive end semantics.
    """
    normalized = _normalize_datetime(dt, zone)
    return int(normalized.replace(microsecond=0).timestamp())


def _timestamp_to_datetime(ts: int) -> datetime:
    """Convert a Unix timestamp to a UTC datetime."""
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _is_all_day_event(gcsa_event: Any) -> bool:
    """Check if a gcsa event is an all-day event.

    Google Calendar uses start.date (not start.dateTime) for all-day events.
    For recurring event instances, we also check duration and time.
    """
    if not hasattr(gcsa_event, "start") or not hasattr(gcsa_event, "end"):
        return False

    # Extract start/end - this handles various Google Calendar formats
    start_dt = _extract_datetime(gcsa_event.start)
    end_dt = _extract_datetime(gcsa_event.end)

    # Primary check: If start/end are date objects (not datetime), it's an all-day event
    # Note: datetime is a subclass of date, so we must check datetime first
    if isinstance(start_dt, date) and not isinstance(start_dt, datetime):
        if isinstance(end_dt, date) and not isinstance(end_dt, datetime):
            return True

    # Secondary check: Google Calendar uses start.date attribute (not method)
    # for all-day events
    # Need to check if it's actually an attribute, not the datetime.date() method
    if hasattr(gcsa_event.start, "date"):
        # Check if it's an attribute (not a method) by seeing if it's callable
        date_attr = getattr(gcsa_event.start, "date", None)
        # If it's not callable, it's an attribute (Google Calendar API format)
        # If it's callable, it's the datetime.date() method (not what we want)
        if date_attr is not None and not callable(date_attr):
            return True

    # Fallback for recurring instances: check if duration is ~24 hours and
    # starts at midnight. This handles cases where Google Calendar returns
    # dateTime for recurring all-day instances
    # Both must be datetime objects (not dates) for this check
    if isinstance(start_dt, datetime) and isinstance(end_dt, datetime):
        # Get timezone (use event timezone or UTC)
        event_tz = (
            ZoneInfo(gcsa_event.timezone)
            if hasattr(gcsa_event, "timezone") and gcsa_event.timezone
            else timezone.utc
        )

        # Convert to event timezone (use copies to avoid modifying originals)
        start_local = (
            start_dt.astimezone(event_tz)
            if start_dt.tzinfo
            else start_dt.replace(tzinfo=event_tz)
        )
        end_local = (
            end_dt.astimezone(event_tz)
            if end_dt.tzinfo
            else end_dt.replace(tzinfo=event_tz)
        )

        # Check if starts at midnight
        if start_local.time() != time.min:
            return False

        # Check if duration is whole days (all-day events can span multiple days)
        # Allow up to 1 hour remainder per day for DST transitions
        duration = end_local - start_local
        days = duration.days
        if days >= 1:  # At least 1 day
            remainder = duration - timedelta(days=days)
            # Allow up to 1 hour remainder total (for DST transitions)
            if remainder <= timedelta(hours=1):
                return True

    return False


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


def _extract_datetime(value: Any) -> datetime | date:
    """Extract a datetime/date from a gcsa event attribute.

    Handles both Google Calendar API format (with .dateTime/.date attributes)
    and direct datetime/date values (from stubs or other sources).
    """
    if isinstance(value, (datetime, date)):
        # Value is already a datetime/date directly
        return value
    elif hasattr(value, "dateTime") and value.dateTime is not None:
        # Value is an object with .dateTime attribute (from Google Calendar API)
        return value.dateTime
    elif hasattr(value, "date") and value.date is not None:
        # Value is an object with .date attribute (from Google Calendar API)
        return value.date
    else:
        # Fallback: assume value is datetime/date directly
        return value


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
    start_dt = datetime.fromtimestamp(start_ts, tz=tz)
    end_dt = datetime.fromtimestamp(end_ts, tz=tz)

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


def _format_exdate(timestamp: int) -> str:
    """Format a UTC timestamp as an RFC 5545 EXDATE string.

    Args:
        timestamp: UTC timestamp in seconds

    Returns:
        EXDATE string in format YYYYMMDDTHHMMSSZ
    """
    dt = _timestamp_to_datetime(timestamp)
    return dt.strftime(_EXDATE_FORMAT)


def _parse_exdates_from_rrule(rrule_str: str) -> tuple[str, list[str]]:
    """Parse EXDATE from an RRULE string.

    Args:
        rrule_str: RRULE string potentially containing EXDATE

    Returns:
        Tuple of (base_rrule_without_exdate, list_of_exdate_strings)
    """
    exdate_match = re.search(r"EXDATE[:=]([^;]+)", rrule_str)
    if exdate_match:
        exdates = exdate_match.group(1).split(",")
        base_rrule = re.sub(r";EXDATE[:=][^;]+", "", rrule_str)
        return base_rrule, exdates
    else:
        return rrule_str, []


def _add_exdate_to_rrule(rrule_str: str, exdate_str: str) -> str:
    """Add an EXDATE to an RRULE string.

    Args:
        rrule_str: Base RRULE string
        exdate_str: EXDATE string to add

    Returns:
        RRULE string with EXDATE appended
    """
    base_rrule, existing_exdates = _parse_exdates_from_rrule(rrule_str)
    if exdate_str not in existing_exdates:
        existing_exdates.append(exdate_str)
    exdate_part = "EXDATE:" + ",".join(existing_exdates)
    return f"{base_rrule};{exdate_part}"


def _convert_timestamps_to_datetime(
    start_ts: int, end_ts: int, is_all_day: bool
) -> tuple[datetime | date, datetime | date]:
    """Convert UTC timestamps to datetime/date objects for Google Calendar.

    Args:
        start_ts: Start timestamp (UTC)
        end_ts: End timestamp (UTC)
        is_all_day: Whether the event is all-day

    Returns:
        Tuple of (start_datetime_or_date, end_datetime_or_date)
    """
    if is_all_day:
        start_dt = _timestamp_to_datetime(start_ts).date()
        end_dt = _timestamp_to_datetime(end_ts).date()
    else:
        start_dt = _timestamp_to_datetime(start_ts)
        end_dt = _timestamp_to_datetime(end_ts)
    return start_dt, end_dt


def _error_result(error: Exception) -> list[WriteResult]:
    """Create a WriteResult list for an error.

    Args:
        error: The exception that occurred

    Returns:
        List containing a single WriteResult with success=False
    """
    return [WriteResult(success=False, event=None, error=error)]


def _handle_write_errors(func: _F) -> _F:
    """Decorator to wrap write operations with error handling.

    Catches all exceptions and converts them to WriteResult lists,
    reducing boilerplate in write methods.

    Args:
        func: Write operation method that returns list[WriteResult]

    Returns:
        Wrapped function that catches exceptions and returns error results
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> list[WriteResult]:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return _error_result(e)

    return wrapper  # type: ignore[return-value]


def _validate_event(
    interval: Interval, require_id: bool = True
) -> tuple[Event | None, list[WriteResult] | None]:
    """Validate that an interval is an Event with required fields.

    Args:
        interval: Interval to validate
        require_id: If True, require that the event has a non-empty ID

    Returns:
        Tuple of (Event, None) if valid, or (None, error_results) if invalid
    """
    if not isinstance(interval, Event):
        return None, [
            WriteResult(
                success=False,
                event=None,
                error=TypeError(f"Expected Event, got {type(interval).__name__}"),
            )
        ]

    if require_id and not interval.id:
        return None, [
            WriteResult(
                success=False,
                event=None,
                error=ValueError("Event must have an ID"),
            )
        ]

    return interval, None


@dataclass
class _PreparedEvent:
    """Event prepared for writing to Google Calendar."""

    event: Event  # Event with calendar metadata set
    start: int  # Start timestamp
    end: int  # End timestamp
    is_all_day: bool
    start_dt: datetime | date
    end_dt: datetime | date


def _prepare_event_for_add(
    interval: Interval,
    calendar_id: str,
    calendar_summary: str,
    calendar_tz: ZoneInfo | None,
) -> _PreparedEvent | WriteResult:
    """Validate and prepare an event for adding to Google Calendar.

    Args:
        interval: Interval to validate and prepare
        calendar_id: Target calendar ID
        calendar_summary: Target calendar summary
        calendar_tz: Calendar timezone for all-day inference

    Returns:
        PreparedEvent if valid, or WriteResult with error if invalid
    """
    # Validate event type
    validated, error_result = _validate_event(interval, require_id=False)
    if error_result:
        return error_result[0]

    event = validated
    assert event is not None

    # Validate bounds
    if event.start is None or event.end is None:
        return WriteResult(
            success=False,
            event=event,
            error=ValueError("Event must have finite start and end"),
        )

    start = event.start
    end = event.end

    # Set calendar metadata and strip ID
    event = replace(
        event,
        id="",
        calendar_id=calendar_id,
        calendar_summary=calendar_summary,
    )

    # Infer all-day if not specified
    is_all_day = event.is_all_day
    if is_all_day is None:
        is_all_day = _infer_is_all_day(start, end, calendar_tz)

    # Convert timestamps to datetime/date
    start_dt, end_dt = _convert_timestamps_to_datetime(start, end, is_all_day)

    return _PreparedEvent(
        event=event,
        start=start,
        end=end,
        is_all_day=is_all_day,
        start_dt=start_dt,
        end_dt=end_dt,
    )


def _build_gcsa_event(prepared: _PreparedEvent) -> GcsaEvent:
    """Build a gcsa Event object from prepared event data."""
    gcsa_reminders = _convert_reminders_to_gcsa(prepared.event.reminders)
    return GcsaEvent(
        summary=prepared.event.summary,
        start=prepared.start_dt,
        end=prepared.end_dt,
        timezone=_UTC_TIMEZONE if not prepared.is_all_day else None,
        description=prepared.event.description,
        reminders=gcsa_reminders,
    )


def _build_event_body(prepared: _PreparedEvent) -> dict[str, Any]:
    """Build raw API event body dict from prepared event data.

    Used for batch API which requires raw dicts instead of gcsa objects.
    """
    body: dict[str, Any] = {
        "summary": prepared.event.summary,
        "start": {},
        "end": {},
    }

    if prepared.is_all_day:
        body["start"]["date"] = (
            prepared.start_dt.isoformat()
            if hasattr(prepared.start_dt, "isoformat")
            else str(prepared.start_dt)
        )
        body["end"]["date"] = (
            prepared.end_dt.isoformat()
            if hasattr(prepared.end_dt, "isoformat")
            else str(prepared.end_dt)
        )
    else:
        assert isinstance(prepared.start_dt, datetime)
        assert isinstance(prepared.end_dt, datetime)
        body["start"]["dateTime"] = prepared.start_dt.isoformat()
        body["start"]["timeZone"] = _UTC_TIMEZONE
        body["end"]["dateTime"] = prepared.end_dt.isoformat()
        body["end"]["timeZone"] = _UTC_TIMEZONE

    if prepared.event.description:
        body["description"] = prepared.event.description

    if prepared.event.reminders is not None:
        body["reminders"] = {
            "useDefault": False,
            "overrides": [
                {"method": r.method, "minutes": r.minutes}
                for r in prepared.event.reminders
            ],
        }

    return body


def _build_result_event(
    prepared: _PreparedEvent,
    event_id: str,
) -> Event:
    """Build result Event from prepared data and created event ID."""
    return Event(
        id=event_id,
        calendar_id=prepared.event.calendar_id,
        calendar_summary=prepared.event.calendar_summary,
        summary=prepared.event.summary,
        description=prepared.event.description,
        recurring_event_id=None,
        is_all_day=prepared.is_all_day,
        reminders=prepared.event.reminders,
        start=prepared.start,
        end=prepared.end,
    )


class Calendar(MutableTimeline[Event]):
    """Timeline backed by the Google Calendar API using local credentials.

    Events are converted to UTC timestamps. All-day events are interpreted using
    the calendar's timezone (fetched from Google Calendar API), while timed events
    use the event's own timezone (if specified) or UTC.

    Supports full read/write operations including:
    - Creating single and recurring events
    - Removing events and recurring series
    - Handling all-day events and reminders
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
            client if client is not None else GoogleCalendar()
        )
        # Fetch calendar timezone for interpreting all-day event dates.
        # Google Calendar uses the calendar's timezone (not UTC) for all-day events.
        # We cache this to avoid repeated API calls.
        self._calendar_timezone: ZoneInfo | None = None
        try:
            cal_info = self.calendar.get_calendar(calendar_id=self.calendar_id)
            tz_str = getattr(cal_info, "timezone", None)
            if tz_str:
                self._calendar_timezone = ZoneInfo(tz_str)
        except Exception:
            # Gracefully handle: API errors, stub/mock calendars without get_calendar,
            # invalid timezone strings, etc. Fall back to UTC (None) for all-day events.
            pass

    @override
    def __str__(self) -> str:
        return (
            f"Calendar(id='{self.calendar_id}', " f"summary='{self.calendar_summary}')"
        )

    @override
    def fetch(
        self, start: int | None, end: int | None, *, reverse: bool = False
    ) -> Iterable[Event]:
        if reverse:
            return self._fetch_reverse(start, end)
        return self._fetch_forward(start, end)

    def _fetch_forward(self, start: int | None, end: int | None) -> Iterable[Event]:
        """Forward iteration through calendar events."""
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
            event_zone = ZoneInfo(e.timezone) if e.timezone else ZoneInfo(_UTC_TIMEZONE)

            # Extract event data using helper functions
            is_all_day = _is_all_day_event(e)
            recurring_event_id = getattr(e, "recurring_event_id", None)
            reminders = _extract_reminders(e)
            evt_start_dt = _extract_datetime(e.start)
            evt_end_dt = _extract_datetime(e.end)

            # For all-day events, normalize dates using the calendar's timezone.
            # Google Calendar interprets all-day event dates in the calendar's
            # timezone, not UTC.
            # For timed events, use the event's timezone.
            if is_all_day:
                # Use cached calendar timezone, fallback to event timezone
                # (for testing/stubs), then UTC
                zone_for_timestamp = (
                    self._calendar_timezone
                    if self._calendar_timezone is not None
                    else event_zone if e.timezone else ZoneInfo(_UTC_TIMEZONE)
                )
            else:
                zone_for_timestamp = event_zone

            yield Event(
                id=e.id,
                calendar_id=self.calendar_id,
                calendar_summary=self.calendar_summary,
                summary=e.summary,
                description=e.description,
                recurring_event_id=recurring_event_id,
                is_all_day=is_all_day,
                reminders=reminders,
                start=_to_timestamp(evt_start_dt, zone_for_timestamp),
                end=_to_timestamp(evt_end_dt, zone_for_timestamp),
            )

    def _fetch_reverse(self, start: int | None, end: int | None) -> Iterable[Event]:
        """Reverse iteration through calendar events using windowed pagination.

        Google Calendar API doesn't support reverse ordering or previous page
        tokens, so we fetch in time windows moving backward and reverse each
        window's results.
        """
        if end is None:
            raise ValueError(
                "Reverse iteration on Calendar requires finite end bound.\n"
                "Fix: Use explicit end when slicing: calendar[start:end:-1]\n"
                "Example: list(calendar[at('2024-01-01'):at('2025-01-01'):-1])"
            )

        # Default start to 1 year before end if not specified
        if start is None:
            start = end - (365 * DAY)

        # Window size: 30 days is reasonable for most calendars
        window_size = 30 * DAY

        current_end = end

        while current_end > start:
            window_start = max(start, current_end - window_size)

            # Fetch this window forward, then reverse
            window_events = list(self._fetch_forward(window_start, current_end))
            yield from reversed(window_events)

            current_end = window_start

    @override
    @_handle_write_errors
    def _add_interval(
        self, interval: Interval, metadata: dict[str, Any]
    ) -> list[WriteResult]:
        """Add a single interval to Google Calendar.

        Converts an Event (Interval subclass) to a Google Calendar event
        and creates it via the gcsa API.

        Args:
            interval: Event to add (must be an Event instance)
            metadata: Additional metadata (unused for single events)

        Returns:
            List containing a single WriteResult with the created event
        """
        # Prepare event for writing
        result = _prepare_event_for_add(
            interval,
            self.calendar_id,
            self.calendar_summary,
            self._calendar_timezone,
        )
        if isinstance(result, WriteResult):
            return [result]

        prepared = result

        # Create gcsa Event and add to calendar
        gcsa_event = _build_gcsa_event(prepared)
        created_event = self.calendar.add_event(
            gcsa_event, calendar_id=self.calendar_id
        )

        # Validate that we got an ID back
        if not created_event.id:
            return _error_result(
                ValueError("Google Calendar did not return an event ID")
            )

        # Build result event
        result_event = _build_result_event(prepared, created_event.id)
        return [WriteResult(success=True, event=result_event, error=None)]

    @override
    @_handle_write_errors
    def _add_recurring(
        self, pattern: RecurringPattern[IvlOut], metadata: dict[str, Any]
    ) -> list[WriteResult]:
        """Add a recurring pattern to Google Calendar.

        Converts a RecurringPattern to a Google Calendar recurring event
        with RRULE and handles exdates.

        Args:
            pattern: RecurringPattern to add (can use any interval_class)
            metadata: Additional metadata to merge with pattern metadata
                     (must include 'summary' at minimum for Event creation)

        Returns:
            List containing a single WriteResult with the created recurring event
        """
        # Always use this calendar's metadata
        # (ignore any calendar_id/calendar_summary in metadata)
        # This allows moving recurring patterns between calendars
        metadata["calendar_id"] = self.calendar_id
        metadata["calendar_summary"] = self.calendar_summary

        # Merge metadata
        merged_metadata = {**pattern.metadata, **metadata}

        # Determine if all-day (duration == DAY means all-day)
        is_all_day = pattern.duration_seconds == DAY

        # Get RRULE string with required "RRULE:" prefix for Google Calendar API
        rrule_str = f"RRULE:{pattern.to_rrule_string()}"

        # Add EXDATE if there are exdates
        if pattern.exdates:
            # Convert exdates (timestamps) to EXDATE format
            for exdate_ts in sorted(pattern.exdates):
                exdate_str = _format_exdate(exdate_ts)
                rrule_str = _add_exdate_to_rrule(rrule_str, exdate_str)

        # Determine series start date/time (DTSTART for Google Calendar)
        # Priority:
        #   1. metadata["start"] - explicit first occurrence timestamp
        #   2. pattern.anchor_timestamp - if pattern was created with full timestamp
        #   3. Compute from pattern's time-of-day + today's date
        if "start" in merged_metadata:
            series_start_ts = merged_metadata["start"]
        elif pattern.anchor_timestamp is not None:
            series_start_ts = pattern.anchor_timestamp
        else:
            # No anchor: use today + time-of-day
            now_in_tz = datetime.now(pattern.zone)
            today_midnight = now_in_tz.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            start_delta = timedelta(seconds=pattern.start_seconds)
            series_start_dt_tz = today_midnight + start_delta
            series_start_ts = int(series_start_dt_tz.timestamp())

        series_end_ts = series_start_ts + pattern.duration_seconds

        # Convert start timestamp to datetime/date
        # For recurring events, use the pattern's timezone so BYDAY is interpreted correctly
        if is_all_day:
            series_start_dt: datetime | date = _timestamp_to_datetime(
                series_start_ts
            ).date()
            series_end_dt: datetime | date = _timestamp_to_datetime(
                series_end_ts
            ).date()
        else:
            # Convert to pattern's timezone, not UTC
            series_start_dt = datetime.fromtimestamp(series_start_ts, tz=pattern.zone)
            series_end_dt = datetime.fromtimestamp(series_end_ts, tz=pattern.zone)

        # Extract Event fields from metadata
        summary = merged_metadata.get("summary", "Recurring Event")
        description = merged_metadata.get("description")

        # Convert reminders if provided in metadata
        reminders = merged_metadata.get("reminders")
        if isinstance(reminders, list):
            # Validate that reminders are Reminder objects
            if not all(isinstance(r, Reminder) for r in reminders):
                return _error_result(
                    TypeError("reminders metadata must contain Reminder objects")
                )
            gcsa_reminders = _convert_reminders_to_gcsa(reminders)
            validated_reminders = reminders
        else:
            gcsa_reminders = None
            validated_reminders = None

        # Create gcsa Event with recurrence
        # Use pattern's timezone for recurring events so BYDAY is interpreted correctly
        # (e.g., "Tuesday 6pm Pacific" should stay Tuesday, not become Wednesday in UTC)
        event_timezone = str(pattern.zone) if not is_all_day else None
        gcsa_event = GcsaEvent(
            summary=summary,
            start=series_start_dt,
            end=series_end_dt,
            timezone=event_timezone,
            description=description,
            reminders=gcsa_reminders,
            recurrence=rrule_str,  # gcsa accepts RRULE string
        )

        # Add event to Google Calendar
        created_event = self.calendar.add_event(
            gcsa_event, calendar_id=self.calendar_id
        )

        # Validate that we got an ID back
        if not created_event.id:
            return _error_result(
                ValueError("Google Calendar did not return an event ID")
            )

        # Create result Event (representing the master recurring event)
        # Master events have recurring_event_id = None
        result_event = Event(
            id=created_event.id,
            calendar_id=self.calendar_id,
            calendar_summary=self.calendar_summary,
            summary=summary,
            description=description,
            recurring_event_id=None,  # Master events don't have recurring_event_id
            is_all_day=is_all_day,
            reminders=validated_reminders,
            start=series_start_ts,
            end=series_start_ts + pattern.duration_seconds,
        )

        return [WriteResult(success=True, event=result_event, error=None)]

    @override
    @_handle_write_errors
    def _remove_interval(self, interval: Interval) -> list[WriteResult]:
        """Remove a single interval from Google Calendar.

        If the interval is a recurring event instance (has `recurring_event_id`),
        adds it to the master event's exdates instead of deleting it.
        Otherwise, deletes the event by ID.

        Args:
            interval: Event to remove (must be an Event instance with an ID)

        Returns:
            List containing a single WriteResult
        """
        # Validate event
        event, error_result = _validate_event(interval)
        if error_result:
            return error_result

        assert event is not None  # For type checker

        # Check if this is a recurring event instance
        if event.recurring_event_id:
            # This is a recurring instance - add to exdates instead of deleting
            return self._remove_recurring_instance(event, event.recurring_event_id)
        else:
            # Standalone event - delete it
            self.calendar.delete_event(event.id, calendar_id=self.calendar_id)
            return [WriteResult(success=True, event=event, error=None)]

    def _remove_recurring_instance(
        self, instance: Event, master_event_id: str
    ) -> list[WriteResult]:
        """Remove a recurring event instance by adding it to exdates.

        Args:
            instance: The recurring instance to remove
            master_event_id: ID of the master recurring event

        Returns:
            List containing a single WriteResult
        """
        try:
            # Fetch the master event
            master_event = self.calendar.get_event(
                master_event_id, calendar_id=self.calendar_id
            )
        except Exception as e:
            return _error_result(
                ValueError(f"Failed to fetch master event {master_event_id}: {e}")
            )

        # Get current recurrence string
        if not master_event.recurrence:
            return _error_result(
                ValueError(f"Master event {master_event_id} has no recurrence")
            )

        rrule_str = master_event.recurrence[0]

        # Format instance start time as EXDATE
        if instance.start is None:
            return _error_result(
                ValueError("Instance must have a start time to add to exdates")
            )

        exdate_str = _format_exdate(instance.start)

        # Add EXDATE to RRULE if not already present
        _, existing_exdates = _parse_exdates_from_rrule(rrule_str)
        if exdate_str not in existing_exdates:
            new_rrule = _add_exdate_to_rrule(rrule_str, exdate_str)
            master_event.recurrence = [new_rrule]

            # Update the master event
            try:
                self.calendar.update_event(master_event, calendar_id=self.calendar_id)
            except Exception as e:
                return _error_result(ValueError(f"Failed to update master event: {e}"))

        return [WriteResult(success=True, event=instance, error=None)]

    @override
    def _add_many(
        self, intervals: Iterable[Interval], metadata: dict[str, Any]
    ) -> list[WriteResult]:
        """Add multiple events to Google Calendar using batch API.

        Uses Google's batch HTTP request API to create multiple events in a
        single network round-trip, significantly improving performance for
        bulk operations.

        Args:
            intervals: Iterable of Event intervals to write
            metadata: Metadata to apply to all events

        Returns:
            List of WriteResult objects (one per event)
        """
        # Convert to list so we can iterate twice
        events_list = list(intervals)
        if not events_list:
            return []

        # Prepare results storage (indexed by request_id)
        results: dict[str, WriteResult] = {}
        prepared_data: dict[str, _PreparedEvent] = {}  # request_id -> prepared event

        def callback(
            request_id: str,
            response: Any,
            exception: Exception | None,
        ) -> None:
            """Handle batch response for each event."""
            prepared = prepared_data[request_id]
            if exception is not None:
                results[request_id] = WriteResult(
                    success=False, event=prepared.event, error=exception
                )
            else:
                result_event = _build_result_event(prepared, response.get("id", ""))
                results[request_id] = WriteResult(
                    success=True, event=result_event, error=None
                )

        # Build batch request
        batch = self.calendar.service.new_batch_http_request(callback=callback)

        for idx, interval in enumerate(events_list):
            request_id = str(idx)

            # Prepare event for writing
            result = _prepare_event_for_add(
                interval,
                self.calendar_id,
                self.calendar_summary,
                self._calendar_timezone,
            )
            if isinstance(result, WriteResult):
                results[request_id] = result
                continue

            prepared = result
            prepared_data[request_id] = prepared

            # Build event body and add to batch
            body = _build_event_body(prepared)
            request = self.calendar.service.events().insert(
                calendarId=self.calendar_id, body=body
            )
            batch.add(request, request_id=request_id)

        # Execute batch (single HTTP request)
        try:
            batch.execute()
        except Exception as e:
            # If batch execution fails entirely, return error for all
            return [
                WriteResult(success=False, event=None, error=e) for _ in events_list
            ]

        # Return results in original order
        return [
            results.get(
                str(i),
                WriteResult(success=False, event=None, error=ValueError("Missing")),
            )
            for i in range(len(events_list))
        ]

    @override
    @_handle_write_errors
    def _remove_series(self, interval: Interval) -> list[WriteResult]:
        """Remove a recurring series from Google Calendar.

        Deletes the master recurring event, which removes all instances of the series.
        If the interval has a `recurring_event_id`, deletes that master event.
        Otherwise, deletes the event by its own ID (assuming it's a master event).

        Args:
            interval: Event representing the series to remove
                (can be a master event or an instance)

        Returns:
            List containing a single WriteResult
        """
        # Validate event
        event, error_result = _validate_event(interval)
        if error_result:
            return error_result

        assert event is not None  # For type checker

        # Determine which event ID to delete
        # If recurring_event_id is set, delete the master
        # Otherwise, delete the event itself (assuming it's a master)
        master_event_id = event.recurring_event_id or event.id

        # Delete the master event (this deletes all instances)
        self.calendar.delete_event(master_event_id, calendar_id=self.calendar_id)

        return [WriteResult(success=True, event=event, error=None)]


def calendars() -> list[Calendar]:
    """Return calendars accessible to the locally authenticated user.

    Returns:
        List of Calendar instances, one per accessible calendar
    """
    client = GoogleCalendar()
    cals = (
        Calendar(e.id, e.summary, client=client)
        for e in client.get_calendar_list()
        if e.id is not None and e.summary is not None
    )
    return sorted(cals, key=lambda c: c.calendar_id)
