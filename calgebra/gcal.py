"""Google Calendar integration via direct REST API calls.

This module provides Calendar, a MutableTimeline implementation
that reads from and writes to Google Calendar using direct HTTP calls
to the Google Calendar API v3. Designed to work in Pyodide/browser
environments via synchronous XMLHttpRequest (available in Web Workers).

For the gcsa-based backend (using local credentials), see calgebra.gcsa.

Example:
    >>> from calgebra.gcal import calendars, Event, Calendar
    >>> from calgebra import at_tz
    >>>
    >>> access_token = "ya29...."  # From Google OAuth
    >>> cals = calendars(access_token)
    >>> primary = cals[0]
    >>>
    >>> at = at_tz("US/Pacific")
    >>> events = list(primary[at("2025-01-01"):at("2025-01-31")])
    >>>
    >>> new_event = Event.from_datetimes(
    ...     start=at(2025, 1, 15, 14, 0),
    ...     end=at(2025, 1, 15, 15, 0),
    ...     summary="Team Meeting",
    ... )
    >>> primary.add(new_event)
"""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from functools import wraps
from typing import Any, Callable, Literal, TypeVar
from zoneinfo import ZoneInfo

from typing_extensions import override

from calgebra.interval import Interval, IvlOut
from calgebra.mutable import MutableTimeline, WriteResult
from calgebra.properties import Property, field
from calgebra.recurrence import RecurringPattern
from calgebra.util import DAY

# Field Helpers
summary: Property[Interval] = field("summary")
description: Property[Interval] = field("description")
event_id: Property[Interval] = field("id")
calendar_id: Property[Interval] = field("calendar_id")
calendar_summary: Property[Interval] = field("calendar_summary")
is_all_day: Property[Interval] = field("is_all_day")
recurring_event_id: Property[Interval] = field("recurring_event_id")
location: Property[Interval] = field("location")
status: Property[Interval] = field("status")
visibility: Property[Interval] = field("visibility")
transparency: Property[Interval] = field("transparency")
color_id: Property[Interval] = field("color_id")
html_link: Property[Interval] = field("html_link")
hangout_link: Property[Interval] = field("hangout_link")
creator: Property[Interval] = field("creator")
organizer: Property[Interval] = field("organizer")

# Type variable for write operation methods
_F = TypeVar("_F", bound=Callable[..., list[WriteResult]])

# Constants
_UTC_TIMEZONE = "UTC"
_EXDATE_FORMAT = "%Y%m%dT%H%M%SZ"
_API_BASE = "https://www.googleapis.com/calendar/v3"

__all__ = [
    "Event",
    "Calendar",
    "Attendee",
    "Reminder",
    "WriteResult",
    "calendars",
]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Attendee:
    """Google Calendar event attendee.

    Attributes:
        email: Attendee's email address.
        display_name: Attendee's display name (optional).
        response_status: RSVP status — "needsAction", "declined",
            "tentative", or "accepted".
        optional: Whether attendance is optional.
        organizer: Whether this attendee is the organizer.
        self_: Whether this attendee represents the authenticated user.
    """

    email: str
    display_name: str | None = None
    response_status: str = "needsAction"
    optional: bool = False
    organizer: bool = False
    self_: bool = False


@dataclass(frozen=True)
class Reminder:
    """Google Calendar event reminder/notification.

    Attributes:
        method: Reminder method — "email" or "popup".
        minutes: Minutes before event start to trigger reminder.
    """

    method: Literal["email", "popup"]
    minutes: int


@dataclass(frozen=True, kw_only=True)
class Event(Interval):
    """Google Calendar event represented as an interval.

    Attributes:
        id: Google Calendar event ID (auto-filled by Calendar on add).
        calendar_id: ID of the calendar containing this event
            (ignored on write — always uses target calendar's ID).
        calendar_summary: Human-readable name of the calendar
            (ignored on write — always uses target calendar's summary).
        summary: Event title/summary.
        description: Event description (optional).
        location: Event location string (optional).
        recurring_event_id: ID of the master recurring event
            (None for standalone or master events).
        is_all_day: True if all-day event, False if timed event,
            None to auto-infer when writing.
        reminders: List of reminders (None = use calendar defaults).
        attendees: List of attendees (None = no attendees).
        status: Event status — "confirmed", "tentative", or "cancelled".
        visibility: Event visibility — "default", "public", "private",
            or "confidential".
        transparency: Whether event blocks time — "opaque" (busy) or
            "transparent" (free).
        color_id: Color ID string from Google Calendar's palette.
        html_link: URL to view event in Google Calendar (read-only).
        hangout_link: Google Meet / Hangout link (read-only).
        creator: Dict with "email" and optional "displayName" of creator
            (read-only).
        organizer: Dict with "email" and optional "displayName" of
            organizer (read-only).
    """

    id: str = ""
    calendar_id: str = ""
    calendar_summary: str = ""
    summary: str = ""
    description: str | None = None
    location: str | None = None
    recurring_event_id: str | None = None
    is_all_day: bool | None = None
    reminders: list[Reminder] | None = None
    attendees: list[Attendee] | None = None
    status: str = "confirmed"
    visibility: str | None = None
    transparency: str | None = None
    color_id: str | None = None
    html_link: str | None = None
    hangout_link: str | None = None
    creator: dict[str, str] | None = None
    organizer: dict[str, str] | None = None

    @override
    def __str__(self) -> str:
        start_str = str(self.start) if self.start is not None else "-∞"
        end_str = str(self.end) if self.end is not None else "+∞"
        if self.start is not None and self.end is not None:
            duration = self.end - self.start
            return f"Event('{self.summary}', {start_str}→{end_str}, {duration}s)"
        return f"Event('{self.summary}', {start_str}→{end_str}, unbounded)"


# ---------------------------------------------------------------------------
# HTTP transport — synchronous XMLHttpRequest (works in Pyodide Web Workers)
# ---------------------------------------------------------------------------


def _xhr_request(
    method: str,
    url: str,
    access_token: str,
    body: dict | None = None,
) -> dict | None:
    """Make a synchronous HTTP request to the Google Calendar API.

    Uses XMLHttpRequest when running in Pyodide (emscripten) and
    falls back to urllib for testing outside the browser.

    Returns parsed JSON response, or None for 204 No Content.
    Raises RuntimeError on HTTP errors.
    """
    import sys

    if sys.platform == "emscripten":
        from js import XMLHttpRequest  # type: ignore[import-untyped]

        xhr = XMLHttpRequest.new()
        xhr.open(method, url, False)  # synchronous
        xhr.setRequestHeader("Authorization", f"Bearer {access_token}")
        xhr.setRequestHeader("Content-Type", "application/json")
        if body is not None:
            xhr.send(json.dumps(body))
        else:
            xhr.send()
        if xhr.status >= 400:
            try:
                err = json.loads(xhr.responseText)
                msg = err.get("error", {}).get("message", xhr.responseText)
            except Exception:
                msg = f"HTTP {xhr.status}"
            raise RuntimeError(f"Google Calendar API error ({xhr.status}): {msg}")
        if xhr.status == 204:
            return None
        return json.loads(xhr.responseText)
    else:
        import urllib.request

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                if resp.status == 204:
                    return None
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode())
                msg = err.get("error", {}).get("message", str(err))
            except Exception:
                msg = f"HTTP {e.code}"
            raise RuntimeError(f"Google Calendar API error ({e.code}): {msg}") from e


def _paginated_get(
    url: str,
    access_token: str,
    params: dict[str, str],
) -> Iterable[dict]:
    """GET with automatic pagination, yielding items from each page."""
    sep = "&" if "?" in url else "?"
    while True:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        full_url = f"{url}{sep}{query}"
        data = _xhr_request("GET", full_url, access_token)
        if data is None:
            break
        for item in data.get("items", []):
            yield item
        next_token = data.get("nextPageToken")
        if not next_token:
            break
        params["pageToken"] = next_token


# ---------------------------------------------------------------------------
# Timestamp / datetime helpers (shared with gcsa.py)
# ---------------------------------------------------------------------------


def _timestamp_to_datetime(ts: int) -> datetime:
    """Convert a Unix timestamp to a UTC datetime."""
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _to_timestamp(dt: datetime | date, zone: ZoneInfo | None) -> int:
    """Convert a datetime or date to a Unix timestamp."""
    if not isinstance(dt, datetime):
        tz = zone if zone is not None else timezone.utc
        dt = datetime.combine(dt, time.min, tzinfo=tz)
    elif dt.tzinfo is None:
        tz = zone if zone is not None else timezone.utc
        dt = dt.replace(tzinfo=tz)
    return int(dt.astimezone(timezone.utc).replace(microsecond=0).timestamp())


def _infer_is_all_day(start_ts: int, end_ts: int, calendar_tz: ZoneInfo | None) -> bool:
    """Infer if an event should be all-day based on timestamps."""
    tz = calendar_tz if calendar_tz is not None else timezone.utc
    start_dt = datetime.fromtimestamp(start_ts, tz=tz)
    end_dt = datetime.fromtimestamp(end_ts, tz=tz)
    if start_dt.time() != time.min or end_dt.time() != time.min:
        return False
    duration = timedelta(seconds=end_ts - start_ts)
    days = duration.days
    remainder = duration - timedelta(days=days)
    return remainder <= timedelta(hours=1)


def _convert_timestamps_to_datetime(
    start_ts: int, end_ts: int, is_all_day: bool
) -> tuple[datetime | date, datetime | date]:
    """Convert UTC timestamps to datetime/date objects for Google Calendar."""
    if is_all_day:
        return _timestamp_to_datetime(start_ts).date(), _timestamp_to_datetime(
            end_ts
        ).date()
    return _timestamp_to_datetime(start_ts), _timestamp_to_datetime(end_ts)


def _format_exdate(timestamp: int) -> str:
    """Format a UTC timestamp as an RFC 5545 EXDATE string."""
    return _timestamp_to_datetime(timestamp).strftime(_EXDATE_FORMAT)


def _parse_exdates_from_rrule(rrule_str: str) -> tuple[str, list[str]]:
    """Parse EXDATE from an RRULE string."""
    exdate_match = re.search(r"EXDATE[:=]([^;]+)", rrule_str)
    if exdate_match:
        exdates = exdate_match.group(1).split(",")
        base_rrule = re.sub(r";EXDATE[:=][^;]+", "", rrule_str)
        return base_rrule, exdates
    return rrule_str, []


def _add_exdate_to_rrule(rrule_str: str, exdate_str: str) -> str:
    """Add an EXDATE to an RRULE string."""
    base_rrule, existing_exdates = _parse_exdates_from_rrule(rrule_str)
    if exdate_str not in existing_exdates:
        existing_exdates.append(exdate_str)
    exdate_part = "EXDATE:" + ",".join(existing_exdates)
    return f"{base_rrule};{exdate_part}"


# ---------------------------------------------------------------------------
# JSON ↔ Event conversion
# ---------------------------------------------------------------------------


def _parse_attendees(raw: list[dict] | None) -> list[Attendee] | None:
    """Parse attendees from API response."""
    if not raw:
        return None
    return [
        Attendee(
            email=a["email"],
            display_name=a.get("displayName"),
            response_status=a.get("responseStatus", "needsAction"),
            optional=a.get("optional", False),
            organizer=a.get("organizer", False),
            self_=a.get("self", False),
        )
        for a in raw
    ]


def _parse_reminders(raw: dict | None) -> list[Reminder] | None:
    """Parse reminders from API response.

    Returns None if using calendar defaults.
    """
    if not raw or raw.get("useDefault", True):
        return None
    overrides = raw.get("overrides", [])
    if not overrides:
        return None
    return [
        Reminder(method=r["method"], minutes=r["minutes"])
        for r in overrides
        if r.get("method") in ("email", "popup") and "minutes" in r
    ]


def _parse_event_datetime(
    dt_obj: dict, calendar_tz: ZoneInfo | None
) -> tuple[int, bool]:
    """Parse a Google Calendar start/end object to (timestamp, is_all_day).

    Args:
        dt_obj: Dict with either "dateTime" or "date" key.
        calendar_tz: Calendar timezone for interpreting all-day dates.

    Returns:
        Tuple of (unix_timestamp, is_all_day).
    """
    if "dateTime" in dt_obj:
        dt_str = dt_obj["dateTime"]
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            tz_str = dt_obj.get("timeZone")
            tz = ZoneInfo(tz_str) if tz_str else timezone.utc
            dt = dt.replace(tzinfo=tz)
        return int(dt.astimezone(timezone.utc).timestamp()), False
    elif "date" in dt_obj:
        d = date.fromisoformat(dt_obj["date"])
        tz = calendar_tz if calendar_tz is not None else timezone.utc
        dt = datetime.combine(d, time.min, tzinfo=tz)
        return int(dt.timestamp()), True
    raise ValueError(
        f"Event datetime object has neither 'dateTime' nor 'date': {dt_obj}"
    )


def _json_to_event(
    raw: dict,
    calendar_id: str,
    calendar_summary: str,
    calendar_tz: ZoneInfo | None,
) -> Event | None:
    """Convert a Google Calendar API event JSON to an Event.

    Returns None if the event is missing required fields.
    """
    event_id = raw.get("id")
    if not event_id:
        return None

    start_obj = raw.get("start")
    end_obj = raw.get("end")
    if not start_obj or not end_obj:
        return None

    start_ts, start_all_day = _parse_event_datetime(start_obj, calendar_tz)
    end_ts, end_all_day = _parse_event_datetime(end_obj, calendar_tz)
    is_all_day = start_all_day or end_all_day

    return Event(
        id=event_id,
        calendar_id=calendar_id,
        calendar_summary=calendar_summary,
        summary=raw.get("summary", ""),
        description=raw.get("description"),
        location=raw.get("location"),
        recurring_event_id=raw.get("recurringEventId"),
        is_all_day=is_all_day,
        reminders=_parse_reminders(raw.get("reminders")),
        attendees=_parse_attendees(raw.get("attendees")),
        status=raw.get("status", "confirmed"),
        visibility=raw.get("visibility"),
        transparency=raw.get("transparency"),
        color_id=raw.get("colorId"),
        html_link=raw.get("htmlLink"),
        hangout_link=raw.get("hangoutLink"),
        creator=raw.get("creator"),
        organizer=raw.get("organizer"),
        start=start_ts,
        end=end_ts,
    )


def _event_to_body(event: Event, is_all_day: bool) -> dict[str, Any]:
    """Convert an Event to a Google Calendar API request body for create/update."""
    body: dict[str, Any] = {}

    if event.summary:
        body["summary"] = event.summary
    if event.description:
        body["description"] = event.description
    if event.location:
        body["location"] = event.location
    if event.visibility:
        body["visibility"] = event.visibility
    if event.transparency:
        body["transparency"] = event.transparency
    if event.color_id:
        body["colorId"] = event.color_id
    if event.status and event.status != "confirmed":
        body["status"] = event.status

    # Start/end
    if event.start is not None and event.end is not None:
        if is_all_day:
            start_d = _timestamp_to_datetime(event.start).date()
            end_d = _timestamp_to_datetime(event.end).date()
            body["start"] = {"date": start_d.isoformat()}
            body["end"] = {"date": end_d.isoformat()}
        else:
            start_dt = _timestamp_to_datetime(event.start)
            end_dt = _timestamp_to_datetime(event.end)
            body["start"] = {
                "dateTime": start_dt.isoformat(),
                "timeZone": _UTC_TIMEZONE,
            }
            body["end"] = {"dateTime": end_dt.isoformat(), "timeZone": _UTC_TIMEZONE}

    # Reminders
    if event.reminders is not None:
        body["reminders"] = {
            "useDefault": False,
            "overrides": [
                {"method": r.method, "minutes": r.minutes} for r in event.reminders
            ],
        }

    # Attendees
    if event.attendees is not None:
        body["attendees"] = [
            {
                "email": a.email,
                **({"displayName": a.display_name} if a.display_name else {}),
                **({"optional": True} if a.optional else {}),
                "responseStatus": a.response_status,
            }
            for a in event.attendees
        ]

    return body


# ---------------------------------------------------------------------------
# Error handling helpers
# ---------------------------------------------------------------------------


def _error_result(error: Exception) -> list[WriteResult]:
    return [WriteResult(success=False, event=None, error=error)]


def _handle_write_errors(func: _F) -> _F:
    """Decorator to wrap write operations with error handling."""

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
    """Validate that an interval is an Event with required fields."""
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


# ---------------------------------------------------------------------------
# Calendar — MutableTimeline backed by Google Calendar REST API
# ---------------------------------------------------------------------------


class Calendar(MutableTimeline[Event]):
    """Timeline backed by the Google Calendar REST API using an OAuth access token.

    Events are converted to UTC timestamps. All-day events are interpreted
    using the calendar's timezone (fetched from Google Calendar API), while
    timed events use the event's own timezone (if specified) or UTC.

    This backend uses synchronous HTTP (XMLHttpRequest in Pyodide Web Workers,
    urllib outside the browser) so that ``fetch()`` returns a synchronous
    ``Iterable`` compatible with all calgebra operators.

    Supports full read/write operations including:
    - Creating single and recurring events
    - Removing events and recurring series
    - Handling all-day events, reminders, attendees, and more
    """

    def __init__(
        self,
        calendar_id: str,
        calendar_summary: str,
        access_token: str,
    ) -> None:
        self.calendar_id: str = calendar_id
        self.calendar_summary: str = calendar_summary
        self._access_token: str = access_token
        self.__calendar_timezone: ZoneInfo | None = None
        self.__calendar_timezone_fetched: bool = False

    @property
    def _calendar_timezone(self) -> ZoneInfo | None:
        """Get calendar timezone, fetching from API on first access."""
        if not self.__calendar_timezone_fetched:
            self.__calendar_timezone_fetched = True
            try:
                url = f"{_API_BASE}/calendars/{self.calendar_id}"
                data = _xhr_request("GET", url, self._access_token)
                if data:
                    tz_str = data.get("timeZone")
                    if tz_str:
                        self.__calendar_timezone = ZoneInfo(tz_str)
            except Exception:
                pass
        return self.__calendar_timezone

    @override
    def __str__(self) -> str:
        return f"Calendar(id='{self.calendar_id}', summary='{self.calendar_summary}')"

    @override
    def fetch(
        self, start: int | None, end: int | None, *, reverse: bool = False
    ) -> Iterable[Event]:
        if reverse:
            return self._fetch_reverse(start, end)
        return self._fetch_forward(start, end)

    def _fetch_forward(self, start: int | None, end: int | None) -> Iterable[Event]:
        """Forward iteration through calendar events with pagination."""
        url = f"{_API_BASE}/calendars/{self.calendar_id}/events"
        params: dict[str, str] = {
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        if start is not None:
            params["timeMin"] = _timestamp_to_datetime(start).isoformat()
        if end is not None:
            params["timeMax"] = _timestamp_to_datetime(end).isoformat()

        cal_tz = self._calendar_timezone

        for raw in _paginated_get(url, self._access_token, params):
            event = _json_to_event(raw, self.calendar_id, self.calendar_summary, cal_tz)
            if event is not None:
                yield event

    def _fetch_reverse(self, start: int | None, end: int | None) -> Iterable[Event]:
        """Reverse iteration using windowed pagination."""
        if end is None:
            raise ValueError(
                "Reverse iteration on Calendar requires finite end bound.\n"
                "Fix: Use explicit end when slicing: calendar[start:end:-1]\n"
                "Example: list(calendar[at('2024-01-01'):at('2025-01-01'):-1])"
            )
        if start is None:
            start = end - (365 * DAY)

        window_size = 30 * DAY
        current_end = end
        while current_end > start:
            window_start = max(start, current_end - window_size)
            window_events = list(self._fetch_forward(window_start, current_end))
            yield from reversed(window_events)
            current_end = window_start

    # -- Write operations ----------------------------------------------------

    @override
    @_handle_write_errors
    def _add_interval(
        self, interval: Interval, metadata: dict[str, Any]
    ) -> list[WriteResult]:
        validated, error = _validate_event(interval, require_id=False)
        if error:
            return error
        assert validated is not None

        if validated.start is None or validated.end is None:
            return _error_result(ValueError("Event must have finite start and end"))

        event = replace(
            validated,
            id="",
            calendar_id=self.calendar_id,
            calendar_summary=self.calendar_summary,
        )

        is_all_day = event.is_all_day
        if is_all_day is None:
            is_all_day = _infer_is_all_day(
                event.start, event.end, self._calendar_timezone
            )

        body = _event_to_body(replace(event, is_all_day=is_all_day), is_all_day)
        url = f"{_API_BASE}/calendars/{self.calendar_id}/events"
        result = _xhr_request("POST", url, self._access_token, body)

        created_id = result.get("id", "") if result else ""
        if not created_id:
            return _error_result(
                ValueError("Google Calendar did not return an event ID")
            )

        result_event = replace(
            event,
            id=created_id,
            is_all_day=is_all_day,
        )
        return [WriteResult(success=True, event=result_event, error=None)]

    @override
    @_handle_write_errors
    def _add_recurring(
        self, pattern: RecurringPattern[IvlOut], metadata: dict[str, Any]
    ) -> list[WriteResult]:
        metadata["calendar_id"] = self.calendar_id
        metadata["calendar_summary"] = self.calendar_summary
        merged = {**pattern.metadata, **metadata}

        is_all_day = pattern.duration_seconds == DAY
        rrule_str = f"RRULE:{pattern.to_rrule_string()}"

        if pattern.exdates:
            for exdate_ts in sorted(pattern.exdates):
                rrule_str = _add_exdate_to_rrule(rrule_str, _format_exdate(exdate_ts))

        # Determine series start
        if "start" in merged:
            series_start_ts = merged["start"]
        elif pattern.anchor_timestamp is not None:
            series_start_ts = pattern.anchor_timestamp
        else:
            now_in_tz = datetime.now(pattern.zone)
            today_midnight = now_in_tz.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            series_start_ts = int(
                (today_midnight + timedelta(seconds=pattern.start_seconds)).timestamp()
            )

        series_end_ts = series_start_ts + pattern.duration_seconds

        summary_str = merged.get("summary", "Recurring Event")
        description_str = merged.get("description")
        reminders_list = merged.get("reminders")
        validated_reminders = None
        if isinstance(reminders_list, list) and all(
            isinstance(r, Reminder) for r in reminders_list
        ):
            validated_reminders = reminders_list

        # Build body
        body: dict[str, Any] = {"summary": summary_str, "recurrence": [rrule_str]}
        if description_str:
            body["description"] = description_str

        if is_all_day:
            body["start"] = {
                "date": _timestamp_to_datetime(series_start_ts).date().isoformat()
            }
            body["end"] = {
                "date": _timestamp_to_datetime(series_end_ts).date().isoformat()
            }
        else:
            event_tz = str(pattern.zone)
            start_dt = datetime.fromtimestamp(series_start_ts, tz=pattern.zone)
            end_dt = datetime.fromtimestamp(series_end_ts, tz=pattern.zone)
            body["start"] = {"dateTime": start_dt.isoformat(), "timeZone": event_tz}
            body["end"] = {"dateTime": end_dt.isoformat(), "timeZone": event_tz}

        if validated_reminders:
            body["reminders"] = {
                "useDefault": False,
                "overrides": [
                    {"method": r.method, "minutes": r.minutes}
                    for r in validated_reminders
                ],
            }

        url = f"{_API_BASE}/calendars/{self.calendar_id}/events"
        result = _xhr_request("POST", url, self._access_token, body)

        created_id = result.get("id", "") if result else ""
        if not created_id:
            return _error_result(
                ValueError("Google Calendar did not return an event ID")
            )

        result_event = Event(
            id=created_id,
            calendar_id=self.calendar_id,
            calendar_summary=self.calendar_summary,
            summary=summary_str,
            description=description_str,
            recurring_event_id=None,
            is_all_day=is_all_day,
            reminders=validated_reminders,
            start=series_start_ts,
            end=series_end_ts,
        )
        return [WriteResult(success=True, event=result_event, error=None)]

    @override
    @_handle_write_errors
    def _remove_interval(self, interval: Interval) -> list[WriteResult]:
        event, error = _validate_event(interval)
        if error:
            return error
        assert event is not None

        if event.recurring_event_id:
            return self._remove_recurring_instance(event, event.recurring_event_id)

        url = f"{_API_BASE}/calendars/{self.calendar_id}/events/{event.id}"
        _xhr_request("DELETE", url, self._access_token)
        return [WriteResult(success=True, event=event, error=None)]

    def _remove_recurring_instance(
        self, instance: Event, master_event_id: str
    ) -> list[WriteResult]:
        """Remove a recurring instance by adding an EXDATE to the master."""
        try:
            url = f"{_API_BASE}/calendars/{self.calendar_id}/events/{master_event_id}"
            master_data = _xhr_request("GET", url, self._access_token)
        except Exception as e:
            return _error_result(
                ValueError(f"Failed to fetch master event {master_event_id}: {e}")
            )

        if not master_data:
            return _error_result(
                ValueError(f"Master event {master_event_id} not found")
            )

        recurrence = master_data.get("recurrence", [])
        if not recurrence:
            return _error_result(
                ValueError(f"Master event {master_event_id} has no recurrence")
            )

        rrule_str = recurrence[0]

        if instance.start is None:
            return _error_result(
                ValueError("Instance must have a start time to add to exdates")
            )

        exdate_str = _format_exdate(instance.start)
        _, existing_exdates = _parse_exdates_from_rrule(rrule_str)

        if exdate_str not in existing_exdates:
            new_rrule = _add_exdate_to_rrule(rrule_str, exdate_str)
            master_data["recurrence"] = [new_rrule]
            try:
                url = (
                    f"{_API_BASE}/calendars/{self.calendar_id}/events/{master_event_id}"
                )
                _xhr_request("PUT", url, self._access_token, master_data)
            except Exception as e:
                return _error_result(ValueError(f"Failed to update master event: {e}"))

        return [WriteResult(success=True, event=instance, error=None)]

    @override
    @_handle_write_errors
    def _remove_series(self, interval: Interval) -> list[WriteResult]:
        event, error = _validate_event(interval)
        if error:
            return error
        assert event is not None

        master_id = event.recurring_event_id or event.id
        url = f"{_API_BASE}/calendars/{self.calendar_id}/events/{master_id}"
        _xhr_request("DELETE", url, self._access_token)
        return [WriteResult(success=True, event=event, error=None)]


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def calendars(access_token: str) -> list[Calendar]:
    """Return calendars accessible to the authenticated user.

    Args:
        access_token: OAuth access token for Google Calendar API.

    Returns:
        List of Calendar instances, sorted by calendar ID.
    """
    url = f"{_API_BASE}/users/me/calendarList"
    result: list[Calendar] = []
    for item in _paginated_get(url, access_token, {}):
        cal_id = item.get("id")
        cal_summary = item.get("summary")
        if cal_id and cal_summary:
            result.append(Calendar(cal_id, cal_summary, access_token))
    return sorted(result, key=lambda c: c.calendar_id)
