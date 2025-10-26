# calgebra 🗓️

A tiny DSL for merging and searching over calendar-like intervals.

## Installation

```bash
pip install calgebra

# Or with Google Calendar support
pip install calgebra[google-calendar]
```

## Quick Start

```python
from datetime import datetime, timezone
from calgebra import day_of_week, time_of_day, hours, HOUR

# Compose time windows from primitives
weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"])
work_hours = time_of_day(start=9*HOUR, duration=8*HOUR, tz="US/Pacific")
business_hours = weekdays & work_hours

# Union: combine busy times (in practice: from Google Calendar, databases, etc.)
monday_meetings = day_of_week("monday") & time_of_day(start=10*HOUR, duration=2*HOUR)
friday_focus = day_of_week("friday") & time_of_day(start=14*HOUR, duration=3*HOUR)
busy = monday_meetings | friday_focus

# Difference: find free time during business hours
free = business_hours - busy

# Filter: only slots >= 2 hours
long_slots = free & (hours >= 2)

# Fetch results with slice notation (supports int, datetime, or date)
start = datetime(2025, 1, 1, tzinfo=timezone.utc)
end = datetime(2025, 1, 31, tzinfo=timezone.utc)
meeting_options = list(long_slots[start:end])
```

Intervals in `calgebra` are inclusive of both `start` and `end`—durations therefore reflect every second covered by an interval. Timeline slices accept integer seconds (Unix timestamps), timezone-aware datetime objects, or date objects. When you subclass `Interval`, define your subclass as a dataclass (ideally `frozen=True`) so the algebra can clone and clamp events internally.

Common helpers and aggregates are exposed alongside the core DSL:

**Recurring Patterns** (RFC 5545 via `python-dateutil`):
- `recurring(freq, ...)` generates intervals based on recurrence rules (weekly, bi-weekly, monthly, etc.)
- `day_of_week(days, tz)` convenience wrapper for filtering by day(s) of week
- `time_of_day(start, duration, tz)` convenience wrapper for daily time windows
- `HOUR`, `MINUTE`, `DAY`, `SECOND` constants for readable time specifications
- Compose with `&` to create complex patterns like business hours, recurring meetings, etc.

**Aggregation & Analysis**:
- `flatten(timeline)` converts overlapping/adjacent spans into a coalesced timeline (returns mask `Interval`s and must be sliced with explicit bounds)
- `union(*timelines)` / `intersection(*timelines)` offer functional set operations
- `total_duration` sums inclusive coverage inside a window
- `max_duration` / `min_duration` find the longest or shortest clamped intervals
- `count_intervals` tallies events over a slice
- `coverage_ratio` reports utilization as a 0–1 fraction

**Transformations**:
- `buffer(timeline, before, after)` adds buffer time around each interval (useful for travel time, setup/teardown)
- `merge_within(timeline, gap)` coalesces intervals separated by at most `gap` seconds (useful for grouping related events)

**Integrations**:
- `calgebra.gcsa.Calendar` provides Google Calendar integration with timezone normalization and automatic paging; it assumes locally stored OAuth credentials

**→ [Read the full tutorial](TUTORIAL.md)** for a complete guide to the DSL  
**→ [API Reference](API.md)** for detailed function signatures and parameters


## Status

calgebra is in **beta** (v0.1.0). The core API is stable and ready for use. Feedback and contributions are welcome!

## License

MIT License - see LICENSE file for details.