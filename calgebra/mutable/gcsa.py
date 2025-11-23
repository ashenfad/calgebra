"""Google Calendar integration for mutable timelines.

This module provides Calendar, a MutableTimeline implementation
that reads from and writes to Google Calendar via the gcsa library.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from functools import wraps
from time import time as current_time
from typing import Any, Callable, Literal, TypeVar
from zoneinfo import ZoneInfo

from gcsa.event import Event as GcsaEvent
from gcsa.google_calendar import GoogleCalendar
from gcsa.reminders import EmailReminder, PopupReminder
from gcsa.reminders import Reminder as GcsaReminder
from typing_extensions import override

from calgebra.interval import Interval
from calgebra.mutable import MutableTimeline, WriteResult
from calgebra.recurrence import RecurringPattern
from calgebra.util import DAY

# Type variable for write operation methods
_F = TypeVar("_F", bound=Callable[..., list[WriteResult]])

# Constants
_UTC_TIMEZONE = "UTC"
_EXDATE_FORMAT = "%Y%m%dT%H%M%SZ"


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

    id: str
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


def _get_calendar_timezone(
    calendar: GoogleCalendar, calendar_id: str
) -> ZoneInfo | None:
    """Get the calendar's default timezone.

    Currently returns None (UTC) but can be extended to fetch from calendar settings.

    Args:
        calendar: GoogleCalendar client instance
        calendar_id: Calendar ID

    Returns:
        Calendar's timezone, or None to use UTC
    """
    # TODO: Fetch actual calendar timezone from Google Calendar API
    # For now, return None which means UTC
    return None


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


class Calendar(MutableTimeline[Event]):
    """Timeline backed by the Google Calendar API using local credentials.

    Events are converted to UTC timestamps. Each event's own timezone (if specified)
    is used when interpreting all-day events or naive datetimes from the API.

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
            client if client is not None else GoogleCalendar(self.calendar_id)
        )

    @override
    def __str__(self) -> str:
        return (
            f"Calendar(id='{self.calendar_id}', " f"summary='{self.calendar_summary}')"
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
            event_zone = ZoneInfo(e.timezone) if e.timezone else ZoneInfo(_UTC_TIMEZONE)

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
        # Validate event (ID not required for add operations)
        event, error_result = _validate_event(interval, require_id=False)
        if error_result:
            return error_result

        assert event is not None  # For type checker

        if event.start is None or event.end is None:
            return _error_result(ValueError("Event must have finite start and end"))

        # Always use this calendar's metadata
        # (ignore any calendar_id/calendar_summary in event)
        # This allows moving events between calendars
        event = replace(
            event,
            calendar_id=self.calendar_id,
            calendar_summary=self.calendar_summary,
        )

        # Determine if event is all-day
        is_all_day = event.is_all_day
        if is_all_day is None:
            # Auto-infer: need calendar's default timezone
            calendar_tz = _get_calendar_timezone(self.calendar, self.calendar_id)
            is_all_day = _infer_is_all_day(event.start, event.end, calendar_tz)

        # Convert timestamps to datetime/date objects
        start_dt, end_dt = _convert_timestamps_to_datetime(
            event.start, event.end, is_all_day
        )

        # Convert reminders
        gcsa_reminders = _convert_reminders_to_gcsa(event.reminders)

        # Create gcsa Event object
        gcsa_event = GcsaEvent(
            summary=event.summary,
            start=start_dt,
            end=end_dt,
            timezone=_UTC_TIMEZONE if not is_all_day else None,
            description=event.description,
            reminders=gcsa_reminders,
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

        # Convert created event back to our Event format
        result_event = Event(
            id=created_event.id,
            calendar_id=self.calendar_id,
            calendar_summary=self.calendar_summary,
            summary=event.summary,
            description=event.description,
            recurring_event_id=None,  # Single events don't have recurring_event_id
            is_all_day=is_all_day,
            reminders=event.reminders,
            start=event.start,
            end=event.end,
        )

        return [WriteResult(success=True, event=result_event, error=None)]

    @override
    @_handle_write_errors
    def _add_recurring(
        self, pattern: RecurringPattern[Event], metadata: dict[str, Any]
    ) -> list[WriteResult]:
        """Add a recurring pattern to Google Calendar.

        Converts a RecurringPattern to a Google Calendar recurring event
        with RRULE and handles exdates.

        Args:
            pattern: RecurringPattern to add (must use Event as interval_class)
            metadata: Additional metadata to merge with pattern metadata

        Returns:
            List containing a single WriteResult with the created recurring event
        """
        if pattern.interval_class is not Event:
            return _error_result(
                TypeError(
                    f"Expected RecurringPattern[Event], "
                    f"got RecurringPattern[{pattern.interval_class.__name__}]"
                )
            )

        # Always use this calendar's metadata
        # (ignore any calendar_id/calendar_summary in metadata)
        # This allows moving recurring patterns between calendars
        metadata["calendar_id"] = self.calendar_id
        metadata["calendar_summary"] = self.calendar_summary

        # Merge metadata
        merged_metadata = {**pattern.metadata, **metadata}

        # Determine if all-day (duration == DAY means all-day)
        is_all_day = pattern.duration_seconds == DAY

        # Get RRULE string
        rrule_str = pattern.to_rrule_string()

        # Add EXDATE if there are exdates
        if pattern.exdates:
            # Convert exdates (timestamps) to EXDATE format
            for exdate_ts in sorted(pattern.exdates):
                exdate_str = _format_exdate(exdate_ts)
                rrule_str = _add_exdate_to_rrule(rrule_str, exdate_str)

        # Determine series start date/time
        # Use current time as DTSTART (or from metadata if provided)
        # For Google Calendar, we need a concrete start date
        series_start_ts = merged_metadata.get("start", int(current_time()))
        series_end_ts = series_start_ts + pattern.duration_seconds

        # Convert start timestamp to datetime/date
        series_start_dt, series_end_dt = _convert_timestamps_to_datetime(
            series_start_ts, series_end_ts, is_all_day
        )

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
        gcsa_event = GcsaEvent(
            summary=summary,
            start=series_start_dt,
            end=series_end_dt,
            timezone=_UTC_TIMEZONE if not is_all_day else None,
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
    return [
        Calendar(e.id, e.summary, client=client)
        for e in client.get_calendar_list()
        if e.id is not None and e.summary is not None
    ]
