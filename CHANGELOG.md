# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

