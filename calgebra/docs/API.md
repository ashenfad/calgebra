# calgebra API Reference

## Core Types (`calgebra.core`)

### `timeline(*intervals)`
Create a timeline from a static collection of intervals without needing to subclass `Timeline`.

- Automatically sorts intervals by `(start, end)`
- Preserves subclass types (works with custom interval subclasses)
- Returns an immutable timeline

**Example:**
```python
from calgebra import timeline, Interval

# Simple timeline
my_events = timeline(
    Interval(start=1000, end=2000),
    Interval(start=5000, end=6000),
)

# Works with subclassed intervals too
@dataclass(frozen=True, kw_only=True)
class Event(Interval):
    title: str

events = timeline(
    Event(start=1000, end=2000, title="Meeting"),
    Event(start=5000, end=6000, title="Lunch"),
)
```

### `Timeline[IvlOut]`
- `fetch(start, end)` → iterable of intervals within bounds (inclusive integer seconds)
- `__getitem__(slice)` → shorthand for `fetch`, accepts int or timezone-aware datetime slice bounds
  - Integer seconds (Unix timestamps): `timeline[1735689600:1767225600]`
  - Timezone-aware datetime: `timeline[datetime(2025, 1, 1, tzinfo=timezone.utc):...]`
  - Naive datetimes are rejected with TypeError
  - **Automatic clipping**: Intervals are automatically clipped to query bounds. Any interval extending beyond `[start:end]` will be trimmed to fit. This ensures accurate aggregations and consistent set operations.
- Set-like operators:
  - `timeline | other` → `Union`
  - `timeline & other` → `Intersection` or `Filtered`
  - `timeline - other` → `Difference`
  - `~timeline` → `Complement`

### `Filter[IvlIn]`
- `apply(event)` → predicate on intervals
- Logical combinations:
  - `filter & other` → `And`
  - `filter | other` → `Or`
  - `filter & timeline` → filtered timeline

### `flatten(timeline)`
- Returns a coalesced timeline by complementing twice. Useful before aggregations or rendering availability. Emits mask `Interval`s and supports unbounded queries (start/end can be `None`).

### `union(*timelines)` / `intersection(*timelines)`
- Functional counterparts to chaining `|` / `&`; require at least one operand and preserve overlaps. `intersection` emits one interval per source for each overlap; use `flatten` if you want single coalesced spans.

## Interval Helpers (`calgebra.interval`)
- `Interval(start, end)` dataclass with inclusive bounds.
- Type vars `IvlIn`, `IvlOut` for generic timelines/filters.

## Properties (`calgebra.properties`)
- Base `Property` class (`apply(event)`).
- Duration helpers (inclusive lengths):
  - `seconds`, `minutes`, `hours`, `days`
- Boundary helpers:
  - `start`, `end`

### Property Helpers

#### `field(accessor)`
Create a property from a field name or accessor function. Makes it easy to create properties for custom interval fields without subclassing.

**Parameters:**
- `accessor`: Either a field name string or a function that extracts a value

**Returns:** A `Property` that can be used in filters and comparisons

**Examples:**
```python
from calgebra import field, one_of

# Simple field access by name
priority = field('priority')
high_priority = timeline & (priority >= 8)

# Type-safe field access with lambda
priority = field(lambda e: e.priority)

# Computed properties
tag_count = field(lambda e: len(e.tags))
multi_tagged = timeline & (tag_count >= 2)
```

#### `one_of(property, values)`
Check if a scalar property value is in the given set of values.

**Use for:** String fields, integer fields, enum fields, etc.

**Examples:**
```python
category = field('category')
work_events = timeline & one_of(category, {"work", "planning"})
```

#### `has_any(property, values)`
Check if a collection property contains **any** of the given values.

**Use for:** Set fields, list fields, tuple fields, etc.

**Examples:**
```python
from calgebra import field, has_any

# Match events with ANY of these tags
tags = field('tags')  # tags: set[str]
work_events = timeline & has_any(tags, {"work", "urgent"})

# Works with lists too
labels = field('labels')  # labels: list[str]
todo_items = timeline & has_any(labels, {"todo", "important"})
```

#### `has_all(property, values)`
Check if a collection property contains **all** of the given values.

**Use for:** Set fields, list fields, tuple fields, etc.

**Examples:**
```python
from calgebra import field, has_all

# Match only events with BOTH tags
tags = field('tags')
critical_work = timeline & has_all(tags, {"work", "urgent"})
```

**Note:** Use `one_of()` for scalar fields and `has_any()`/`has_all()` for collection fields.

## Metrics (`calgebra.metrics`)
- `total_duration(timeline, start, end)` → inclusive seconds covered (uses `flatten`)
- `max_duration(timeline, start, end)` → longest interval clamped to bounds (returns `Interval | None`)
- `min_duration(timeline, start, end)` → shortest interval clamped to bounds (returns `Interval | None`)
- `count_intervals(timeline, start, end)` → number of events in slice
- `coverage_ratio(timeline, start, end)` → fraction of window covered (`float`)

## Recurring Patterns (`calgebra.recurrence`)
Timezone-aware recurrence pattern generators backed by `python-dateutil`'s RFC 5545 implementation.

### `recurring(freq, *, interval=1, day=None, week=None, day_of_month=None, month=None, start=0, duration=DAY, tz="UTC")`
Generate intervals based on recurrence rules with full RFC 5545 support.

**Parameters:**
- `freq`: Recurrence frequency - `"daily"`, `"weekly"`, `"monthly"`, or `"yearly"`
- `interval`: Repeat every N units (default: 1). Examples:
  - `interval=2` with `freq="weekly"` → bi-weekly
  - `interval=3` with `freq="monthly"` → quarterly
- `day`: Day name(s) for weekly/monthly patterns (single string or list)
  - Valid: `"monday"`, `"tuesday"`, `"wednesday"`, `"thursday"`, `"friday"`, `"saturday"`, `"sunday"`
  - Examples: `"monday"`, `["tuesday", "thursday"]`
- `week`: Nth occurrence for monthly patterns (1=first, -1=last, 2=second, etc.)
  - Combine with `day` for patterns like "first Monday" or "last Friday"
- `day_of_month`: Day(s) of month (1-31, or -1 for last day)
  - Examples: `1`, `[1, 15]`, `-1`
- `month`: Month(s) for yearly patterns (1-12)
  - Examples: `1`, `[1, 4, 7, 10]` (quarterly)
- `start`: Start time in seconds from midnight (default: 0)
- `duration`: Duration in seconds (default: DAY = full day)
- `tz`: IANA timezone name

**Examples:**
```python
from calgebra import recurring, HOUR, MINUTE

# Bi-weekly Mondays at 9:30am for 30 minutes
biweekly = recurring(freq="weekly", interval=2, day="monday", 
                     start=9*HOUR + 30*MINUTE, duration=30*MINUTE, tz="US/Pacific")

# First Monday of each month
first_monday = recurring(freq="monthly", week=1, day="monday", tz="UTC")

# Last Friday of each month
last_friday = recurring(freq="monthly", week=-1, day="friday", tz="UTC")

# 1st and 15th of every month
payroll = recurring(freq="monthly", day_of_month=[1, 15], tz="UTC")

# Quarterly (every 3 months)
quarterly = recurring(freq="monthly", interval=3, day_of_month=1, tz="UTC")

# Annual company party: June 15th at 5pm for 3 hours
annual_party = recurring(freq="yearly", month=6, day_of_month=15, 
                         start=17*HOUR, duration=3*HOUR, tz="UTC")

# Tax deadlines: April 15th each year
tax_deadline = recurring(freq="yearly", month=4, day_of_month=15, tz="UTC")
```

### Convenience Wrappers

For common patterns, use these ergonomic wrappers:

#### `day_of_week(days, tz="UTC")`
Convenience wrapper for filtering by day(s) of the week. Equivalent to `recurring(freq="weekly", day=days, tz=tz)`.

- `days`: Single day name or list (e.g., `"monday"`, `["tuesday", "thursday"]`)
- `tz`: IANA timezone name

**Examples:**
```python
mondays = day_of_week("monday", tz="US/Pacific")
weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"])
weekends = day_of_week(["saturday", "sunday"], tz="UTC")
```

#### `time_of_day(start=0, duration=DAY, tz="UTC")`
Convenience wrapper for daily time windows. Equivalent to `recurring(freq="daily", start=start, duration=duration, tz=tz)`.

- `start`: Start time in seconds from midnight (default: 0)
- `duration`: Duration in seconds (default: DAY = full day)
- `tz`: IANA timezone name

**Examples:**
```python
from calgebra import time_of_day, HOUR, MINUTE

work_hours = time_of_day(start=9*HOUR, duration=8*HOUR, tz="US/Pacific")  # 9am-5pm
standup = time_of_day(start=9*HOUR + 30*MINUTE, duration=30*MINUTE, tz="UTC")  # 9:30am-10am
```

### Composing Patterns

Combine wrappers with `&` to create complex patterns:

```python
from calgebra import day_of_week, time_of_day, HOUR, MINUTE

# Business hours = weekdays & 9-5 (auto-flattened)
business_hours = (
    day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"])
    & time_of_day(start=9*HOUR, duration=8*HOUR, tz="US/Pacific")
)

# Monday standup = Mondays & 9:30-10am (auto-flattened)
monday_standup = (
    day_of_week("monday") & time_of_day(start=9*HOUR + 30*MINUTE, duration=30*MINUTE)
)
```

**Note:** Recurring patterns require finite bounds when slicing. When intersecting mask timelines (like recurring patterns), the result is automatically flattened to yield one interval per overlap.

## Transformations (`calgebra.transform`)

Operations that modify the shape or structure of intervals while preserving metadata.

### `buffer(timeline, *, before=0, after=0)`
Add buffer time before and/or after each interval.

**Parameters:**
- `timeline`: Source timeline
- `before`: Seconds to add before each interval (default: 0)
- `after`: Seconds to add after each interval (default: 0)

**Returns:** Timeline with buffered intervals preserving original metadata

**Examples:**
```python
from calgebra import buffer, HOUR, MINUTE

# Flights need 2 hours of pre-travel time
blocked = buffer(flights, before=2*HOUR)

# Meetings need 15 min buffer on each side
busy = buffer(meetings, before=15*MINUTE, after=15*MINUTE)

# Check for conflicts with expanded times
conflicts = blocked & work_calendar
```

### `merge_within(timeline, *, gap)`
Merge intervals separated by at most `gap` seconds.

**Parameters:**
- `timeline`: Source timeline
- `gap`: Maximum gap (in seconds) between intervals to merge across

**Returns:** Timeline with nearby intervals merged, preserving first interval's metadata

**Examples:**
```python
from calgebra import merge_within, MINUTE

# Treat alarms within 15 min as one incident
incidents = merge_within(alarms, gap=15*MINUTE)

# Group closely-scheduled meetings into busy blocks
busy_blocks = merge_within(meetings, gap=5*MINUTE)

# Combine with other operations
daily_incidents = incidents & day_of_week("monday")
```

**Note:** Unlike `flatten()`, `merge_within()` preserves metadata from the first interval in each merged group. Use `flatten()` when you don't need to preserve metadata and want all adjacent/overlapping intervals coalesced regardless of gap size.

## Module Exports (`calgebra.__init__`)
- `Interval`, `Timeline`, `Filter`, `Property`
- Timeline creation: `timeline`
- Properties and helpers: `start`, `end`, `seconds`, `minutes`, `hours`, `days`, `field`, `one_of`, `has_any`, `has_all`
- Metrics: `total_duration`, `max_duration`, `min_duration`, `count_intervals`, `coverage_ratio`
- Utils: `flatten`, `union`, `intersection`
- Recurring patterns: `recurring`, `day_of_week`, `time_of_day`
- Transforms: `buffer`, `merge_within`
- Time constants: `SECOND`, `MINUTE`, `HOUR`, `DAY`
- Utilities: `at_tz`, `docs`

## Google Calendar Integration (`calgebra.gcsa`)
- `list_calendars()` returns lightweight `CalendarItem` records (`id`, `summary`) for every calendar accessible to the authenticated Google account. Use it to present choices before instantiating a timeline.
- `Calendar(calendar | CalendarItem, client=None)` is a `Timeline[Event]` backed by `gcsa.GoogleCalendar`. Slice it like any other timeline—bounds are converted to UTC, paging is automatic, and results include metadata for downstream set operations.
- `Event` extends `Interval` with Google metadata: `id`, `calendar_id` (source calendar), `summary`, and optional `description`. These fields survive unions/intersections, ensuring you can trace provenance after composing multiple calendars.

## Notes
- All intervals are inclusive; durations use `end - start + 1`.
- Intervals support unbounded values: `start` or `end` can be `None` to represent -∞ or +∞.
- Complement and flatten support unbounded queries (start/end can be `None`).
- Aggregation helpers clamp to query bounds but preserve metadata via `dataclasses.replace`.
- Time window helpers are timezone-aware and use stdlib `zoneinfo`.
