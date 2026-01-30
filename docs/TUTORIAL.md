# calgebra Tutorial

**calgebra** is a tiny DSL for working with calendar-like intervals using algebraic operations. Think of it as set theory for time ranges.

## Core Concepts

### Intervals

An `Interval` represents a time range with a `start` and `end` (integers, typically Unix timestamps). Intervals use **exclusive end bounds** `[start, end)`, matching Python slicing.

```python
from calgebra import Interval, at_tz

# From timestamps
meeting = Interval(start=1000, end=2000)

# From datetimes (recommended)
at = at_tz("US/Pacific")
vacation = Interval.from_datetimes(start=at(2025, 7, 1), end=at(2025, 7, 10))
```

### Timelines

A `Timeline` is a lazy source of intervals. Compose them with operators, then slice to execute:

```python
# Compose first (no data fetched yet)
busy = alice_calendar | bob_calendar

# Slice to execute
events = list(busy[start:end])
```

Timelines are **composable** via set operators and **lazy** until sliced.

### Slicing with `at_tz()`

The `at_tz()` helper creates timezone-aware datetimes from various inputs:

```python
from datetime import date, datetime
from calgebra import at_tz

at = at_tz("US/Pacific")

# Date strings → midnight
at("2025-01-01")

# Datetime strings
at("2025-01-01T09:00:00")

# Date objects
at(date(2025, 1, 1))

# Naive datetimes → attach timezone
at(datetime(2025, 1, 1, 9, 30))

# Components
at(2025, 1, 1, 9, 30)

# Use in slicing
events = list(timeline[at("2025-01-01"):at("2025-02-01")])
```

**Important**: Slicing requires timezone-aware datetimes. Naive datetimes raise `TypeError`.

### Automatic Clipping

Intervals are automatically clipped to query bounds:

```python
t = timeline(Interval(start=100, end=500))
result = list(t[0:300])
# Result: [Interval(start=100, end=300)]  # Clipped to query end
```

This ensures accurate aggregations and consistent set operations.

### Filters and Properties

Filters are predicates created from property comparisons:

```python
from calgebra import hours, minutes

short = minutes < 30
medium = (minutes >= 30) & (hours < 2)
long = hours >= 2

# Apply to timeline with &
long_meetings = calendar & (hours >= 2)
```

Built-in duration properties: `seconds`, `minutes`, `hours`, `days`

### Displaying Intervals

```python
from calgebra import pprint

pprint(events, tz="US/Pacific")
# 2025-01-01 09:00:00 -> 2025-01-01 17:00:00

# Single interval
print(events[0].format(tz="US/Pacific", fmt="%H:%M"))
# 09:00 -> 17:00
```

## Operators

calgebra uses Python operators to compose timelines:

| Op | Meaning | Example |
|----|---------|---------|
| `\|` | Union | `alice_cal \| bob_cal` — anyone busy |
| `&` | Intersection | `cal_a & cal_b` — both busy |
| `-` | Difference | `workhours - meetings` — free time |
| `~` | Complement | `~busy` — all gaps |

```python
# Union: combine intervals
all_busy = alice_calendar | bob_calendar

# Intersection: find overlaps
both_busy = calendar_a & calendar_b

# Difference: subtract intervals
available = workhours - my_calendar

# Complement: invert (find gaps)
free = ~my_calendar

# Filter with &
long_meetings = calendar & (hours >= 2)
```

**Note**: Complement (`~`) yields mask `Interval` objects without metadata. It works with unbounded queries: `list(free[None:None])`.

## Working Example

Finding time slots for a team meeting:

```python
from calgebra import timeline, Interval, hours, at_tz

at = at_tz("US/Pacific")

alice_busy = timeline(
    Interval.from_datetimes(start=at(2025, 1, 15, 9), end=at(2025, 1, 15, 10)),
    Interval.from_datetimes(start=at(2025, 1, 15, 14), end=at(2025, 1, 15, 15)),
)
bob_busy = timeline(
    Interval.from_datetimes(start=at(2025, 1, 15, 9, 30), end=at(2025, 1, 15, 10, 30)),
)

# Compose the query (lazy)
busy = alice_busy | bob_busy
free = ~busy
options = free & (hours >= 1)

# Execute by slicing
meeting_slots = list(options[at("2025-01-15"):at("2025-01-16")])
```

## Recurring Patterns

### Convenience Wrappers

```python
from calgebra import day_of_week, time_of_day, HOUR, MINUTE

# Days of week
mondays = day_of_week("monday", tz="US/Pacific")
weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"], tz="US/Pacific")
weekends = day_of_week(["saturday", "sunday"], tz="US/Pacific")

# Time windows
work_hours = time_of_day(start=9*HOUR, duration=8*HOUR, tz="US/Pacific")
standup_time = time_of_day(start=9*HOUR + 30*MINUTE, duration=30*MINUTE, tz="US/Pacific")

# Compose for business hours
business_hours = weekdays & work_hours

# Find free time during work hours
free = business_hours - my_calendar
```

### Advanced Patterns with `recurring()`

For patterns beyond simple weekly/daily, use `recurring()` directly:

```python
from calgebra import recurring, HOUR, MINUTE

# Bi-weekly (every other Monday)
biweekly = recurring(
    freq="weekly", interval=2, day="monday",
    start=9*HOUR + 30*MINUTE, duration=30*MINUTE, tz="US/Pacific"
)

# First Monday of each month
monthly = recurring(
    freq="monthly", week=1, day="monday",
    start=10*HOUR, duration=HOUR, tz="UTC"
)

# Last Friday of each month
last_friday = recurring(
    freq="monthly", week=-1, day="friday",
    start=17*HOUR, duration=2*HOUR, tz="US/Pacific"
)

# 1st and 15th of every month
payroll = recurring(freq="monthly", day_of_month=[1, 15], tz="UTC")
```

**Parameters:**
- `freq`: `"daily"`, `"weekly"`, `"monthly"`, `"yearly"`
- `interval`: Repeat every N units (e.g., `2` for bi-weekly)
- `day`: Day name(s) for weekly/monthly patterns
- `week`: Nth occurrence (`1`=first, `-1`=last)
- `day_of_month`: Specific day(s) of month (`1`-`31`)
- `month`: Month(s) for yearly patterns (`1`-`12`)
- `start`/`duration`: Time window in seconds
- `tz`: IANA timezone name

### Timezone Handling

Recurring patterns are timezone-aware, including DST:

```python
# Find overlap between Pacific and London work hours
pacific_hours = weekdays & time_of_day(start=9*HOUR, duration=8*HOUR, tz="US/Pacific")
london_hours = weekdays & time_of_day(start=9*HOUR, duration=8*HOUR, tz="Europe/London")
overlap = pacific_hours & london_hours
```

## Transformations

### `buffer()` — Add Time Around Events

```python
from calgebra import buffer, HOUR, MINUTE

# 2 hours before flights
blocked = buffer(flights, before=2*HOUR)

# 15 min buffer on both sides
busy = buffer(meetings, before=15*MINUTE, after=15*MINUTE)
```

### `merge_within()` — Coalesce Nearby Intervals

```python
from calgebra import merge_within, MINUTE

# Treat alarms within 15 min as one incident
incidents = merge_within(alarms, gap=15*MINUTE)

# Group nearby meetings into busy blocks
busy_blocks = merge_within(meetings, gap=5*MINUTE)
```

**vs `flatten()`**: `merge_within()` preserves metadata from the first interval; `flatten()` creates minimal `Interval` objects without metadata.

## Extending calgebra

### Custom Intervals

Subclass `Interval` as a frozen dataclass:

```python
from dataclasses import dataclass
from calgebra import Interval

@dataclass(frozen=True, kw_only=True)
class Event(Interval):
    title: str
    priority: int
```

### Custom Properties

Use `field()` for simple field access:

```python
from calgebra import field, one_of, has_any

# Field by name or lambda
priority = field('priority')
priority = field(lambda e: e.priority)

# Comparisons
high_priority = timeline & (priority >= 8)

# Membership (scalars)
category = field('category')
work = timeline & one_of(category, {"work", "planning"})

# Collection membership
tags = field('tags')
urgent = timeline & has_any(tags, {"urgent", "important"})
```

### Custom Timelines

```python
from calgebra import Timeline, Interval
from typing import override

class DatabaseTimeline(Timeline[Interval]):
    def __init__(self, db):
        self.db = db

    @override
    def fetch(self, start: int | None, end: int | None, *, reverse: bool = False):
        for row in self.db.query(start, end):
            yield Interval(start=row['start'], end=row['end'])
```

## Auto-Flattening

calgebra optimizes intersections based on interval types:

**Automatic** (no `flatten()` needed):
```python
# Mask & Mask → single interval per overlap
business_hours = weekdays & work_hours

# Rich & Mask → preserves rich metadata
work_meetings = my_calendar & work_hours
```

**When you need `flatten()`**:
```python
from calgebra import flatten

# Coalesce union results
all_busy = flatten(alice_cal | bob_cal)

# Both sources have metadata, want single spans
combined = flatten(calendar_a & calendar_b)
```

## Metrics

Aggregate timelines over periods:

```python
from datetime import date
from calgebra import total_duration, coverage_ratio, count_intervals

# Daily coverage for a month (single fetch, 30 results)
daily = coverage_ratio(
    calendar, date(2025, 11, 1), date(2025, 12, 1),
    period="day", tz="US/Pacific"
)
# Returns: [(date(2025,11,1), 0.73), (date(2025,11,2), 0.81), ...]

# Total duration
weekly = total_duration(meetings, date(2025, 11, 1), date(2025, 12, 1), period="week")

# Event counts
monthly = count_intervals(calendar, date(2025, 1, 1), date(2026, 1, 1), period="month")
```

**Periods:** `"day"`, `"week"`, `"month"`, `"year"`, `"full"` (exact bounds)

**Bounds:** Accepts `date`, timezone-aware `datetime`, or Unix timestamps.

See [API Reference](API.md#metrics-calgebrametrics) for full details including `group_by` histograms.

## Caching

For slow data sources like Google Calendar, wrap timelines with `cached()` to avoid repeated API calls:

```python
from calgebra import cached, at_tz
from calgebra.gcsa import calendars

cals = calendars()
at = at_tz("US/Pacific")

# Wrap with 10-minute TTL cache
team_busy = cached(cals[0] | cals[1] | cals[2], ttl=600)

# First query hits Google Calendar API
slots = list((business_hours - team_busy)[at("2025-01-01"):at("2025-01-31")])

# Subsequent queries use cache
slots2 = list((business_hours - team_busy)[at("2025-01-15"):at("2025-01-20")])
```

**Features:**
- **Partial hits**: Only fetches uncached portions of a query range
- **TTL eviction**: Expired segments are automatically purged and refetched

**Key field**: By default, intervals are deduplicated using the `id` field. For iCalendar sources, use `key="uid"`:

```python
# Local files are already fast; caching benefits remote CalDAV or URL sources
cached_ical = cached(ical_source, ttl=300, key="uid")
```

See [API Reference](API.md#caching-calgebracache) for full details.

## Key Points

- **Composition is lazy, slicing executes**: Build queries with operators, fetch with `timeline[start:end]`
- **Exclusive end bounds**: `[start, end)` everywhere, matching Python slicing
- **Always use timezones**: `at_tz()` is the ergonomic way to create tz-aware datetimes
- **Filters vs Timelines**: `&` works between them; `|` only between timelines
- **Unbounded intervals**: `start` or `end` can be `None` for infinity
