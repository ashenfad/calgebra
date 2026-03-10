---
name: gcal
description: Google Calendar integration via REST API. Use when reading/writing Google Calendar events, listing calendars, creating meetings, managing recurring events, or working with attendees and reminders. Requires an OAuth access token.
modules:
  - calgebra.gcal
user-invocable: true
---

# Google Calendar (calgebra.gcal)

Direct REST API backend for Google Calendar. Works in Pyodide/browser (sync XMLHttpRequest in Web Workers) and standard Python (urllib fallback).

Requires the `calgebra` skill for core concepts (Timelines, operators, slicing).

## Setup

```python
from calgebra.gcal import calendars, Calendar, Event, Reminder, Attendee
from calgebra import at_tz

access_token = "ya29...."  # OAuth access token with calendar scope
at = at_tz("US/Pacific")

cals = calendars(access_token)
for c in cals:
    print(c.summary, c.id, c.timezone, c.primary)

# Get the primary calendar
primary = next(c for c in cals if c.primary)
```

## Calendar Fields

| Field | Type | Notes |
|-------|------|-------|
| `id` | `str` | Google Calendar ID |
| `summary` | `str` | Calendar display name |
| `primary` | `bool` | True if this is the user's primary calendar |
| `timezone` | `str \| None` | IANA timezone (e.g. `"America/Los_Angeles"`) |

## Reading Events

```python
events = list(primary[at("2025-01-01"):at("2025-01-31")])

for e in events:
    print(e.summary, e.start, e.end, e.duration)
    print(e.location, e.status, e.attendees)
```

All calgebra operators work — union, intersection, difference, complement, filters:

```python
from calgebra import hours, union

team_busy = union(*cals)
long_meetings = primary & (hours >= 2)
free = business_hours - primary
```

## Event Fields

| Field | Type | Notes |
|-------|------|-------|
| `id` | `str` | Google Calendar event ID (auto-filled on add) |
| `summary` | `str` | Event title |
| `description` | `str \| None` | Event description |
| `location` | `str \| None` | Location string |
| `start`, `end` | `int` | Unix timestamps (UTC) |
| `is_all_day` | `bool \| None` | Auto-inferred on write if None |
| `recurring_event_id` | `str \| None` | Master event ID (None for standalone) |
| `status` | `str` | `"confirmed"`, `"tentative"`, `"cancelled"` |
| `visibility` | `str \| None` | `"default"`, `"public"`, `"private"`, `"confidential"` |
| `transparency` | `str \| None` | `"opaque"` (busy) or `"transparent"` (free) |
| `color_id` | `str \| None` | Google Calendar color palette ID |
| `html_link` | `str \| None` | URL to view in Google Calendar (read-only) |
| `hangout_link` | `str \| None` | Google Meet link (read-only) |
| `attendees` | `list[Attendee] \| None` | Event attendees |
| `reminders` | `list[Reminder] \| None` | None = calendar defaults |
| `creator` | `dict \| None` | `{"email": ..., "displayName": ...}` (read-only) |
| `organizer` | `dict \| None` | `{"email": ..., "displayName": ...}` (read-only) |
| `calendar_id` | `str` | Source calendar ID |
| `calendar_summary` | `str` | Source calendar name |

## Creating Events

```python
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

# Multiple events at once
events = [event1, event2, event3]
results = primary.add(events)
```

## Creating Recurring Events

```python
from calgebra import recurring, HOUR, MINUTE

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

# Remove single event (or single recurring instance via EXDATE)
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

## Attendee

```python
Attendee(
    email="alice@example.com",
    display_name="Alice",          # optional
    response_status="accepted",    # "needsAction", "declined", "tentative", "accepted"
    optional=False,                # optional attendance
)
```

## Reminder

```python
Reminder(method="popup", minutes=10)   # popup 10 min before
Reminder(method="email", minutes=30)   # email 30 min before
```

## Field Helpers

Pre-defined `Property` objects for filtering:

```python
from calgebra.gcal import summary, location, status, transparency, calendar_id

work_events = primary & (summary == "Work")
private = primary & (visibility == "private")
busy_only = primary & (transparency == "opaque")
```

## Authentication

This module requires a Google OAuth access token with `calendar` scope. How you obtain it depends on your environment:

- **Browser (Pyodide):** Google Identity Services JS library
- **Server/CLI:** Google OAuth2 flow via google-auth library
- **Testing:** Google OAuth Playground (developers.google.com/oauthplayground)
