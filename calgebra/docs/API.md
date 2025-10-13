# calgebra API Reference

## Core Types (`calgebra.core`)

### `Timeline[IvlOut]`
- `fetch(start, end)` → iterable of intervals within bounds (inclusive integer seconds)
- `__getitem__(slice)` → shorthand for `fetch`
- Set-like operators:
  - `timeline | other` → `Union`
  - `timeline & other` → `Intersection` or `Filtered` (intersection yields a trimmed interval per source, so metadata from each input is preserved; use `flatten` when you need coalesced coverage)
  - `timeline - other` → `Difference`
  - `~timeline` → `Complement` (requires finite bounds)
- Extension hooks:
  - `_make_complement_interval(start, end)` → customize gap interval type
  - `_coerce_bound(value, edge)` → hook for accepting non-integer slice values (default only accepts integers)

### `Filter[IvlIn]`
- `apply(event)` → predicate on intervals
- Logical combinations:
  - `filter & other` → `And`
  - `filter | other` → `Or`
  - `filter & timeline` → filtered timeline

### `flatten(timeline)`
- Returns a coalesced timeline by complementing twice. Useful before aggregations or rendering availability. Emits plain `Interval`s and requires slicing with finite bounds (e.g. `flattened[start:end]`).

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
- `one_of(property, values)` → membership filter

## Metrics (`calgebra.metrics`)
- `total_duration(timeline, start, end)` → inclusive seconds covered (uses `flatten`)
- `max_duration(timeline, start, end)` → longest interval clamped to bounds (returns `Interval | None`)
- `min_duration(timeline, start, end)` → shortest interval clamped to bounds (returns `Interval | None`)
- `count_intervals(timeline, start, end)` → number of events in slice
- `coverage_ratio(timeline, start, end)` → fraction of window covered (`float`)

## Recurring Patterns (`calgebra.recurrence`)
Timezone-aware recurrence pattern generators backed by `python-dateutil`'s RFC 5545 implementation.

### `recurring(freq, *, interval=1, day=None, week=None, day_of_month=None, month=None, start_hour=0, duration_hours=24, tz="UTC")`
Generate intervals based on recurrence rules with full RFC 5545 support.

**Parameters:**
- `freq`: Recurrence frequency - `"daily"`, `"weekly"`, or `"monthly"`
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
- `start_hour`: Start hour of each occurrence (0-24, supports fractional)
- `duration_hours`: Duration in hours (supports fractional)
- `tz`: IANA timezone name

**Examples:**
```python
from calgebra import recurring

# Bi-weekly Mondays at 9:30am for 30 minutes
biweekly = recurring(freq="weekly", interval=2, day="monday", 
                     start_hour=9.5, duration_hours=0.5, tz="US/Pacific")

# First Monday of each month
first_monday = recurring(freq="monthly", week=1, day="monday", tz="UTC")

# Last Friday of each month
last_friday = recurring(freq="monthly", week=-1, day="friday", tz="UTC")

# 1st and 15th of every month
payroll = recurring(freq="monthly", day_of_month=[1, 15], tz="UTC")

# Quarterly (every 3 months)
quarterly = recurring(freq="monthly", interval=3, day_of_month=1, tz="UTC")
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

#### `time_of_day(start_hour=0, duration_hours=24, tz="UTC")`
Convenience wrapper for daily time windows. Equivalent to `recurring(freq="daily", start_hour=start_hour, duration_hours=duration_hours, tz=tz)`.

- `start_hour`: Start hour (0-24), supports fractional hours (e.g., 9.5 = 9:30am)
- `duration_hours`: Duration in hours (supports fractional)
- `tz`: IANA timezone name

**Examples:**
```python
work_hours = time_of_day(start_hour=9, duration_hours=8, tz="US/Pacific")  # 9am-5pm
standup = time_of_day(start_hour=9.5, duration_hours=0.5, tz="UTC")  # 9:30am-10am
```

### Composing Patterns

Combine wrappers with `&` to create complex patterns:

```python
from calgebra import day_of_week, time_of_day, flatten

# Business hours = weekdays & 9-5 (flatten to coalesce)
business_hours = flatten(
    day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"])
    & time_of_day(start_hour=9, duration_hours=8, tz="US/Pacific")
)

# Monday standup = Mondays & 9:30-10am
monday_standup = flatten(
    day_of_week("monday") & time_of_day(start_hour=9.5, duration_hours=0.5)
)
```

**Note:** Recurring patterns require finite bounds when slicing. Intersection yields one interval per source, so use `flatten` to coalesce results.

## Module Exports (`calgebra.__init__`)
- `Interval`, `Timeline`, `Filter`, `Property`
- Properties and helpers: `start`, `end`, `seconds`, `minutes`, `hours`, `days`, `one_of`
- Metrics: `total_duration`, `max_duration`, `min_duration`, `count_intervals`, `coverage_ratio`
- Utils: `flatten`, `union`, `intersection`
- Recurring patterns: `recurring`, `day_of_week`, `time_of_day`

## Notes
- All intervals are inclusive; durations use `end - start + 1`.
- Complement and flatten require finite bounds when slicing.
- Aggregation helpers clamp to query bounds but preserve metadata via `dataclasses.replace`.
- Time window helpers are timezone-aware and use stdlib `zoneinfo`.
