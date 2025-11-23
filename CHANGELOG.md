# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [0.6.0] - 2025-11-22

### Added
- **Mutable Timeline API** (`calgebra.mutable`): Write operations (`add()`, `remove()`, `remove_series()`) with `WriteResult` return type for handling partial failures
- **Google Calendar Write Support**: `GoogleCalendarTimeline` (exported as `Calendar`) now supports creating, updating, and deleting events
- **Documentation**: New `GCSA.md` guide for Google Calendar integration

### Fixed
- Intersection algorithm now correctly handles overlapping intervals when sources have different lengths

## [0.5.0] - 2025-11-20

### Changed
- **Breaking**: All intervals now use **exclusive end bounds** (`[start, end)`), matching Python slicing idioms throughout the library.
  - `Interval(start=10, end=13)` now represents 3 seconds `{10, 11, 12}` (previously 4 seconds).
  - Adjacent intervals like `[0, 5)` and `[5, 10)` naturally touch at the boundary.

## [0.4.1] - 2025-11-19

### Added
- Minor performance improvement for union (now flattens nested ops)

### Fixed
- **Consistent Recurrence**: Recurring patterns now stay anchored consistently regardless of query timeframe

## [0.4.0] - 2025-11-19

### Changed
- **Breaking**: Timeline slicing now uses **exclusive end bounds** (`[start:end)`), aligning with standard Python slicing idioms. Previously, slicing was inclusive of the end bound.
  - `timeline[start:end]` now returns intervals in the range `[start, end - 1]`.
  - `Timeline.fetch(start, end)` also respects this exclusive end behavior.
- Updated metric functions (`total_duration`, `max_duration`, `min_duration`, `count_intervals`, `coverage_ratio`) to interpret their `end` parameter as exclusive.
- Updated `coverage_ratio` calculation to use `end - start` (instead of `end - start + 1`) for the denominator, correctly reflecting the span of an exclusive slice.

### Documentation
- Updated `README.md`, `TUTORIAL.md`, and `API.md` to explicitly state that timeline slicing uses exclusive end bounds while internal `Interval` objects remain inclusive.

## [0.3.2] - 2025-11-16

### Added
- `gcsa.Event` instances now include `calendar_summary` metadata alongside `calendar_id`, making it easier to display the original calendar when unions/intersections combine timelines.

### Changed
- Replaced `list_calendars()` with `calendars()`, which authenticates once and returns ready-to-use `Calendar` timelines (each reuses the shared client but tracks its own IDs/summaries).

## [0.3.1] - 2025-11-16

### Added
- `gcsa.Event` now carries its originating `calendar_id`, so provenance survives unions/differences without custom bookkeeping.

### Documentation
- Added an API section describing the gcsa module and its helpers to make the integration easier for agents and scripts to discover.

## [0.3.0] - 2025-11-06

### Added
- **`at_tz()` helper function**: Ergonomic timezone-aware datetime factory for timeline slicing
  - Create datetime factories: `at = at_tz("US/Pacific")`
  - Parse date strings: `at("2024-01-01")` → midnight in timezone
  - Use with slicing: `timeline[at("2024-01-01"):at("2024-12-31")]`

### Changed
- **Removed `date` object support in Timeline slicing**: Timeline slices now only accept `int` (Unix timestamps) or timezone-aware `datetime` objects.
- **Removed `timezone_name` parameter from `Calendar`**: The Calendar class no longer accepts a `timezone_name` parameter.

## [0.2.3] - 2025-10-30

### Added
- **Automatic interval clipping**: All timelines now automatically clip intervals to query bounds in `Timeline.__getitem__`. When you slice `timeline[start:end]`, any intervals extending beyond those bounds are trimmed to fit.

## [0.2.2] - 2025-10-30

### Added
- **Unbounded end support for recurring patterns**: `recurring()`, `day_of_week()`, and `time_of_day()` now support unbounded end queries via automatic paging (e.g., `recurring(...)[start:]`)
- Adjacent intervals from recurring patterns are now automatically merged via `flatten()`

### Fixed
- **Lookback bug fix**: Recurring patterns now correctly include long-duration events that start before the query range but extend into it
- Events that span midnight (e.g., 11pm for 3 hours) are now correctly captured across page boundaries

## [0.2.1] - 2025-10-27

### Added
- `buffer()` now validates that `before` and `after` parameters are non-negative

### Fixed
- `buffer()` now correctly handles unbounded intervals (None values) instead of raising TypeError
- `merge_within()` now correctly handles unbounded intervals when calculating gaps
- `Event.__str__()` now correctly handles unbounded intervals in string representation

## [0.2.0] - 2025-10-27

### Added
- **Unbounded intervals**: `Interval` now supports `None` for `start` or `end` to represent -∞ or +∞
- `finite_start` and `finite_end` properties on `Interval` that return sentinel values for algorithm use
- Complement (`~`) now supports unbounded queries (start/end can be `None`)
- `flatten()` now supports unbounded queries (uses double complement internally)
- Comprehensive test suite for unbounded interval operations

### Changed
- **Breaking**: `Interval.start` and `Interval.end` are now `int | None` instead of `int`
- `Start` and `End` properties may return sentinel values (NEG_INF/POS_INF) instead of `None` for simpler filtering
- Updated documentation to reflect unbounded interval support

## [0.1.0] - 2025-10-26

### Added
- Initial release of calgebra
- Core DSL with set-like operators (`|`, `&`, `-`, `~`) for timeline composition
- Timeline slicing with integer timestamps, timezone-aware datetime, and date objects
- Property-based filtering (`hours >= 2`, `start >= timestamp`, etc.)
- Recurring patterns via `recurring()`, `day_of_week()`, and `time_of_day()`
- Metric functions: `total_duration`, `max_duration`, `min_duration`, `count_intervals`, `coverage_ratio`
- Transformations: `buffer()` and `merge_within()`
- Google Calendar integration via `calgebra.gcsa.Calendar`
- Comprehensive documentation accessible via `calgebra.docs` dictionary

[0.6.0]: https://github.com/ashenfad/calgebra/releases/tag/v0.6.0
[0.5.0]: https://github.com/ashenfad/calgebra/releases/tag/v0.5.0
[0.4.1]: https://github.com/ashenfad/calgebra/releases/tag/v0.4.1
[0.4.0]: https://github.com/ashenfad/calgebra/releases/tag/v0.4.0
[0.3.2]: https://github.com/ashenfad/calgebra/releases/tag/v0.3.2
[0.3.1]: https://github.com/ashenfad/calgebra/releases/tag/v0.3.1
[0.3.0]: https://github.com/ashenfad/calgebra/releases/tag/v0.3.0
[0.2.3]: https://github.com/ashenfad/calgebra/releases/tag/v0.2.3
[0.2.2]: https://github.com/ashenfad/calgebra/releases/tag/v0.2.2
[0.2.1]: https://github.com/ashenfad/calgebra/releases/tag/v0.2.1
[0.2.0]: https://github.com/ashenfad/calgebra/releases/tag/v0.2.0
[0.1.0]: https://github.com/ashenfad/calgebra/releases/tag/v0.1.0

