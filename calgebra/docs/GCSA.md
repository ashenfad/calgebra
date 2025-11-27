# Google Calendar Integration

`calgebra` provides full read/write support for Google Calendar through the `calgebra.gcsa` module. This guide covers authentication, reading events, writing events (single and recurring), removing events, and common patterns.

## Installation

Install `calgebra` with Google Calendar support:

```bash
pip install calgebra[google-calendar]
```

This installs the `gcsa` library, which handles Google Calendar API authentication and communication.

## Authentication

`gcsa` uses Google's OAuth2 flow. On first use, it will open a browser window for authentication. Credentials are stored locally for subsequent use.

**Setup:**
1. Install `calgebra[google-calendar]`
2. Import and use `calendars()` - authentication happens automatically on first use
3. Grant calendar access permissions when prompted

**Note:** For production deployments, you may need to configure OAuth2 credentials explicitly. See the [gcsa documentation](https://github.com/getyourguide/gcsa) for advanced authentication options.

## Getting Started

```python
from calgebra.gcsa import calendars, Calendar, Event
from calgebra import at_tz

# Get all accessible calendars
cals = calendars()
primary = cals[0]  # Usually your primary calendar

# Check calendar info
print(f"Calendar: {primary.calendar_summary} (ID: {primary.calendar_id})")
```

## Reading Events

Google Calendar timelines work just like any other `calgebra` timeline - use slice notation to query events:

```python
from calgebra.gcsa import calendars
from calgebra import at_tz

cals = calendars()
primary = cals[0]

# Query events using date strings
at = at_tz("US/Pacific")
events = list(primary[at("2025-01-01"):at("2025-01-31")])

# Or use datetime objects
from datetime import datetime, timezone
start = datetime(2025, 1, 1, tzinfo=timezone.utc)
end = datetime(2025, 1, 31, tzinfo=timezone.utc)
events = list(primary[start:end])

# Or use timestamps
events = list(primary[1735689600:1738368000])
```

### Reverse Iteration

Get events in reverse chronological order using step `-1`:

```python
from itertools import islice
from calgebra.gcsa import calendars
from calgebra import at_tz

cals = calendars()
primary = cals[0]
at = at_tz("US/Pacific")

# All events, newest first
recent_first = list(primary[at("2025-01-01"):at("2025-02-01"):-1])

# Last 5 events (stops after 5)
last_5 = list(islice(primary[at("2024-01-01"):at("2025-01-01"):-1], 5))

# Most recent event
most_recent = next(primary[at("2024-01-01"):at("2025-01-01"):-1], None)
```

**Note:** Reverse iteration requires a finite `end` bound (defaults `start` to 1 year before). Forward iteration works without `start` (API defaults to "now"), but explicit bounds are recommended.

**Event Properties:**
- `id`: Google Calendar event ID
- `calendar_id`: Calendar containing this event
- `calendar_summary`: Human-readable calendar name
- `summary`: Event title
- `description`: Event description (optional)
- `start`, `end`: Unix timestamps (UTC)
- `recurring_event_id`: ID of master recurring event (None for standalone/master events)
- `is_all_day`: True for all-day events, False for timed events
- `reminders`: List of `Reminder` objects (None = calendar defaults)

## Writing Single Events

Create and add events using `Event.from_datetimes()`:

```python
from calgebra.gcsa import calendars, Event, Reminder
from calgebra import at_tz

cals = calendars()
primary = cals[0]
at = at_tz("US/Pacific")

# Create a timed event
# Note: calendar_id/calendar_summary are always ignored on write
# (always uses the target calendar's metadata - allows moving events between calendars)
meeting = Event.from_datetimes(
    start=at(2025, 1, 15, 14, 0),  # 2:00 PM Pacific
    end=at(2025, 1, 15, 15, 0),    # 3:00 PM Pacific
    summary="Team Meeting",
    description="Weekly team sync",
    reminders=[
        Reminder(method="email", minutes=30),
        Reminder(method="popup", minutes=15),
    ],
)

# Add to calendar
results = primary.add(meeting)
if results[0].success:
    print(f"Event created: {results[0].event.id}")
else:
    print(f"Error: {results[0].error}")
```

### All-Day Events

All-day events are automatically inferred when:
- Duration is whole days (within 1 hour tolerance for DST)
- Start and end are at midnight boundaries in the calendar's timezone

You can also explicitly set `is_all_day`:

```python
# Auto-infer all-day (default)
vacation = Event.from_datetimes(
    start=at(2025, 7, 1),
    end=at(2025, 7, 10),  # 9 days
    summary="Vacation",
)

# Explicitly set all-day
holiday = Event.from_datetimes(
    start=at(2025, 12, 25),
    end=at(2025, 12, 26),
    summary="Christmas",
    is_all_day=True,  # Force all-day
)

primary.add(vacation)
primary.add(holiday)
```

## Writing Recurring Events

Create recurring events using `calgebra`'s `recurring()` patterns:

```python
from calgebra.gcsa import calendars, Event, Reminder
from calgebra import recurring, at_tz, HOUR

cals = calendars()
primary = cals[0]
at = at_tz("US/Pacific")

# Weekly meeting (every Monday at 2 PM, starting Jan 6, 2025)
weekly_pattern = recurring(
    freq="weekly",
    day="monday",
    start=at(2025, 1, 6, 14, 0),  # First occurrence (tz inferred from datetime)
    duration=1 * HOUR,
)

# Add with metadata
results = primary.add(
    weekly_pattern,
    summary="Weekly Standup",
    description="Team sync meeting",
    reminders=[Reminder(method="popup", minutes=5)],
)

if results[0].success:
    print(f"Recurring event created: {results[0].event.id}")
```

**Pattern Parameters** (`recurring()`):
- `start`: First occurrence as datetime/timestamp, OR seconds from midnight (time-of-day only)
- `duration`: Event duration in seconds
- `tz`: Timezone (inferred from `start` if datetime with tzinfo, otherwise defaults to UTC)

**Metadata Parameters** (`add()`):
- `summary`: Event title
- `description`: Event description
- `reminders`: List of `Reminder` objects

**Supported Recurrence Patterns:**
- `freq`: `"daily"`, `"weekly"`, `"monthly"`, `"yearly"`
- `day`: Day of week (`"monday"`, `"tuesday"`, etc.) or list for multiple days
- `day_of_month`: Day of month (1-31) or list
- `month`: Month (1-12) or list
- `week`: Week offset (`1` = first, `-1` = last)
- `interval`: Frequency multiplier (e.g., `2` = every 2 weeks)

**Examples:**

```python
from calgebra import recurring, HOUR

# Every weekday at 9 AM, starting Jan 6, 2025
workdays = recurring(
    freq="weekly",
    day=["monday", "tuesday", "wednesday", "thursday", "friday"],
    start=at(2025, 1, 6, 9, 0),
    duration=8 * HOUR,
)

# First Monday of every month at 10 AM
monthly = recurring(
    freq="monthly",
    day="monday",
    week=1,  # First week
    start=at(2025, 1, 6, 10, 0),
    duration=1 * HOUR,
)

# Every 2 weeks on Friday at 3 PM
biweekly = recurring(
    freq="weekly",
    day="friday",
    interval=2,  # Every 2 weeks
    start=at(2025, 1, 3, 15, 0),
    duration=1 * HOUR,
)
```

## Removing Events

### Remove Single Event

```python
from calgebra.gcsa import calendars

cals = calendars()
primary = cals[0]

# Get an event
events = list(primary[at("2025-01-15"):at("2025-01-16")])
if events:
    event = events[0]
    
    # Remove it
    results = primary.remove(event)
    if results[0].success:
        print("Event deleted")
    else:
        print(f"Error: {results[0].error}")
```

### Remove Recurring Instance

To remove a single occurrence from a recurring series (without deleting the entire series):

```python
# Get a recurring instance
events = list(primary[at("2025-01-20"):at("2025-01-21")])
if events:
    instance = events[0]
    
    # Check if it's a recurring instance
    if instance.recurring_event_id:
        # Remove just this instance (adds to exdates)
        results = primary.remove(instance)
        if results[0].success:
            print("Instance removed from series")
```

### Remove Entire Recurring Series

To delete all occurrences of a recurring event:

```python
# Get any instance from the series
events = list(primary[at("2025-01-20"):at("2025-01-21")])
if events:
    instance = events[0]
    
    # Remove entire series
    results = primary.remove_series(instance)
    if results[0].success:
        print("Entire recurring series deleted")
```

**Note:** You can also remove a series using the master event directly (if you have its ID).

## Common Patterns

### Finding Free Time

Combine Google Calendar with `calgebra`'s set operations to find available time slots:

```python
from calgebra.gcsa import calendars
from calgebra import day_of_week, time_of_day, at_tz, HOUR

cals = calendars()
primary = cals[0]
at = at_tz("US/Pacific")

# Define business hours
weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"])
business_hours = time_of_day(start=9*HOUR, duration=8*HOUR, tz="US/Pacific")
available = weekdays & business_hours

# Get busy times from calendar
busy = primary[at("2025-01-01"):at("2025-02-01")]

# Find free time
free = available - busy

# Filter for slots >= 2 hours
from calgebra import hours
long_slots = free & (hours >= 2)

# Get results
meeting_times = list(long_slots[at("2025-01-01"):at("2025-02-01")])
```

### Blocking Time

Create recurring blocks for focus time, office hours, etc.:

```python
from calgebra.gcsa import calendars, Event, Reminder
from calgebra import recurring, at_tz, HOUR

cals = calendars()
primary = cals[0]
at = at_tz("US/Pacific")

# Block 2-4 PM every weekday for focus time
focus_time = recurring(
    freq="weekly",
    day=["monday", "tuesday", "wednesday", "thursday", "friday"],
    start=at(2025, 1, 6, 14, 0),
    duration=2 * HOUR,
)

primary.add(
    focus_time,
    summary="Focus Time",
    description="No meetings during this time",
    reminders=[Reminder(method="popup", minutes=5)],
)
```

### Syncing Multiple Calendars

Query and combine events from multiple calendars:

```python
from calgebra.gcsa import calendars
from calgebra import union, at_tz

cals = calendars()
at = at_tz("US/Pacific")

# Get events from multiple calendars
work = cals[0]  # Work calendar
personal = cals[1]  # Personal calendar

# Combine all events
all_events = union(work, personal)

# Query combined timeline
busy_times = list(all_events[at("2025-01-01"):at("2025-02-01")])
```

### Working with Event Metadata

Access and filter by event properties:

```python
from calgebra.gcsa import calendars
from calgebra import field, at_tz

cals = calendars()
primary = cals[0]
at = at_tz("US/Pacific")

# Get events
events = list(primary[at("2025-01-01"):at("2025-02-01")])

# Filter by summary
summary_field = field("summary")
important = primary & (summary_field == "Important Meeting")

# Filter all-day events
is_all_day_field = field("is_all_day")
all_day_events = primary & (is_all_day_field == True)

# Access event properties
for event in events:
    print(f"{event.summary}: {event.start} - {event.end}")
    if event.reminders:
        for reminder in event.reminders:
            print(f"  Reminder: {reminder.method} {reminder.minutes} min before")
```

## Error Handling

All write operations return `WriteResult` objects:

```python
from calgebra.gcsa import calendars, Event
from calgebra import at_tz

cals = calendars()
primary = cals[0]
at = at_tz("US/Pacific")

event = Event.from_datetimes(
    start=at(2025, 1, 15, 14, 0),
    end=at(2025, 1, 15, 15, 0),
    summary="Meeting",
)

results = primary.add(event)
result = results[0]

if result.success:
    print(f"Success! Event ID: {result.event.id}")
else:
    print(f"Error: {result.error}")
    # Handle error appropriately
```

## Type Hints

For better IDE support and type checking:

```python
from calgebra.gcsa import Calendar, Event, Reminder
from calgebra import at_tz

cals: list[Calendar] = calendars()
primary: Calendar = cals[0]
at = at_tz("US/Pacific")

event: Event = Event.from_datetimes(
    start=at(2025, 1, 15, 14, 0),
    end=at(2025, 1, 15, 15, 0),
    summary="Meeting",
)
```

## See Also

- [API Reference](API.md) - Complete API documentation
- [Tutorial](TUTORIAL.md) - Learn calgebra's core concepts
- [gcsa Documentation](https://github.com/getyourguide/gcsa) - Underlying Google Calendar library

