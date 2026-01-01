"""iCalendar (RFC 5545) integration for calgebra.

This module provides tools to convert between .ics files and MemoryTimeline objects,
allowing you to load calendar files, manipulate them with calgebra's set operations,
and save them back.

Requires the `icalendar` library: `pip install calgebra[ical]`
"""

import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, cast

try:
    import icalendar
    from icalendar import Calendar, Event, vRecur
except ImportError:
    # We allow importing this module even if icalendar is missing,
    # but functions will raise ImportError when called.
    icalendar = None  # type: ignore

from calgebra.core import Timeline
from calgebra.interval import Interval
from calgebra.mutable.memory import MemoryTimeline
from calgebra.properties import Property, field
from calgebra.recurrence import RecurringPattern

# Field Helpers
summary: Property[Interval] = field("summary")
description: Property[Interval] = field("description")
uid: Property[Interval] = field("uid")
location: Property[Interval] = field("location")
dtstamp: Property[Interval] = field("dtstamp")
sequence: Property[Interval] = field("sequence")
recurrence_id: Property[Interval] = field("recurrence_id")
is_all_day: Property[Interval] = field("is_all_day")
calendar_name: Property[Interval] = field("calendar_name")
status: Property[Interval] = field("status")
transp: Property[Interval] = field("transp")
categories: Property[Interval] = field("categories")

# Constants
_UTC = timezone.utc

_ICAL_FREQ_MAP = {
    "DAILY": "daily",
    "WEEKLY": "weekly",
    "MONTHLY": "monthly",
    "YEARLY": "yearly",
}


@dataclass(frozen=True, kw_only=True)
class ICalEvent(Interval):
    """Event representing an iCalendar VEVENT.

    Attributes:
        summary: Event summary (title)
        description: Event description
        uid: Unique Identifier (UID)
        location: Event location
        dtstamp: Timestamp of creation/modification
        sequence: Revision sequence number
        recurrence_id: ID for specific instances of a recurring event
        is_all_day: True if event is all-day (derived from DTSTART/DTEND type)
        calendar_name: Name of the source calendar (from X-WR-CALNAME)
        status: Event status (TENTATIVE, CONFIRMED, CANCELLED)
        transp: Time transparency (OPAQUE = busy, TRANSPARENT = free)
        categories: Tuple of category tags
    """

    summary: str | None = None
    description: str | None = None
    uid: str | None = None
    location: str | None = None
    dtstamp: datetime | None = None
    sequence: int = 0
    recurrence_id: datetime | None = None
    is_all_day: bool = False
    calendar_name: str | None = None
    status: Literal["TENTATIVE", "CONFIRMED", "CANCELLED"] | None = None
    transp: Literal["OPAQUE", "TRANSPARENT"] = "OPAQUE"
    categories: tuple[str, ...] = ()

    def __str__(self) -> str:
        base = super().__str__()
        title = f" '{self.summary}'" if self.summary else ""
        return base.replace("Interval(", f"ICalEvent{title}(", 1)


def _ensure_icalendar_installed() -> None:
    if icalendar is None:
        raise ImportError(
            "The 'icalendar' library is required for iCal integration.\n"
            "Install it via: pip install calgebra[ical]"
        )


def _dt_to_timestamp(dt: datetime | date) -> int:
    """Convert datetime/date to Unix timestamp."""
    if isinstance(dt, datetime):
        return int(dt.timestamp())
    # Date object: treat as midnight UTC for timestamp purposes (simplified)
    # Ideally we use the timezone context, but for Intervals we need an int.
    # We'll refine this if ensuring faithful round-tripping of all-day events
    # requires it.
    dt_full = datetime.combine(dt, datetime.min.time(), tzinfo=timezone.utc)
    return int(dt_full.timestamp())


def _parse_vevent(
    component: Event, tz_provider: Any = None, calendar_name: str | None = None
) -> Interval | RecurringPattern[ICalEvent]:
    """Parse a VEVENT component into an Interval or RecurringPattern."""
    # Extract basic properties
    summary = str(component.get("SUMMARY", ""))
    description = str(component.get("DESCRIPTION", ""))
    uid = str(component.get("UID", ""))
    location = str(component.get("LOCATION", ""))

    dtstamp_prop = component.get("DTSTAMP")
    dtstamp = dtstamp_prop.dt if dtstamp_prop else None

    sequence = int(component.get("SEQUENCE", 0))

    # Status and transparency
    status = str(component.get("STATUS", "")) or None
    transp = str(component.get("TRANSP", "OPAQUE")) or "OPAQUE"

    # Categories (can be a comma-separated list)
    categories_prop = component.get("CATEGORIES")
    if categories_prop:
        # categories_prop.cats is a list of category strings
        if hasattr(categories_prop, "cats"):
            categories = tuple(categories_prop.cats)
        else:
            categories = tuple(str(categories_prop).split(","))
    else:
        categories = ()

    # Times
    dtstart_prop = component.get("DTSTART")
    dtend_prop = component.get("DTEND")
    duration_prop = component.get("DURATION")

    if not dtstart_prop:
        raise ValueError("VEVENT missing DTSTART")

    start_dt = dtstart_prop.dt
    is_all_day = not isinstance(start_dt, datetime)  # date vs datetime

    # Resolve end time
    if dtend_prop:
        end_dt = dtend_prop.dt
    elif duration_prop:
        end_dt = start_dt + duration_prop.dt
    else:
        # Default duration: 1 day for all-day, 0 for instant? RFC says:
        # "DTEND" property is missing... duration is 1 day (for date value)
        # or 0 seconds (for date-time value)
        if is_all_day:
            end_dt = start_dt + timedelta(days=1)
        else:
            end_dt = start_dt
            # Note: 0-duration intervals are allowed but might generally be points.

    # Convert to timestamps
    start_ts = _dt_to_timestamp(start_dt)
    end_ts = _dt_to_timestamp(end_dt)

    # Calculate duration
    duration_seconds = end_ts - start_ts

    # Extract metadata dict
    metadata = {
        "summary": summary,
        "description": description,
        "uid": uid,
        "location": location,
        "dtstamp": dtstamp,
        "sequence": sequence,
        "is_all_day": is_all_day,
        "calendar_name": calendar_name,
        "status": status,
        "transp": transp,
        "categories": categories,
    }

    # Common event factory
    def create_event(**overrides: Any) -> ICalEvent:
        return ICalEvent(start=start_ts, end=end_ts, **{**metadata, **overrides})

    # Check for RRULE
    rrule_prop = component.get("RRULE")
    if not rrule_prop:
        # Static Event
        return create_event()

    # It's a recurring pattern
    # rrule_prop is a vRecur object, which behaves like a dict

    # vRecur keys: FREQ, INTERVAL, BYDAY, etc.
    freq_str = rrule_prop.get("FREQ", ["DAILY"])[0]  # Usually a list with 1 item
    freq = _ICAL_FREQ_MAP.get(freq_str.upper())
    if not freq:
        raise ValueError(f"Unsupported frequency: {freq_str}")

    interval = int(rrule_prop.get("INTERVAL", [1])[0])

    # RecurringPattern accepts raw strings/lists for these and parses/sanitizes them
    byday = rrule_prop.get("BYDAY")
    if byday and isinstance(byday, list):
        # Convert vWeekday/list to strings
        byday = [str(d) for d in byday]
    elif byday:
        byday = [str(byday)]

    day_of_month = rrule_prop.get("BYMONTHDAY")
    month = rrule_prop.get("BYMONTH")

    # Advanced RRULE parts
    bysetpos = rrule_prop.get("BYSETPOS")
    byweekno = rrule_prop.get("BYWEEKNO")
    byyearday = rrule_prop.get("BYYEARDAY")
    byhour = rrule_prop.get("BYHOUR")
    byminute = rrule_prop.get("BYMINUTE")
    bysecond = rrule_prop.get("BYSECOND")
    wkst = rrule_prop.get("WKST")

    # Normalize WKST to string if present (vRecur might return vWeekday)
    if wkst:
        if isinstance(wkst, list):
            wkst = str(wkst[0])
        else:
            wkst = str(wkst)

    # Start/TZ
    # We use the start_ts.
    # If start_dt has tzinfo, we convert to IANA string.
    tz = None
    if isinstance(start_dt, datetime) and start_dt.tzinfo:
        try:
            tz = str(start_dt.tzinfo)
        except Exception:
            pass

    # EXDATEs (exceptions)
    exdates = []
    if "EXDATE" in component:
        # EXDATE can appear multiple times or contain multiple values
        # decoded() handles the parsing into datetime/date objects
        exdate_props = component.decoded("EXDATE")

        # Ensure list
        if not isinstance(exdate_props, list):
            exdate_props = [exdate_props]

        for ed in exdate_props:
            if isinstance(ed, (date, datetime)):
                # Note: This logic assumes exceptions are in the same timeframe
                # convention as start
                exdates.append(_dt_to_timestamp(ed))

    return RecurringPattern(
        freq=cast(Any, freq),
        interval=interval,
        day=byday,
        day_of_month=day_of_month,
        month=month,
        start=start_ts,  # Use timestamp to preserve anchor
        duration=duration_seconds,
        tz=tz,
        interval_class=ICalEvent,
        exdates=exdates,
        # Advanced parts
        bysetpos=bysetpos,
        byweekno=byweekno,
        byyearday=byyearday,
        byhour=byhour,
        byminute=byminute,
        bysecond=bysecond,
        wkst=wkst,
        **metadata,
    )


def _interval_to_vevent(item: Interval | RecurringPattern[Any]) -> Event:
    """Convert an Interval or RecurringPattern to an iCalendar VEVENT."""
    event = Event()

    is_all_day = False
    meta: dict[str, Any] = {}

    if isinstance(item, RecurringPattern):
        rp = cast(RecurringPattern[ICalEvent], item)
        meta = rp.metadata

        # Start
        anchor = rp.anchor_timestamp if rp.anchor_timestamp else rp.start_seconds
        dtstart = datetime.fromtimestamp(anchor, tz=rp.zone or timezone.utc)

        event.add("dtstart", dtstart)
        event.add("duration", timedelta(seconds=rp.duration_seconds))

        # RRULE
        rrule_str = rp.to_rrule_string()
        event.add("rrule", vRecur.from_ical(rrule_str))

        # EXDATEs
        if rp.exdates:
            for mts in rp.exdates:
                mdt = datetime.fromtimestamp(mts, tz=rp.zone or timezone.utc)
                event.add("exdate", mdt)

    else:
        # Static Interval (or ICalEvent)
        ivl = cast(Interval, item)
        meta = vars(ivl)

        if ivl.start is None:
            raise ValueError("Cannot serialize unbounded interval (start is None)")

        is_all_day = meta.get("is_all_day", False) or getattr(ivl, "is_all_day", False)

        dtstart = datetime.fromtimestamp(ivl.start, tz=timezone.utc)

        if is_all_day:
            event.add("dtstart", dtstart.date())
        else:
            event.add("dtstart", dtstart)

        if ivl.end is not None:
            dtend = datetime.fromtimestamp(ivl.end, tz=timezone.utc)
            if is_all_day:
                event.add("dtend", dtend.date())
            else:
                event.add("dtend", dtend)

    # Common metadata properties
    for key, prop in [
        ("summary", "summary"),
        ("description", "description"),
        ("uid", "uid"),
        ("location", "location"),
    ]:
        val = meta.get(key)
        if val:
            event.add(prop, val)

    return event


def file_to_timeline(path: str | Path) -> MemoryTimeline:
    """Load an iCalendar (.ics) file into a MemoryTimeline.

    Args:
        path: Path to the .ics file

    Returns:
        MemoryTimeline populated with events from the file.
        Recurring events are preserved as symbolic RecurringPattern objects.
    """
    _ensure_icalendar_installed()

    with open(path, "rb") as f:
        cal = Calendar.from_ical(f.read())

    # Extract calendar name from X-WR-CALNAME property
    calendar_name = str(cal.get("X-WR-CALNAME", "")) or None

    timeline = MemoryTimeline()

    for component in cal.walk("VEVENT"):
        try:
            item = _parse_vevent(component, calendar_name=calendar_name)
            timeline.add(item)
        except Exception as e:
            # We might want to log this or optionally fail
            print(f"Warning: Failed to parse VEVENT: {e}", file=sys.stderr)
            continue

    return timeline


def timeline_to_file(timeline: Timeline[Any], path: str | Path) -> None:
    """Save a timeline to an iCalendar (.ics) file.

    Optimized for MemoryTimeline to preserve symbolic recurrence rules.

    Args:
        timeline: The source timeline (ideally MemoryTimeline)
        path: Output file path
    """
    _ensure_icalendar_installed()

    cal = Calendar()
    cal.add("prodid", "-//calgebra//mxm.dk//")
    cal.add("version", "2.0")

    items: list[Interval | RecurringPattern[Any]] = []

    if isinstance(timeline, MemoryTimeline):
        for _, pattern in timeline._recurring_patterns:
            items.append(pattern)
        for interval in timeline._static_intervals:
            items.append(interval)
    else:
        raise NotImplementedError(
            "timeline_to_file currently only supports MemoryTimeline."
        )

    for item in items:
        try:
            event = _interval_to_vevent(item)
            cal.add_component(event)
        except ValueError:
            # Skip invalid items (e.g. unbounded)
            continue

    with open(path, "wb") as f:
        f.write(cal.to_ical())
