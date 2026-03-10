---
name: calgebra
description: Set algebra for calendars. Use when working with time intervals, finding free time, detecting conflicts, composing calendars, filtering events by duration or properties, computing metrics, or building recurring patterns.
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
```

**Timelines** are lazy interval sources. Compose with operators, slice to execute:

```python
busy = alice_cal | bob_cal        # compose (no data fetched)
events = list(busy[start:end])    # slice to execute
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

## Filtering

```python
from calgebra import hours, minutes, field, one_of, has_any

long_meetings = calendar & (hours >= 2)
short = calendar & (minutes < 30)

# Custom fields
priority = field("priority")
high = timeline & (priority >= 8)

category = field("category")
work = timeline & one_of(category, {"work", "planning"})
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

```python
from calgebra import coverage_ratio, total_duration, count_intervals
from datetime import date

daily = coverage_ratio(calendar, date(2025, 11, 1), date(2025, 12, 1), period="day", tz="US/Pacific")
# Returns: [(date(2025,11,1), 0.73), ...]

weekly = total_duration(meetings, date(2025, 11, 1), date(2025, 12, 1), period="week")
monthly = count_intervals(calendar, date(2025, 1, 1), date(2026, 1, 1), period="month")

# Cyclic histograms
by_weekday = count_intervals(meetings, date(2025, 1, 1), date(2025, 3, 1),
    period="day", group_by="day_of_week", tz="US/Pacific")
# Returns: [(0, 45), (1, 52), ..., (6, 8)]  # Mon=0
```

Periods: `"hour"`, `"day"`, `"week"`, `"month"`, `"year"`, `"full"`.

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
