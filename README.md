# calgebra 🗓️

Set algebra for calendars. Compose lazily and query efficiently.

## Installation

```bash
pip install calgebra

# Or with Google Calendar support
pip install calgebra[google-calendar]
```

## Quick Start

```python
from calgebra import day_of_week, time_of_day, hours, at_tz, pprint, HOUR
from itertools import islice

# Setup
tz = "US/Pacific"
at = at_tz(tz)

# 1. Define Availability
weekdays = day_of_week(
    ["monday", "tuesday", "wednesday", "thursday", "friday"],
    tz=tz
)
work_hours = time_of_day(start=9*HOUR, duration=8*HOUR, tz=tz)
business_hours = weekdays & work_hours

# 2. Define Constraints
lunch = time_of_day(start=12*HOUR, duration=1*HOUR, tz=tz) 
monday_sync = day_of_week("monday", tz=tz) & time_of_day(start=9*HOUR, duration=1*HOUR, tz=tz)
busy = lunch | monday_sync

# 3. Calculate Free Time
free_time = (business_hours - busy) & (hours >= 2)

# 4. Query (Jan 2025)
start, end = at("2025-01-01"), at("2025-02-01")

print("Forward options:")
pprint(islice(free_time[start:end], 5), tz=tz)

print("\nReverse options (Last 3 in Jan):")
pprint(islice(free_time[end:start:-1], 3), tz=tz)
```

Intervals use **exclusive end bounds** (`[start, end)`), matching Python slicing. `Interval(start=10, end=13)` represents 3 seconds. Intervals are automatically clipped to query bounds.

**Core Features:**
- **Set operations**: `|` (union), `&` (intersection), `-` (difference), `~` (complement)
- **Recurring patterns**: `recurring()`, `day_of_week()`, `time_of_day()` (RFC 5545 via `python-dateutil`)
- **Reverse iteration**: `timeline[end:start:-1]` for reverse chronological order
- **Aggregations**: `total_duration`, `max_duration`, `min_duration`, `count_intervals`, `coverage_ratio`
- **Transformations**: `buffer()` (add time around intervals), `merge_within()` (coalesce nearby intervals)
- **Google Calendar**: `calgebra.gcsa.calendars()` for read/write operations

**→** **[Quick-start](docs/QUICK-START.md)** | **[Tutorial](docs/TUTORIAL.md)** | **[API Reference](docs/API.md)** | **[Google Calendar](docs/GCSA.md)**


## License

MIT License - see LICENSE file for details.