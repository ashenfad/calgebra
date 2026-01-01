# calgebra API Reference

## Table of Contents

- [Core Types](#core-types-calgebracore)
- [Interval Helpers](#interval-helpers-calgebrainterval)
- [Properties](#properties-calgebraproperties)
- [Metrics](#metrics-calgebrametrics)
- [Recurring Patterns](#recurring-patterns-calgebrarecurrence)
- [Transformations](#transformations-calgebratransform)
- [Reverse Iteration](#reverse-iteration)
- [Mutable Timelines](#mutable-timelines-calgebramutable)
- [Google Calendar Integration](#google-calendar-integration-calgebragcsa)
- [iCalendar Integration (.ics)](#icalendar-integration-ics-calgebraical)
- [Notes](#notes)

---

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
- `fetch(start, end, *, reverse=False)` → iterable of intervals within bounds (inclusive start, exclusive end)
- `__getitem__(slice)` → shorthand for `fetch`, accepts int or timezone-aware datetime slice bounds
  - Integer seconds (Unix timestamps): `timeline[1735689600:1767225600]` (exclusive end)
  - Timezone-aware datetime: `timeline[datetime(2025, 1, 1, tzinfo=timezone.utc):...]`
  - Naive datetimes are rejected with TypeError
  - **Automatic clipping**: Intervals are automatically clipped to query bounds. Any interval extending beyond `[start:end)` will be trimmed to fit. This ensures accurate aggregations and consistent set operations.
  - **Reverse iteration**: Use step `-1` to iterate in reverse chronological order:
    - `timeline[start:end:-1]` — events in `[start, end)`, newest first
    - `timeline[end:start:-1]` — same (bounds are normalized)
    - Only step values of `1`, `-1`, or `None` are supported
  - **Reverse iteration notes**:
    - Keep reverse queries bounded (days to weeks) for operations that buffer results in memory (intersection, difference, complement, recurring patterns)
    - Recurring patterns and Google Calendar require a finite `end` bound for reverse iteration
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
- Merges overlapping and adjacent intervals into single coalesced spans. Loses custom metadata (emits basic `Interval` objects). Useful before aggregations or rendering availability. Supports unbounded queries (start/end can be `None`). See [Auto-Flattening and When to Use `flatten()`](TUTORIAL.md#auto-flattening-and-when-to-use-flatten) for when you need this vs. automatic flattening.

### `union(*timelines)` / `intersection(*timelines)`
- Functional forms of `|` and `&` operators. Accept multiple timelines as arguments.

## Interval Helpers (`calgebra.interval`)
- `Interval(start, end)` dataclass with exclusive end bounds `[start, end)`. Duration is `end - start`.
- `Interval.from_datetimes(start, end, **kwargs)` classmethod to create intervals from timezone-aware `datetime` objects.
  - Requires timezone-aware datetimes (raises `ValueError` for naive datetimes)
  - Converts to Unix timestamps automatically
  - Works with all `Interval` subclasses
  - Example: `Interval.from_datetimes(start=dt1, end=dt2)`
- `format(tz="UTC", fmt="%Y-%m-%d %H:%M:%S")` method to get a human-readable string representation.
- `pprint(intervals, tz="UTC", fmt=...)` helper to print a formatted list of intervals to stdout.
- Type vars `IvlIn`, `IvlOut` for generic timelines/filters.

## Properties (`calgebra.properties`)
- Base `Property` class (`apply(event)`).
- Duration helpers (exclusive end semantics: `end - start`):
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

All metric functions support **periodic aggregations** for efficient time-series analysis.

### Function Signatures

All metrics share a consistent signature pattern:

```python
metric_function(
    timeline: Timeline,
    start: date | datetime | int,
    end: date | datetime | int,
    period: Literal["day", "week", "month", "year", "full"] = "full",
    tz: str = "UTC"
) -> list[tuple[date, ReturnType]]
```

**Parameters:**
- `timeline`: Timeline to aggregate
- `start`: Query start (date → midnight in tz, datetime → as-is, int → Unix timestamp)
- `end`: Query end (exclusive)
- `period`: Aggregation period (default: `"full"`)
  - `"day"` - Full calendar days (midnight to midnight)
  - `"week"` - ISO weeks (Monday through Sunday)
  - `"month"` - Calendar months (1st to last day)
  - `"year"` - Calendar years (Jan 1 to Dec 31)
  - `"full"` - Exact query bounds (no calendar snapping)
- `tz`: Timezone for date interpretation and period boundaries (default: `"UTC"`)

**Returns:** List of `(period_start_date, value)` tuples

**Period alignment:** Periods snap to calendar boundaries even if query doesn't. Querying Mon 3pm → Fri 9am with `period="day"` returns 5 full calendar days (Mon 00:00 → Sat 00:00).

### Available Metrics

#### `total_duration()` → `list[tuple[date, int]]`
Total seconds covered per period (automatically flattens overlapping intervals).

```python
from datetime import date
from calgebra import total_duration

# Daily total duration for November
daily = total_duration(
    cal_union,
    start=date(2025, 11, 1),
    end=date(2025, 12, 1),
    period="day",
    tz="US/Pacific"
)
# Returns: [(date(2025,11,1), 28800), (date(2025,11,2), 14400), ...]
```

#### `coverage_ratio()` → `list[tuple[date, float]]`
Fraction of each period covered (0.0 to 1.0). Automatically flattens overlapping intervals.

```python
# Daily coverage ratio for November
daily = coverage_ratio(
    cal_union,
    start=date(2025, 11, 1),
    end=date(2025, 12, 1),
    period="day",
    tz="US/Pacific"
)
# Returns: [(date(2025,11,1), 0.73), (date(2025,11,2), 0.41), ...]
```

#### `count_intervals()` → `list[tuple[date, int]]`
Number of intervals per period.

```python
# Weekly event counts
weekly = count_intervals(timeline, date(2025, 11, 1), date(2025, 12, 1), period="week")
```

#### `max_duration()` → `list[tuple[date, Interval | None]]`
Longest interval per period, or None if empty.

```python
# Find longest meeting each day
longest = max_duration(meetings, date(2025, 11, 1), date(2025, 11, 8), period="day")
```

#### `min_duration()` → `list[tuple[date, Interval | None]]`
Shortest interval per period, or None if empty.

```python
# Find shortest meeting each week
shortest = min_duration(meetings, date(2025, 11, 1), date(2025, 12, 1), period="week")
```

### Performance

**Efficient:** Timeline data is fetched once, then aggregated across all periods.

```python
# Bad: 30 days × 7 calendars = 210 API calls
for day in november_days:
    ratio = coverage_ratio(cal_union, day.start, day.end)[0][1]

# Good: 7 API calls (one per calendar)
daily = coverage_ratio(cal_union, date(2025, 11, 1), date(2025, 12, 1), period="day")
```

### Empty Periods

Empty periods return appropriate null values:
- `total_duration`: `0` seconds
- `coverage_ratio`: `0.0`
- `count_intervals`: `0`
- `max_duration` / `min_duration`: `None`

### Timezone Handling

Periods respect the specified timezone, including DST transitions:
- Spring forward: 23-hour days
- Fall back: 25-hour days

```python
# November 2024 includes DST fall-back (Nov 3)
daily = total_duration(timeline, date(2024, 11, 1), date(2024, 11, 5), 
                       period="day", tz="US/Pacific")
# Nov 3 will have 25 hours worth of data
```

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
  - Valid: `"monday"`, `"tuesday"`, `"MO"`, `"1MO"`, `["TU", "TH"]`
  - Examples: `"monday"`, `["tuesday", "thursday"]`, `"1MO"` (first Monday)
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
Filter by day(s) of the week. Adjacent days are merged into continuous intervals.

- `days`: Single day name or list (e.g., `"monday"`, `["tuesday", "thursday"]`)
- `tz`: IANA timezone name

**Examples:**
```python
mondays = day_of_week("monday", tz="US/Pacific")
weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"])
weekends = day_of_week(["saturday", "sunday"], tz="UTC")
```

#### `time_of_day(start=0, duration=DAY, tz="UTC")`
Daily time window filter. Consecutive days are merged into continuous intervals.

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

**Note:** Recurring patterns require finite bounds when slicing. When intersecting with recurring patterns, overlapping intervals are automatically merged into single spans. See [Auto-Flattening and When to Use `flatten()`](TUTORIAL.md#auto-flattening-and-when-to-use-flatten) for details.

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

## Reverse Iteration

All timelines support reverse chronological iteration using Python's slice step syntax.

### Basic Usage

```python
from itertools import islice
from calgebra import at_tz

at = at_tz("US/Pacific")

# Forward iteration (default)
events = list(calendar[at("2025-01-01"):at("2025-02-01")])

# Reverse iteration
events_reversed = list(calendar[at("2025-01-01"):at("2025-02-01"):-1])

# Get last 5 events (efficient - stops after 5)
last_5 = list(islice(calendar[at("2024-01-01"):at("2025-01-01"):-1], 5))

# Most recent event
most_recent = next(calendar[start:end:-1], None)
```

### Bounds Normalization

For reverse iteration, bounds are normalized to `[min, max)` regardless of order:

```python
# These are equivalent:
calendar[100:500:-1]  # Bounds in "natural" order
calendar[500:100:-1]  # Bounds swapped

# Both yield events in [100, 500), newest first
```

### Step Validation

Only step values of `1`, `-1`, or `None` (defaults to `1`) are supported:

```python
calendar[start:end:1]    # ✅ Forward (explicit)
calendar[start:end]      # ✅ Forward (default)
calendar[start:end:-1]   # ✅ Reverse

calendar[start:end:2]    # ❌ ValueError
calendar[start:end:0]    # ❌ ValueError
```

### Composition

Reverse iteration works with all timeline operations:

```python
# Union
combined = (cal1 | cal2)[start:end:-1]

# Intersection
overlaps = (cal1 & cal2)[start:end:-1]

# Difference
free_time = (business_hours - busy)[start:end:-1]

# Filters
long_events = (calendar & (hours >= 2))[start:end:-1]

# Transforms
buffered = buffer(calendar, before=HOUR)[start:end:-1]
```

### Bound Requirements

Iteration requires a finite "origin" — the point where iteration begins:

| Timeline | Forward (needs `start`) | Reverse (needs `end`) |
|----------|-------------------------|----------------------|
| `MemoryTimeline` / `timeline()` | Optional | Optional |
| `RecurringPattern` | **Required** | **Required** |
| `Calendar` (GCSA) | Recommended* | **Required** |
| Composed (`\|`, `&`, `-`, `~`) | Inherits | Inherits |

\* Google Calendar API defaults to "now" if `start` is omitted, but explicit bounds are recommended for predictable behavior.

**Note:** Infinite sources (recurring patterns, Google Calendar) cannot iterate from ±∞, so they require a finite origin for the direction of travel. The opposite bound is always optional. For in-memory timelines, both bounds are optional since the data is finite.

## Mutable Timelines (`calgebra.mutable`)

`MutableTimeline` extends `Timeline` with write operations:

- `add(item, **metadata)` → `list[WriteResult]`
  - Add single intervals, iterables of intervals, or `RecurringPattern` objects
  - `metadata` provides backend-specific fields (e.g., `summary`, `description`, `reminders`)
  - Returns list of `WriteResult` objects (one per item written)

- `remove(items)` → `list[WriteResult]`
  - Remove single interval or iterable of intervals
  - For recurring instances, marks the instance as excluded (master event remains)
  - Returns list of `WriteResult` objects

- `remove_series(items)` → `list[WriteResult]`
  - Remove entire recurring series
  - Can use master event or any instance
  - Returns list of `WriteResult` objects

**Note:** `MemoryTimeline` is available for testing/development. For production use, see Google Calendar integration below.

**See also:** [Google Calendar Guide](GCSA.md) for complete write operation examples.

## Google Calendar Integration (`calgebra.gcsa`)

- `calendars()` → `list[Calendar]` - Returns ready-to-use `Calendar` timelines (one per accessible Google Calendar)
- `Calendar` - Timeline backed by Google Calendar API with full read/write support
- `Event` - Extends `Interval` with Google Calendar metadata:
  - `id`: Google Calendar event ID
  - `calendar_id`: Source calendar ID
  - `calendar_summary`: Human-readable calendar name
  - `summary`: Event title
  - `description`: Event description (optional)
  - `recurring_event_id`: Master recurring event ID (None for standalone/master events)
  - `is_all_day`: True for all-day events, False for timed events
  - `reminders`: List of `Reminder` objects (None = calendar defaults)
- `Reminder` - Event reminder/notification:
  - `method`: `"email"` or `"popup"`
  - `minutes`: Minutes before event start

**See also:** [Google Calendar Guide](GCSA.md) for authentication, examples, and common patterns.

## iCalendar Integration (.ics) (`calgebra.ical`)

Provides interoperability with standard iCalendar files (RFC 5545).

### Functions

#### `file_to_timeline(path)` → `MemoryTimeline`
Load an `.ics` file into an in-memory timeline.

- **Preserves Recurrence**: `RRULE`s are parsed into symbolic `RecurringPattern` objects, allowing efficient manipulation of infinite series.
- **Error Handling**: Skips malformed VEVENT components with a warning.

#### `timeline_to_file(timeline, path)`
Save a timeline to an `.ics` file.

- **Optimized**: If `MemoryTimeline` contains symbolic `RecurringPattern` objects, they are written as `RRULE`s.
- **Static Intervals**: Static intervals are written as individual `VEVENT`s.

### `RecurringPattern`
For advanced recurrence rules beyond `recurring()`'s simplified interface, you can instantiate `RecurringPattern` directly. It supports all standard RFC 5545 recurrence parts via `dateutil.rrule`.

```python
from calgebra.recurrence import RecurringPattern

# "Last weekday of the month"
pattern = RecurringPattern(
    freq="monthly",
    day=["MO", "TU", "WE", "TH", "FR"],
    bysetpos=-1,  # Last occurrence in the set
    tz="UTC"
)
```

**Supported Advanced Arguments:**
- `bysetpos`: Nth occurrence (e.g., `-1` for last, `[1, 3]` for 1st and 3rd)
- `byyearday`: Day of year (1 to 366)
- `byweekno`: Week of year (1 to 53)
- `byhour`, `byminute`, `bysecond`: Time components
- `wkst`: Week start day (default `MO`)

### `ICalEvent`
Extension of `Interval` for iCalendar data.

- **Attributes**:
  - `start`, `end`: Unix timestamps
  - `summary`: Title
  - `description`: Notes
  - `location`: Location string
  - `uid`: Unique Identifier
  - `is_all_day`: Boolean flag
  - `sequence`: Revision number
  - `dtstamp`: Creation timestamp
  - `calendar_name`: Source calendar name (from `X-WR-CALNAME`)
  - `status`: Event status (`"TENTATIVE"`, `"CONFIRMED"`, `"CANCELLED"`, or `None`)
  - `transp`: Time transparency (`"OPAQUE"` = busy, `"TRANSPARENT"` = free; default: `"OPAQUE"`)
  - `categories`: Tuple of category tags (e.g., `("work", "meeting")`)

**Field Helpers:**
Pre-defined `Property` objects correspond to the attributes above, allowing clean filtering syntax:
- `summary`, `description`, `location`, `uid`
- `is_all_day`: Useful for separating all-day events from timed events
- `dtstamp`, `sequence`, `recurrence_id`
- `calendar_name`: Filter by source calendar
- `status`: Filter by event status
- `transp`: Filter busy vs free time
- `categories`: Filter by category tags (use with `has_any()` or `has_all()`)

**Example:**
```python
from calgebra.ical import file_to_timeline, timeline_to_file, summary, is_all_day

# Load
timeline = file_to_timeline("my_calendar.ics")

# Filter
work_events = timeline & (summary == "Work")
all_day_items = timeline & (is_all_day == True)

# Save
timeline_to_file(work_events, "work_only.ics")
```

## Notes
- All intervals use **exclusive end bounds** `[start, end)`, matching Python slicing idioms. Duration is simply `end - start`.
- Timeline slicing also uses exclusive end bounds `[start:end)` for consistency.
- Intervals support unbounded values: `start` or `end` can be `None` to represent -∞ or +∞.
- Complement and flatten support unbounded queries (start/end can be `None`).
- Aggregation helpers clamp to query bounds but preserve metadata via `dataclasses.replace`.
- Time window helpers are timezone-aware and use stdlib `zoneinfo`.
