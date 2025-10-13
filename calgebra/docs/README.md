# calgebra 🗓️

A tiny DSL for merging and searching over calendar-like intervals.

## Installation

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install the package (core library, no dependencies)
pip install -e .

# Or with Google Calendar support
pip install -e .[google-calendar]
```

## Quick Start

```python
from calgebra import business_hours, hours

# Built-in time windows (weekdays, weekends, business hours)
workhours = business_hours(tz="US/Pacific")

# Union: combine multiple calendars
busy = alice_calendar | bob_calendar | charlie_calendar

# Difference: find free time during business hours
free = workhours - busy

# Filter: only slots >= 2 hours
long_slots = free & (hours >= 2)

# Fetch results with slice notation
meeting_options = list(long_slots[start_second:end_second])
```

Intervals in `calgebra` are inclusive of both `start` and `end`—durations therefore reflect every second covered by an interval. Timeline slices accept integer seconds; timeline implementations can override `_coerce_bound` if they want to accept other time representations (for example, datetimes) and translate them internally. When you subclass `Interval`, define your subclass as a dataclass (ideally `frozen=True`) so the algebra can clone and clamp events internally.

Common helpers and aggregates are exposed alongside the core DSL:

**Time Windows** (built-in, zero dependencies):
- `business_hours(tz, start_hour, end_hour)` generates weekday work hours (default 9am-5pm)
- `weekdays(tz)` generates all Monday-Friday time
- `weekends(tz)` generates all Saturday-Sunday time

**Aggregation & Analysis**:
- `flatten(timeline)` converts overlapping/adjacent spans into a coalesced timeline (returns plain `Interval`s and must be sliced with explicit bounds)
- `union(*timelines)` / `intersection(*timelines)` offer functional set operations (intersection yields a trimmed copy from each source, so call `flatten(...)` if you need coalesced spans)
- `total_duration` sums inclusive coverage inside a window
- `max_duration` / `min_duration` find the longest or shortest clamped intervals
- `count_intervals` tallies events over a slice
- `coverage_ratio` reports utilization as a 0–1 fraction

**Integrations**:
- `calgebra.gcsa.Calendar` provides Google Calendar integration with timezone normalization and automatic paging; it assumes locally stored OAuth credentials

**→ [Read the full tutorial](TUTORIAL.md)** for a complete guide to the DSL

## Documentation for Agents

Documentation is available programmatically for AI agents and code-aware tools:

```python
import calgebra

# Access documentation as structured data
print(calgebra.docs.keys())  # dict_keys(['readme', 'tutorial', 'api'])

# Discover what the package does
readme = calgebra.docs["readme"]  # Package overview and quick start

# Learn how to use it
tutorial = calgebra.docs["tutorial"]  # Comprehensive guide with examples
api_ref = calgebra.docs["api"]        # API reference

# Example: Use in agex task primers
@agent.task(calgebra.docs["tutorial"])
def schedule_meeting(...):
    pass
```

This enables agents to access the same documentation humans use. The `readme` helps with package discovery and understanding the library's purpose, while `tutorial` and `api` provide usage guidance at runtime.

## Development Status

This library is currently under development. The core architecture and API design are being finalized.

## License

MIT License - see LICENSE file for details.