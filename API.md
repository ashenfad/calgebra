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

## Time Windows (`calgebra.windows`)
Built-in timezone-aware generators using two composable primitives (zero dependencies):

### `day_of_week(days, tz="UTC")`
- Returns a timeline for specific day(s) of the week (all hours)
- `days`: Single day name or list of day names (case-insensitive)
  - Valid: "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
- `tz`: IANA timezone name (e.g., "US/Pacific", "Europe/London")
- Examples:
  ```python
  mondays = day_of_week("monday", tz="US/Pacific")
  weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"])
  weekends = day_of_week(["saturday", "sunday"], tz="UTC")
  ```

### `time_of_day(start_hour=0, duration_hours=24, tz="UTC")`
- Returns a timeline for a specific time window each day (all days)
- `start_hour`: Start hour (0-24), supports fractional hours (e.g., 9.5 = 9:30am)
- `duration_hours`: Duration in hours (supports fractional hours)
- `tz`: IANA timezone name
- Examples:
  ```python
  work_hours = time_of_day(start_hour=9, duration_hours=8, tz="US/Pacific")  # 9am-5pm
  standup = time_of_day(start_hour=9.5, duration_hours=0.5, tz="UTC")  # 9:30am-10am
  ```

### Composing Time Windows
Combine primitives with `&` to create complex patterns:

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

**Note:** Time windows require finite bounds when slicing. Intersection yields one interval per source, so use `flatten` to coalesce results.

## Module Exports (`calgebra.__init__`)
- `Interval`, `Timeline`, `Filter`, `Property`
- Properties and helpers: `start`, `end`, `seconds`, `minutes`, `hours`, `days`, `one_of`
- Metrics: `total_duration`, `max_duration`, `min_duration`, `count_intervals`, `coverage_ratio`
- Utils: `flatten`, `union`, `intersection`
- Time windows: `day_of_week`, `time_of_day`

## Notes
- All intervals are inclusive; durations use `end - start + 1`.
- Complement and flatten require finite bounds when slicing.
- Aggregation helpers clamp to query bounds but preserve metadata via `dataclasses.replace`.
- Time window helpers are timezone-aware and use stdlib `zoneinfo`.
