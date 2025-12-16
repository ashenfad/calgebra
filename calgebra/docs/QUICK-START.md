# calgebra Quick Start

Set operations for calendar intervals. Compose timelines, find free time, detect conflicts.

## Core Types

```python
from calgebra import Interval, at_tz, timeline

# Intervals: time ranges with [start, end) exclusive end
at = at_tz("US/Pacific")
meeting = Interval.from_datetimes(start=at(2025, 1, 15, 14, 0), end=at(2025, 1, 15, 15, 0))

# Timelines: lazy interval sources, sliced to execute
events = list(my_calendar[at("2025-01-01"):at("2025-01-31")])

# Display results
from calgebra import pprint
pprint(events, tz="US/Pacific")
# 2025-01-15 14:00:00 -> 2025-01-15 15:00:00
```

## Operators

| Op | Meaning | Example |
|----|---------|---------|
| `\|` | Union | `alice_cal \| bob_cal` |
| `&` | Intersection | `calendar_a & calendar_b` |
| `-` | Difference | `workhours - my_calendar` |
| `~` | Complement | `~busy` (all free time) |

```python
# Find when everyone is free during work hours
busy = alice_cal | bob_cal | charlie_cal
free = workhours - busy
slots = list(free[start:end])
```

## Filtering

```python
from calgebra import hours, minutes

long_meetings = calendar & (hours >= 2)
short_meetings = calendar & (minutes < 30)
medium = calendar & (minutes >= 30) & (hours < 2)
```

## Recurring Patterns

```python
from calgebra import day_of_week, time_of_day, recurring, HOUR, MINUTE

# Weekdays 9-5
weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"], tz="US/Pacific")
work_hours = time_of_day(start=9*HOUR, duration=8*HOUR, tz="US/Pacific")
business_hours = weekdays & work_hours

# Specific recurring meeting
monday_standup = (
    day_of_week("monday", tz="US/Pacific") 
    & time_of_day(start=9*HOUR + 30*MINUTE, duration=30*MINUTE, tz="US/Pacific")
)

# Advanced: bi-weekly, monthly, etc.
biweekly = recurring(freq="weekly", interval=2, day="monday", start=9*HOUR, duration=HOUR, tz="US/Pacific")
first_monday = recurring(freq="monthly", week=1, day="monday", start=10*HOUR, duration=HOUR, tz="UTC")
```

## Transformations

```python
from calgebra import buffer, merge_within, HOUR, MINUTE

# Add travel buffer around flights
blocked = buffer(flights, before=2*HOUR, after=30*MINUTE)

# Merge nearby alarms into incidents
incidents = merge_within(alarms, gap=15*MINUTE)
```

## Metrics

```python
from calgebra import coverage_ratio, total_duration, count_intervals
from datetime import date

# Daily coverage for a month
daily = coverage_ratio(calendar, date(2025, 11, 1), date(2025, 12, 1), period="day", tz="US/Pacific")
# Returns: [(date(2025,11,1), 0.73), (date(2025,11,2), 0.81), ...]

# Total meeting time
total = total_duration(meetings, date(2025, 11, 1), date(2025, 11, 8))[0][1]
```

## Google Calendar

```python
from calgebra.gcsa import calendars, Calendar, Event
from calgebra import at_tz, union

at = at_tz("US/Pacific")

# Read
cals = calendars()
primary: Calendar = cals[0]  # primary may not be index 0
events = list(primary[at("2025-01-01"):at("2025-01-31")])

# Write
new_event = Event.from_datetimes(
    start=at(2025, 1, 15, 14, 0),
    end=at(2025, 1, 15, 15, 0),
    summary="Team Meeting",
)
results = primary.add(new_event)

# Compose multiple calendars
team_busy = union(*cals)
```

## Reverse Iteration

```python
from itertools import islice

# Get events in reverse chronological order
recent_first = list(calendar[start:end:-1])

# Get last 5 events (stops after 5)
last_5 = list(islice(calendar[start:end:-1], 5))

# Most recent event
most_recent = next(calendar[start:end:-1], None)

# Works with all operations
free_slots_recent = list((business_hours - busy)[start:end:-1])
```

> Reverse iteration note: intersection, difference, complement, and recurring patterns materialize reverse slices in memory. Keep reverse ranges bounded. Recurring reverse needs a finite `end`; Google Calendar reverse defaults to a 1-year lookback and fetches 30-day windows forward before reversing.

## Common Patterns

**Find meeting slots:**
```python
busy = alice_cal | bob_cal | charlie_cal
free = business_hours - busy
options = free & (hours >= 1)
slots = list(options[start:end])
```

**Detect conflicts:**
```python
conflicts = my_calendar & proposed_meeting_time
has_conflict = any(conflicts[start:end])
```

**Available work hours:**
```python
available = business_hours - my_calendar
free_slots = list(available[at("2025-01-15"):at("2025-01-16")])
```

**Last N events:**
```python
from itertools import islice
last_10 = list(islice(calendar[at("2020-01-01"):at("2025-01-01"):-1], 10))
```

**Overlap between timezones:**
```python
pacific_hours = day_of_week(weekdays, tz="US/Pacific") & time_of_day(start=9*HOUR, duration=8*HOUR, tz="US/Pacific")
london_hours = day_of_week(weekdays, tz="Europe/London") & time_of_day(start=9*HOUR, duration=8*HOUR, tz="Europe/London")
overlap = pacific_hours & london_hours
```

