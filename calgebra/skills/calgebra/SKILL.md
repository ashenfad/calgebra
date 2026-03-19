---
name: calgebra
description: Set algebra for calendars. Use when working with time intervals, finding free time, detecting conflicts, composing calendars, filtering events by duration or properties, computing metrics, or building recurring patterns.
modules:
  - calgebra
user-invocable: true
---

# calgebra

Set algebra for calendars. Compose lazily, query efficiently.

## Quick Start

```python
from calgebra import at_tz, to_dataframe, total_duration, HOUR
from calgebra.gcal import calendars, transparency
from datetime import date

token = access_token
tz = "US/Pacific"
at = at_tz(tz)

cals = calendars(token)
primary = next(c for c in cals if c.primary)

# Events this week
events = list(primary[at("2025-01-20"):at("2025-01-27")])
df = to_dataframe(events, tz=tz)

# Busy time (excludes transparent/free events)
busy = primary & (transparency == "opaque")
busy_events = list(busy[at("2025-01-20"):at("2025-01-27")])
```

> **Imports matter:** `transparency` comes from `calgebra.gcal`, NOT from
> `calgebra`. Other field helpers like `hours`, `minutes`, `field` come
> from `calgebra`.

> **`at_tz()` is required** for all timeline slicing. You cannot pass bare
> `date` objects to slice bounds. Dates are only accepted by metrics.

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

# Compose (no data fetched yet)
busy = alice_cal | bob_cal
busy = union(alice_cal, bob_cal, charlie_cal)  # functional form

# Slice to execute — bounds must use at_tz(), NOT bare dates
at = at_tz("US/Pacific")
events = list(busy[at("2025-01-01"):at("2025-01-31")])
```

**`at_tz()`** creates timezone-aware datetimes for slicing. Always pair with `"US/Pacific"`:

```python
at = at_tz("US/Pacific")
at("2025-01-01")              # date string -> midnight
at(2025, 1, 15, 14, 30)      # components
at(date(2025, 1, 1))         # date object -> midnight
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

> **Important:** Use `&` between timelines and filters. `|` only works
> between timelines.

## DataFrame Conversion (Preferred for Displaying Events)

Use `to_dataframe` to present events to the user:

```python
from calgebra import to_dataframe

events = list(calendar[at("2025-01-01"):at("2025-02-01")])
df = to_dataframe(events, tz="US/Pacific")

# Control columns
df = to_dataframe(events, include=["day", "time", "duration", "summary"])
df = to_dataframe(events, exclude=["uid", "dtstamp"])

# Raw datetime objects instead of formatted strings
df = to_dataframe(events, raw=True)
```

**Default columns:** `day` (date string), `time` (time string), `duration` (formatted),
then type-specific fields (`summary`, `location`, etc.).
**With `raw=True`:** `day` → datetime, `time` → datetime, `duration` → int (seconds).

## Recurring Patterns

```python
from calgebra import day_of_week, time_of_day, recurring, HOUR, MINUTE

tz = "US/Pacific"
weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"], tz=tz)
work_hours = time_of_day(start=9*HOUR, duration=8*HOUR, tz=tz)
business_hours = weekdays & work_hours

# Advanced
biweekly = recurring(freq="weekly", interval=2, day="monday", start=9*HOUR, duration=HOUR, tz=tz)
first_monday = recurring(freq="monthly", week=1, day="monday", start=10*HOUR, duration=HOUR, tz=tz)
last_friday = recurring(freq="monthly", week=-1, day="friday", tz=tz)
payroll = recurring(freq="monthly", day_of_month=[1, 15], tz=tz)
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
- **period**: `"full"`, `"hour"`, `"day"`, `"week"` (ISO Mon–Sun), `"month"`, `"year"`
- **tz**: Always pass `"US/Pacific"` (or an explicit IANA timezone).
- **group_by** (optional): Collapses windows by cyclic key. **Cannot be used with `period="full"` or `"year"`**.

```python
from calgebra import total_duration, count_intervals, coverage_ratio
from datetime import date

tz = "US/Pacific"

# Total meeting seconds per day
daily = total_duration(meetings, date(2025, 11, 1), date(2025, 12, 1),
    period="day", tz=tz)
# Returns: [(date(2025,11,1), 7200), (date(2025,11,2), 0), ...]

# Daily coverage ratio
daily_cov = coverage_ratio(calendar, date(2025, 11, 1), date(2025, 12, 1),
    period="day", tz=tz)
```

**Cyclic histograms (`group_by`):**

Copy these exact `period`+`group_by` pairs — no other combinations work:

```python
# Meetings per hour of day
by_hour = total_duration(cal, date(2025, 1, 1), date(2025, 4, 1),
    period="hour", group_by="hour_of_day", tz=tz)

# Events per day of week (Mon=0)
by_dow = count_intervals(cal, date(2025, 1, 1), date(2025, 4, 1),
    period="day", group_by="day_of_week", tz=tz)

# Coverage per day of month
by_dom = coverage_ratio(cal, date(2025, 1, 1), date(2025, 4, 1),
    period="day", group_by="day_of_month", tz=tz)

# Total per week of year
by_woy = total_duration(cal, date(2025, 1, 1), date(2025, 4, 1),
    period="week", group_by="week_of_year", tz=tz)

# Events per month of year
by_moy = count_intervals(cal, date(2025, 1, 1), date(2026, 1, 1),
    period="month", group_by="month_of_year", tz=tz)
```

## iCalendar (.ics) Files

```python
from calgebra import file_to_timeline, timeline_to_file

cal = file_to_timeline("calendar.ics")
events = list(cal[at("2025-01-01"):at("2025-02-01")])

timeline_to_file(filtered_events, "output.ics")
```

## Reverse Iteration

```python
from itertools import islice

recent_first = list(calendar[start:end:-1])
last_5 = list(islice(calendar[start:end:-1], 5))
most_recent = next(calendar[start:end:-1], None)
```

## Common Patterns

**Find free time:**
```python
from calgebra.gcal import calendars, transparency
from calgebra import day_of_week, time_of_day, HOUR, at_tz

token = access_token
tz = "US/Pacific"
at = at_tz(tz)

cals = calendars(token)
primary = next(c for c in cals if c.primary)

weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"], tz=tz)
work_hours = time_of_day(start=9*HOUR, duration=8*HOUR, tz=tz)
business_hours = weekdays & work_hours

busy = primary & (transparency == "opaque")
free = business_hours - busy
slots = list(free[at("2025-01-20"):at("2025-01-24")])
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
- Always use `at_tz("US/Pacific")` for slice bounds — never bare dates
- `transparency` is imported from `calgebra.gcal`, not `calgebra`
- `&` works between timelines and filters; `|` only between timelines
- Recurring patterns require finite bounds when slicing
