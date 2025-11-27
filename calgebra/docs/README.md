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
from calgebra import day_of_week, time_of_day, hours, at_tz, HOUR
from itertools import islice

# Compose time windows
weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"])
work_hours = time_of_day(start=9*HOUR, duration=8*HOUR, tz="US/Pacific")
business_hours = weekdays & work_hours

# Find free time
busy = monday_meetings | friday_focus
free = business_hours - busy
long_slots = free & (hours >= 2)

# Query results (forward)
at = at_tz("US/Pacific")
meeting_options = list(long_slots[at("2025-01-01"):at("2025-02-01")])

# Query in reverse (last 5 events)
last_5 = list(islice(calendar[at("2024-01-01"):at("2025-01-01"):-1], 5))
```

Intervals use **exclusive end bounds** (`[start, end)`), matching Python slicing. `Interval(start=10, end=13)` represents 3 seconds. Intervals are automatically clipped to query bounds.

**Core Features:**
- **Set operations**: `|` (union), `&` (intersection), `-` (difference), `~` (complement)
- **Recurring patterns**: `recurring()`, `day_of_week()`, `time_of_day()` (RFC 5545 via `python-dateutil`)
- **Reverse iteration**: `timeline[end:start:-1]` for reverse chronological order
- **Aggregations**: `total_duration`, `max_duration`, `min_duration`, `count_intervals`, `coverage_ratio`
- **Transformations**: `buffer()` (add time around intervals), `merge_within()` (coalesce nearby intervals)
- **Google Calendar**: `calgebra.gcsa.calendars()` for read/write operations

**→ **[Quick-start](docs/QUICK-START.md)** | **[Tutorial](docs/TUTORIAL.md)** | **[API Reference](docs/API.md)** | **[Google Calendar](docs/GCSA.md)**


## License

MIT License - see LICENSE file for details.