# Google Calendar Integration (Direct REST API)

`calgebra` provides full read/write support for Google Calendar through the `calgebra.gcal` module using direct REST API calls. Unlike `calgebra.gcsa` (which uses the gcsa library with local credentials), this backend takes an OAuth access token directly and works in browser/Pyodide environments.

> **Alternative backend:** For desktop/CLI use with local OAuth credentials, see [`calgebra.gcsa`](GCSA.md).

## When to Use `gcal` vs `gcsa`

| | `calgebra.gcal` | `calgebra.gcsa` |
|---|---|---|
| **Auth** | OAuth access token | Local credential files |
| **Dependencies** | None (stdlib only) | `gcsa` library |
| **Browser/Pyodide** | Yes (sync XMLHttpRequest) | No |
| **Server/CLI** | Yes (urllib fallback) | Yes |
| **Batch writes** | Sequential | Google Batch API |

## Getting Started

```python
from calgebra.gcal import calendars, Calendar, Event, Reminder, Attendee
from calgebra import at_tz

access_token = "ya29...."  # OAuth access token with calendar scope
at = at_tz("US/Pacific")

# Get all accessible calendars
cals = calendars(access_token)
primary = cals[0]

print(f"Calendar: {primary.calendar_summary} (ID: {primary.calendar_id})")
```

## Reading Events

Google Calendar timelines work just like any other `calgebra` timeline — use slice notation to query events:

```python
from calgebra.gcal import calendars
from calgebra import at_tz

cals = calendars(access_token)
primary = cals[0]
at = at_tz("US/Pacific")

events = list(primary[at("2025-01-01"):at("2025-01-31")])

for e in events:
    print(f"{e.summary}: {e.format(tz='US/Pacific')}")
    if e.location:
        print(f"  Location: {e.location}")
    if e.attendees:
        for a in e.attendees:
            print(f"  {a.email} ({a.response_status})")
```

### Reverse Iteration

```python
from itertools import islice

# All events, newest first
recent_first = list(primary[at("2025-01-01"):at("2025-02-01"):-1])

# Last 5 events
last_5 = list(islice(primary[at("2024-01-01"):at("2025-01-01"):-1], 5))

# Most recent event
most_recent = next(primary[at("2024-01-01"):at("2025-01-01"):-1], None)
```

**Note:** Reverse iteration requires a finite `end` bound.

### Event Properties

| Field | Type | Notes |
|-------|------|-------|
| `id` | `str` | Google Calendar event ID |
| `summary` | `str` | Event title |
| `description` | `str \| None` | Event description |
| `location` | `str \| None` | Location string |
| `start`, `end` | `int` | Unix timestamps (UTC) |
| `is_all_day` | `bool` | True for all-day events |
| `recurring_event_id` | `str \| None` | Master event ID (None for standalone) |
| `status` | `str` | `"confirmed"`, `"tentative"`, `"cancelled"` |
| `visibility` | `str \| None` | `"default"`, `"public"`, `"private"`, `"confidential"` |
| `transparency` | `str \| None` | `"opaque"` (busy) or `"transparent"` (free) |
| `color_id` | `str \| None` | Google Calendar color palette ID |
| `html_link` | `str \| None` | URL to view in Google Calendar |
| `hangout_link` | `str \| None` | Google Meet link |
| `attendees` | `list[Attendee] \| None` | Event attendees |
| `reminders` | `list[Reminder] \| None` | None = calendar defaults |
| `creator` | `dict \| None` | `{"email": ..., "displayName": ...}` |
| `organizer` | `dict \| None` | `{"email": ..., "displayName": ...}` |
| `calendar_id` | `str` | Source calendar ID |
| `calendar_summary` | `str` | Source calendar name |

**Field Helpers:**
Pre-defined `Property` objects for filtering:
- `summary`, `description`, `location`
- `event_id` (maps to `id`), `calendar_id`, `calendar_summary`
- `is_all_day`, `recurring_event_id`
- `status`, `visibility`, `transparency`
- `color_id`, `html_link`, `hangout_link`
- `creator`, `organizer`

## Writing Single Events

```python
from calgebra.gcal import calendars, Event, Reminder, Attendee
from calgebra import at_tz

cals = calendars(access_token)
primary = cals[0]
at = at_tz("US/Pacific")

# Timed event with attendees and reminders
meeting = Event.from_datetimes(
    start=at(2025, 1, 15, 14, 0),
    end=at(2025, 1, 15, 15, 0),
    summary="Team Meeting",
    description="Weekly team sync",
    location="Room 42",
    reminders=[
        Reminder(method="email", minutes=30),
        Reminder(method="popup", minutes=15),
    ],
    attendees=[
        Attendee(email="alice@example.com"),
        Attendee(email="bob@example.com", optional=True),
    ],
)

results = primary.add(meeting)
if results[0].success:
    print(f"Event created: {results[0].event.id}")
else:
    print(f"Error: {results[0].error}")
```

### All-Day Events

All-day events are automatically inferred when start and end are at midnight boundaries:

```python
# Auto-inferred as all-day
vacation = Event.from_datetimes(
    start=at(2025, 7, 1),
    end=at(2025, 7, 10),
    summary="Vacation",
)

# Explicitly set
holiday = Event.from_datetimes(
    start=at(2025, 12, 25),
    end=at(2025, 12, 26),
    summary="Christmas",
    is_all_day=True,
)
```

### Multiple Events

```python
events = [event1, event2, event3]
results = primary.add(events)

for i, result in enumerate(results):
    if result.success:
        print(f"Event {i} created: {result.event.id}")
    else:
        print(f"Event {i} failed: {result.error}")
```

## Writing Recurring Events

```python
from calgebra.gcal import calendars, Reminder
from calgebra import recurring, at_tz, HOUR, MINUTE

cals = calendars(access_token)
primary = cals[0]
at = at_tz("US/Pacific")

# Weekly Monday standup
pattern = recurring(
    freq="weekly",
    day="monday",
    start=at(2025, 1, 6, 9, 30),
    duration=30*MINUTE,
)

results = primary.add(
    pattern,
    summary="Weekly Standup",
    description="Team sync",
    reminders=[Reminder(method="popup", minutes=5)],
)

# Bi-weekly Friday retro
biweekly = recurring(
    freq="weekly",
    interval=2,
    day="friday",
    start=at(2025, 1, 3, 15, 0),
    duration=HOUR,
)
primary.add(biweekly, summary="Retro")

# First Monday of every month
monthly = recurring(
    freq="monthly",
    week=1,
    day="monday",
    start=at(2025, 1, 6, 10, 0),
    duration=HOUR,
)
primary.add(monthly, summary="Monthly Review")
```

## Removing Events

### Remove Single Event

```python
events = list(primary[at("2025-01-15"):at("2025-01-16")])
if events:
    results = primary.remove(events[0])
```

### Remove Recurring Instance

Removing a recurring instance adds an EXDATE to the master event (the series continues without that occurrence):

```python
events = list(primary[at("2025-01-20"):at("2025-01-21")])
instance = events[0]

if instance.recurring_event_id:
    results = primary.remove(instance)  # removes just this occurrence
```

### Remove Entire Recurring Series

```python
results = primary.remove_series(instance)  # deletes all occurrences
```

## Common Patterns

### Finding Free Time

```python
from calgebra.gcal import calendars
from calgebra import day_of_week, time_of_day, hours, at_tz, HOUR

cals = calendars(access_token)
primary = cals[0]
at = at_tz("US/Pacific")

weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"])
business_hours = weekdays & time_of_day(start=9*HOUR, duration=8*HOUR, tz="US/Pacific")

free = business_hours - primary
long_slots = free & (hours >= 2)
slots = list(long_slots[at("2025-01-01"):at("2025-02-01")])
```

### Combining Multiple Calendars

```python
from calgebra import union

all_busy = union(*cals)
free = business_hours - all_busy
```

### Filtering by Event Properties

```python
from calgebra.gcal import summary, location, transparency

work_meetings = primary & (summary == "Work")
busy_only = primary & (transparency == "opaque")
```

## Authentication

This module requires an OAuth access token with the `https://www.googleapis.com/auth/calendar` scope.

**Browser (Pyodide):** Use Google Identity Services JS library to obtain a token client-side.

**Server/CLI:** Use google-auth or similar OAuth2 libraries.

**Testing:** Use [Google's OAuth Playground](https://developers.google.com/oauthplayground/) — select Calendar API v3 scopes, authorize, and copy the access token.

## Error Handling

All write operations return `list[WriteResult]`:

```python
results = primary.add(event)
result = results[0]

if result.success:
    print(f"Success! Event ID: {result.event.id}")
else:
    print(f"Error: {result.error}")
```

API errors (authentication failures, rate limits, etc.) are wrapped in `RuntimeError` with the Google Calendar API error message.

## See Also

- [API Reference](API.md) - Complete API documentation
- [Tutorial](TUTORIAL.md) - Learn calgebra's core concepts
- [Google Calendar (gcsa)](GCSA.md) - Alternative backend using local credentials
