# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/ashenfad/calgebra/releases/tag/v0.1.0
[0.2.0]: https://github.com/ashenfad/calgebra/releases/tag/v0.2.0

