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
Built-in timezone-aware generators for common recurring patterns (zero dependencies):

### `business_hours(tz="UTC", start_hour=9, end_hour=17)`
- Returns a timeline of weekday work hours
- `tz`: IANA timezone name (e.g., "US/Pacific", "Europe/London")
- `start_hour`: inclusive hour (0-23), default 9
- `end_hour`: exclusive hour (0-24), default 17 (ends at 16:59:59)
- Example: `workhours = business_hours(tz="US/Pacific", start_hour=8, end_hour=18)`

### `weekdays(tz="UTC")`
- Returns a timeline of all Monday-Friday time (all hours)
- Example: `weekday_events = my_calendar & weekdays(tz="US/Eastern")`

### `weekends(tz="UTC")`
- Returns a timeline of all Saturday-Sunday time (all hours)
- Example: `weekend_free = ~my_calendar & weekends(tz="UTC")`

**Note:** All time window functions require finite bounds when slicing (e.g., `timeline[start:end]`).

## Module Exports (`calgebra.__init__`)
- `Interval`, `Timeline`, `Filter`, `Property`
- Properties and helpers: `start`, `end`, `seconds`, `minutes`, `hours`, `days`, `one_of`
- Metrics: `total_duration`, `max_duration`, `min_duration`, `count_intervals`, `coverage_ratio`
- Utils: `flatten`, `union`, `intersection`
- Time windows: `business_hours`, `weekdays`, `weekends`

## Notes
- All intervals are inclusive; durations use `end - start + 1`.
- Complement and flatten require finite bounds when slicing.
- Aggregation helpers clamp to query bounds but preserve metadata via `dataclasses.replace`.
- Time window helpers are timezone-aware and use stdlib `zoneinfo`.
