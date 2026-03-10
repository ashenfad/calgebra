---
name: calgebra
description: Set algebra for calendars. Use when working with time intervals, finding free time, detecting conflicts, composing calendars, filtering events by duration or properties, computing metrics, or building recurring patterns.
modules:
  - calgebra
user-invocable: true
---

# calgebra

Set algebra for calendars. Compose lazily, query efficiently.

## Core Concepts

**Intervals** are time ranges `[start, end)` with exclusive end bounds (Unix timestamps):

```python
from calgebra import Interval, at_tz

at = at_tz("US/Pacific")
meeting = Interval.from_datetimes(start=at(2025, 1, 15, 14, 0), end=at(2025, 1, 15, 15, 0))
meeting.duration  # seconds (end - start)
```

**Timelines** are lazy interval sources. Compose with operators, slice to execute:

```python
from calgebra import timeline, union, intersection

# Static timeline from intervals
my_events = timeline(event1, event2, event3)

# Compose (no data fetched yet)
busy = alice_cal | bob_cal
busy = union(alice_cal, bob_cal, charlie_cal)  # functional form

# Slice to execute
events = list(busy[start:end])
```

**`at_tz()`** creates timezone-aware datetimes from strings, dates, or components:

```python
at = at_tz("US/Pacific")
at("2025-01-01")              # date string -> midnight
at(2025, 1, 15, 14, 30)      # components
at(date(2025, 1, 1))         # date object
```

## Operators

| Op | Meaning | Example |
|----|---------|---------|
| `\|` | Union | `alice \| bob` — anyone busy |
| `&` | Intersection | `cal_a & cal_b` — both busy |
| `-` | Difference | `workhours - meetings` — free time |
| `~` | Complement | `~busy` — all gaps |

Functional forms: `union(*timelines)`, `intersection(*timelines)`.

## Filtering

```python
from calgebra import hours, minutes, field, one_of, has_any, has_all

long_meetings = calendar & (hours >= 2)
short = calendar & (minutes < 30)

# Custom fields
priority = field("priority")
high = timeline & (priority >= 8)

category = field("category")
work = timeline & one_of(category, {"work", "planning"})

# Collection fields
tags = field("tags")
urgent = timeline & has_any(tags, {"urgent", "critical"})
both = timeline & has_all(tags, {"work", "urgent"})
```

## DataFrame Conversion (Preferred for Displaying Events)

Use `to_dataframe` to present events to the user — it produces a clean, readable table and is the idiomatic way to share calendar data:

```python
from calgebra import to_dataframe

events = list(calendar[start:end])
df = to_dataframe(events, tz="US/Pacific")

# Control columns
df = to_dataframe(events, include=["day", "time", "duration", "summary"])
df = to_dataframe(events, exclude=["uid", "dtstamp"])

# Raw datetime objects instead of formatted strings
df = to_dataframe(events, raw=True)
```

Columns: `day`, `time`, `duration` first, then type-specific fields (`summary`, `location`, etc.).

## Point-in-Time Queries

```python
# What's happening at a specific moment?
now_events = list(timeline.overlapping(unix_timestamp))
# Returns full unclipped intervals where start <= point < end
```

## Recurring Patterns

```python
from calgebra import day_of_week, time_of_day, recurring, HOUR, MINUTE

weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"], tz="US/Pacific")
work_hours = time_of_day(start=9*HOUR, duration=8*HOUR, tz="US/Pacific")
business_hours = weekdays & work_hours

# Advanced
biweekly = recurring(freq="weekly", interval=2, day="monday", start=9*HOUR, duration=HOUR, tz="US/Pacific")
first_monday = recurring(freq="monthly", week=1, day="monday", start=10*HOUR, duration=HOUR, tz="UTC")
last_friday = recurring(freq="monthly", week=-1, day="friday", tz="UTC")
payroll = recurring(freq="monthly", day_of_month=[1, 15], tz="UTC")
```

## Transformations

```python
from calgebra import buffer, merge_within, flatten, HOUR, MINUTE

blocked = buffer(flights, before=2*HOUR)
busy = buffer(meetings, before=15*MINUTE, after=15*MINUTE)
incidents = merge_within(alarms, gap=15*MINUTE)
coalesced = flatten(cal_a | cal_b)  # merge overlapping spans
```

## Metrics

All metric functions share this signature:

```python
metric(timeline, start, end, period="full", tz="UTC", group_by=None)
```

- **start/end**: `date`, `datetime`, or Unix `int`. Dates are interpreted as midnight in `tz`.
- **period**: Slices the start–end range into calendar-aligned windows. Each window produces one result tuple.
  - `"full"` — single window spanning start to end (default)
  - `"hour"`, `"day"`, `"week"` (ISO Mon–Sun), `"month"`, `"year"`
- **tz**: Timezone for interpreting dates and aligning period boundaries.
- **group_by** (optional): Collapses windows by cyclic key, summing values across matching periods. **Cannot be used with `period="full"` or `"year"`** — requires `"hour"`, `"day"`, `"week"`, or `"month"`.

**Available metrics:**

| Function | Returns per window | Notes |
|---|---|---|
| `total_duration` | `int` (seconds) | Flattens overlaps before summing |
| `count_intervals` | `int` | Number of intervals touching window |
| `coverage_ratio` | `float` (0–1) | Fraction of window covered |
| `max_duration` | `Interval \| None` | Longest interval in window |
| `min_duration` | `Interval \| None` | Shortest interval in window |

**Return shape:**
- Without `group_by`: `list[(date, value)]` — one tuple per period window
- With `group_by`: `list[(int, value)]` — one tuple per cyclic bucket, sorted by key

```python
from calgebra import total_duration, count_intervals, coverage_ratio
from calgebra import max_duration, min_duration
from datetime import date

# Total meeting seconds per day
daily = total_duration(meetings, date(2025, 11, 1), date(2025, 12, 1),
    period="day", tz="US/Pacific")
# Returns: [(date(2025,11,1), 7200), (date(2025,11,2), 0), ...]

# Single total over entire range (default period="full")
total = total_duration(meetings, date(2025, 11, 1), date(2025, 12, 1), tz="US/Pacific")
# Returns: [(date(2025,11,1), 180000)]

# Event count per month
monthly = count_intervals(calendar, date(2025, 1, 1), date(2026, 1, 1),
    period="month", tz="US/Pacific")

# Daily coverage ratio
daily_cov = coverage_ratio(calendar, date(2025, 11, 1), date(2025, 12, 1),
    period="day", tz="US/Pacific")
# Returns: [(date(2025,11,1), 0.73), ...]

# Longest meeting each day
longest = max_duration(meetings, date(2025, 11, 1), date(2025, 11, 8),
    period="day", tz="US/Pacific")
# Returns: [(date(2025,11,1), Event(...)), ...] — None for empty days
```

**Cyclic histograms (`group_by`):**

`group_by` aggregates across a cyclic dimension (e.g. all Mondays together).
**IMPORTANT: `period` and `group_by` are paired — you MUST copy the exact
`period`+`group_by` pair from the examples below. No other combinations work.**

```python
from datetime import date
from calgebra import total_duration, count_intervals, coverage_ratio

# "How much time in meetings per hour of day?"
by_hour = total_duration(cal, date(2025, 1, 1), date(2025, 4, 1),
    period="hour", group_by="hour_of_day", tz="US/Pacific")
# Returns: [(0, 0), ..., (9, 54000), ..., (23, 0)]  — 24 buckets

# "How many meetings per day of week?"
by_dow = count_intervals(cal, date(2025, 1, 1), date(2025, 4, 1),
    period="day", group_by="day_of_week", tz="US/Pacific")
# Returns: [(0, 45), (1, 52), ..., (6, 0)]  — 7 buckets, Mon=0

# "What % of time is booked per day of month?"
by_dom = coverage_ratio(cal, date(2025, 1, 1), date(2025, 4, 1),
    period="day", group_by="day_of_month", tz="US/Pacific")
# Returns: [(1, 0.73), (2, 0.81), ..., (31, 0.5)]  — 31 buckets

# "Total meeting time per week of year?"
by_woy = total_duration(cal, date(2025, 1, 1), date(2025, 4, 1),
    period="week", group_by="week_of_year", tz="US/Pacific")
# Returns: [(1, 18000), ..., (53, 0)]  — 53 buckets

# "Event count per month of year?"
by_moy = count_intervals(cal, date(2025, 1, 1), date(2026, 1, 1),
    period="month", group_by="month_of_year", tz="US/Pacific")
# Returns: [(1, 30), (2, 28), ..., (12, 25)]  — 12 buckets
```

These are the ONLY valid period+group_by pairs. Any other combination
(e.g. `period="full"` or `period="day"` with `group_by="hour_of_day"`)
raises ValueError.

## iCalendar (.ics) Files

```python
from calgebra import file_to_timeline, timeline_to_file

# Load .ics file into a timeline
cal = file_to_timeline("calendar.ics")
events = list(cal[start:end])

# Save timeline to .ics file
timeline_to_file(filtered_events, "output.ics")
```

## Reverse Iteration

```python
from itertools import islice

recent_first = list(calendar[start:end:-1])
last_5 = list(islice(calendar[start:end:-1], 5))
most_recent = next(calendar[start:end:-1], None)
```

## Displaying Results

```python
from calgebra import pprint

pprint(events, tz="US/Pacific")
print(event.format(tz="US/Pacific"))
```

## Caching

```python
from calgebra import cached

fast_cal = cached(slow_calendar, ttl=600)  # 10 min TTL
# Partial cache hits: only fetches uncached portions
```

## Common Patterns

**Find meeting slots:**
```python
busy = alice_cal | bob_cal | charlie_cal
free = business_hours - busy
options = free & (hours >= 1)
slots = list(options[at("2025-01-15"):at("2025-01-16")])
```

**Detect conflicts:**
```python
has_conflict = any((my_calendar & proposed_time)[start:end])
```

**Cross-timezone overlap:**
```python
pacific = weekdays & time_of_day(start=9*HOUR, duration=8*HOUR, tz="US/Pacific")
london = weekdays & time_of_day(start=9*HOUR, duration=8*HOUR, tz="Europe/London")
overlap = pacific & london
```

## Key Points

- Composition is lazy, slicing executes
- Exclusive end bounds `[start, end)` everywhere
- Always use timezone-aware datetimes (use `at_tz()`)
- `&` works between timelines and filters; `|` only between timelines
- Recurring patterns require finite bounds when slicing
