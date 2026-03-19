---
name: gcal
description: Google Calendar integration via REST API. Use when reading/writing Google Calendar events, listing calendars, creating meetings, managing recurring events, or working with attendees and reminders.
modules:
  - calgebra.gcal
user-invocable: true
---

# Google Calendar (calgebra.gcal)

Direct REST API backend for Google Calendar. Works in Pyodide/browser
via sync XMLHttpRequest.

Requires the `calgebra` skill for core concepts (Timelines, operators, slicing).

## Setup

Always start with this pattern:

```python
from calgebra.gcal import calendars, Calendar, Event, Reminder, Attendee
from calgebra.gcal import transparency  # for busy/free filtering
from calgebra import at_tz, to_dataframe

access_token = "ya29...."  # OAuth access token with calendar scope
tz = "US/Pacific"
at = at_tz(tz)

cals = calendars(access_token)
primary = next(c for c in cals if c.primary)
```

> **`transparency`** is imported from `calgebra.gcal`, NOT from `calgebra`.

## Reading Events

```python
# List events
events = list(primary[at("2025-01-01"):at("2025-01-31")])
df = to_dataframe(events, tz=tz)

# Busy events only (excludes transparent/free events)
busy = primary & (transparency == "opaque")
busy_events = list(busy[at("2025-01-01"):at("2025-01-31")])

# Free time during business hours
from calgebra import day_of_week, time_of_day, HOUR

weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"], tz=tz)
work_hours = time_of_day(start=9*HOUR, duration=8*HOUR, tz=tz)
business_hours = weekdays & work_hours

free = business_hours - busy
slots = list(free[at("2025-01-20"):at("2025-01-24")])
```

All calgebra operators work — union, intersection, difference, complement, filters:

```python
from calgebra import hours, union

team_busy = union(*cals)
long_meetings = primary & (hours >= 2)
```

## Calendar Fields

| Field | Type | Notes |
|-------|------|-------|
| `id` | `str` | Google Calendar ID |
| `summary` | `str` | Calendar display name |
| `primary` | `bool` | True if this is the user's primary calendar |
| `timezone` | `str \| None` | IANA timezone |

## Event Fields

| Field | Type | Notes |
|-------|------|-------|
| `id` | `str` | Google event ID (auto-filled on add) |
| `summary` | `str` | Event title |
| `description` | `str \| None` | Event description |
| `location` | `str \| None` | Location string |
| `start`, `end` | `int` | Unix timestamps (UTC) |
| `is_all_day` | `bool \| None` | Auto-inferred on write if None |
| `recurring_event_id` | `str \| None` | Master event ID |
| `status` | `str` | `"confirmed"`, `"tentative"`, `"cancelled"` |
| `transparency` | `str` | `"opaque"` (busy) or `"transparent"` (free) |
| `attendees` | `list[Attendee] \| None` | Event attendees |
| `reminders` | `list[Reminder] \| None` | None = calendar defaults |
| `html_link` | `str \| None` | URL to view in Google Calendar |
| `hangout_link` | `str \| None` | Google Meet link |

> **Transparency** is normalized on parse: events missing the field default
> to `"opaque"` (busy).

## Creating Events

```python
token = access_token
tz = "US/Pacific"
at = at_tz(tz)

cals = calendars(token)
primary = next(c for c in cals if c.primary)

# Timed event
meeting = Event.from_datetimes(
    start=at(2025, 1, 15, 14, 0),
    end=at(2025, 1, 15, 15, 0),
    summary="Team Meeting",
    description="Weekly sync",
    location="Room 42",
    reminders=[Reminder(method="popup", minutes=10)],
    attendees=[
        Attendee(email="alice@example.com"),
        Attendee(email="bob@example.com", optional=True),
    ],
)
results = primary.add(meeting)

# All-day event (auto-inferred from midnight-to-midnight)
vacation = Event.from_datetimes(
    start=at(2025, 7, 1),
    end=at(2025, 7, 10),
    summary="Vacation",
)
primary.add(vacation)

# Multiple events at once (single API call — preferred)
results = primary.add([event1, event2, event3])
```

## Creating Recurring Events

```python
from calgebra import recurring, HOUR, MINUTE

at = at_tz("US/Pacific")

# Weekly Monday standup
pattern = recurring(
    freq="weekly", day="monday",
    start=at(2025, 1, 6, 9, 30),
    duration=30*MINUTE,
)
primary.add(pattern, summary="Standup", reminders=[Reminder(method="popup", minutes=5)])

# Bi-weekly Friday retro
pattern = recurring(
    freq="weekly", interval=2, day="friday",
    start=at(2025, 1, 3, 15, 0),
    duration=HOUR,
)
primary.add(pattern, summary="Retro")
```

## Removing Events

```python
events = list(primary[at("2025-01-15"):at("2025-01-16")])
event = events[0]

# Remove single event (or single recurring instance)
results = primary.remove(event)

# Remove entire recurring series
if event.recurring_event_id:
    results = primary.remove_series(event)
```

## WriteResult

All write operations return `list[WriteResult]`:

```python
results = primary.add(event)
if results[0].success:
    print(f"Created: {results[0].event.id}")
else:
    print(f"Error: {results[0].error}")
```

## Attendee & Reminder

```python
Attendee(email="alice@example.com", display_name="Alice", optional=False)
Reminder(method="popup", minutes=10)
Reminder(method="email", minutes=30)
```

## Field Helpers for Filtering

```python
from calgebra.gcal import summary, location, status, transparency, calendar_id

work_events = primary & (summary == "Work")
busy_only = primary & (transparency == "opaque")
```
