# calgebra Tutorial

**calgebra** is a tiny DSL for working with calendar-like intervals using algebraic operations. Think of it as set theory for time ranges.

## Core Concepts

### Intervals

An `Interval` represents a time range with a `start` and `end` (both integers, typically Unix timestamps):

```python
from calgebra import Interval

meeting = Interval(start=1000, end=2000)
```

Intervals are inclusive of both bounds. In the example above, the interval covers the entire range from `1000` through `2000`, which means durations count every second in that span.

### Timelines

A `Timeline` is a source of intervals. It's like a lazy stream that can fetch intervals within a time range:

```python
from datetime import datetime, timezone
from calgebra import Timeline

# Fetch intervals between start and end using integer timestamps
events = timeline.fetch(start=0, end=10000)

# Or use slice notation (more intuitive!)
events = timeline[0:10000]

# Timelines also accept datetime and date objects
start = datetime(2025, 1, 1, tzinfo=timezone.utc)
end = datetime(2025, 12, 31, tzinfo=timezone.utc)
events = timeline[start:end]
```

Timelines are **composable** - you can combine them using operators to create complex queries.

> **Note:** Implementations should yield events sorted by `(start, end)` so that set operations can merge them efficiently.

### Slicing Timelines

The most ergonomic way to slice timelines is using `at_tz()` with date strings:

```python
from calgebra import at_tz

# Create a timezone-aware datetime factory
at = at_tz("US/Pacific")

# Query with simple date strings
events = timeline[at("2025-01-01"):at("2025-12-31")]

# Also works with datetime strings
events = timeline[at("2025-01-01T09:00:00"):at("2025-01-01T17:00:00")]

# Or with components
events = timeline[at(2025, 1, 1):at(2025, 12, 31)]
```

**Alternative methods** (more verbose but sometimes needed):

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Explicit timezone-aware datetime objects
utc_events = timeline[
    datetime(2025, 1, 1, tzinfo=timezone.utc):
    datetime(2025, 12, 31, tzinfo=timezone.utc)
]

pacific_events = timeline[
    datetime(2025, 1, 1, tzinfo=ZoneInfo("US/Pacific")):
    datetime(2025, 12, 31, tzinfo=ZoneInfo("US/Pacific"))
]

# Integer timestamps (Unix seconds) for low-level use
events = timeline[1735689600:1767225600]
```

**Important**: All datetime objects **must be timezone-aware**. Naive datetimes (without timezone info) will raise an error:

```python
# ❌ This will raise TypeError
timeline[datetime(2025, 1, 1):datetime(2025, 12, 31)]

# ✅ Use at_tz() or add timezone info explicitly
at = at_tz("UTC")
timeline[at("2025-01-01"):at("2025-12-31")]
```

### More `at_tz()` Examples

The `at_tz()` helper accepts multiple input formats:

```python
from calgebra import at_tz

at = at_tz("US/Pacific")

# Date strings → midnight in timezone
at("2024-01-01")  # datetime(2024, 1, 1, 0, 0, tzinfo=ZoneInfo('US/Pacific'))

# Datetime strings → specific time
at("2024-01-01T15:30:00")  # 3:30 PM Pacific
at("2024-01-01T15:30:45")  # With seconds

# Components → build datetime
at(2024, 1, 1)              # Midnight
at(2024, 1, 1, 15, 30)      # 3:30 PM
at(2024, 1, 1, 15, 30, 45)  # With seconds

# Mix timezones if needed
eastern = at_tz("US/Eastern")
timeline[at("2024-01-01"):eastern("2024-12-31")]
```

This pattern is especially useful for interactive queries and scripts where you're working in a consistent timezone.

### Automatic Clipping

**Important behavior**: Intervals are automatically clipped to your query bounds. When you slice `timeline[start:end]`, any intervals extending beyond those bounds are trimmed to fit within the query range:

```python
from calgebra import timeline, Interval

# Create a timeline with an interval that extends past our query
t = timeline([Interval(start=100, end=500)])

# Query for [0:300] - the interval will be clipped
result = list(t[0:300])
# Result: [Interval(start=100, end=300)]  # Clipped to query end
```

This automatic clipping ensures:
- **Accurate aggregations**: `total_duration()` reflects only the portion within your query window
- **Consistent set operations**: Intersection, union, and difference work correctly within bounds
- **Predictable behavior**: You always get intervals that fit your query range

This behavior applies to all timelines, including recurring patterns, transformations, and set operations.

### Filters

A `Filter` is a predicate that tests whether an interval meets some condition. Filters are created using `Property` comparisons:

```python
from calgebra import hours

# Filter for intervals >= 2 hours long
long_meetings = hours >= 2
```

### Properties

A `Property` extracts a value from an interval. Built-in properties include:

- `seconds` - duration in seconds
- `minutes` - duration in minutes  
- `hours` - duration in hours
- `days` - duration in days

You can compare properties to create filters:

```python
from calgebra import minutes, hours

short = minutes < 30
medium = (minutes >= 30) & (hours < 2)
long = hours >= 2
```

## The DSL: Operators

calgebra uses Python operators to compose timelines and filters:

### Union: `|` (OR)

Combine intervals from multiple sources:

```python
# Compose timelines first
all_busy = alice_calendar | bob_calendar

# Then slice to get results
events = list(all_busy[start:end])
```

### Intersection: `&` (AND)

Find overlapping intervals:

```python
# Times when BOTH teams are busy
both_busy = calendar_a & calendar_b

# Fetch results
overlaps = list(both_busy[start:end])
```

**Note**: Intersection behavior is smart about when to yield multiple intervals per overlap vs. a single coalesced interval, based on whether the timelines contain metadata. See [Auto-Flattening and When to Use `flatten()`](#auto-flattening-and-when-to-use-flatten) for details.

### Difference: `-` (SUBTRACT)

Remove intervals from a timeline:

```python
# Business hours when I'm NOT in meetings
available = workhours - my_calendar

# Get the results
free_time = list(available[start:end])
```

### Complement: `~` (NOT)

Invert a timeline to find gaps:

```python
# All times I'm NOT busy
free = ~my_calendar

# Can slice with any bounds (even unbounded!)
free_intervals = list(free[start:end])

# Works with unbounded queries too
all_free_time = list(free[None:None])
```

### Filtering: `&` with Filters

Apply predicates to intervals:

```python
from calgebra import hours

# Only meetings >= 2 hours
long_meetings = calendar & (hours >= 2)

# Filters work on either side
also_long = (hours >= 2) & calendar

# Get the results
events = list(long_meetings[start:end])
```

## Working Example: Finding Meeting Times

Here's a realistic example - finding time slots for a team meeting:

```python
from calgebra import timeline, Interval, hours

# Define some busy periods (Unix timestamps)
alice_busy = timeline(
    Interval(start=1000, end=2000),
    Interval(start=5000, end=6000),
)
bob_busy = timeline(
    Interval(start=1500, end=2500),
    Interval(start=7000, end=8000),
)
charlie_busy = timeline(
    Interval(start=3000, end=4000),
)

# Compose the query (no data fetched yet!)
busy = alice_busy | bob_busy | charlie_busy
free = ~busy
options = free & (hours >= 1)

# Now fetch the results by slicing
meeting_slots = list(options[0:10000])
```

**Note**: Complement (`~`) always yields mask `Interval` objects representing gaps, regardless of the source timeline's interval type. Gaps are the absence of events and have no metadata. Complement can now work with unbounded queries (start/end can be `None`).

## Recurring Patterns

calgebra provides powerful recurrence pattern support via `recurring()`, backed by `python-dateutil`'s RFC 5545 implementation. For common cases, convenience wrappers make simple patterns ergonomic.

### Convenience Wrappers for Common Patterns

**`day_of_week(days, tz)`** - Filter by day(s) of the week (wrapper around `recurring(freq="weekly", day=...)`)  
**`time_of_day(start, duration, tz)`** - Filter by time window (wrapper around `recurring(freq="daily", ...)`)

These are great starting points for everyday patterns:

### Basic Usage

```python
from calgebra import day_of_week, time_of_day, HOUR, MINUTE

# All Mondays
mondays = day_of_week("monday", tz="US/Pacific")

# Weekdays (Monday-Friday)
weekdays = day_of_week(
    ["monday", "tuesday", "wednesday", "thursday", "friday"],
    tz="US/Pacific"
)

# Weekends
weekends = day_of_week(["saturday", "sunday"], tz="UTC")

# 9am-5pm every day (8 hours)
daytime = time_of_day(start=9*HOUR, duration=8*HOUR, tz="UTC")

# 9:30am-10am (30 minutes)
standup_time = time_of_day(start=9*HOUR + 30*MINUTE, duration=30*MINUTE, tz="US/Pacific")
```

### Composing: Business Hours

Combine day-of-week and time-of-day to create business hours:

```python
from calgebra import day_of_week, time_of_day, HOUR

# Business hours = weekdays AND 9-5
weekdays = day_of_week(
    ["monday", "tuesday", "wednesday", "thursday", "friday"],
    tz="US/Pacific"
)
work_hours = time_of_day(start=9*HOUR, duration=8*HOUR, tz="US/Pacific")
business_hours = weekdays & work_hours

# Find free time during work hours
free = business_hours - my_calendar
free_slots = list(free[monday:friday])
```

### Composing: Recurring Meetings

Create specific recurring meeting patterns:

```python
from calgebra import day_of_week, time_of_day, HOUR, MINUTE

# Monday standup: every Monday at 9:30am for 30 minutes
mondays = day_of_week("monday", tz="US/Pacific")
standup_time = time_of_day(start=9*HOUR + 30*MINUTE, duration=30*MINUTE, tz="US/Pacific")
monday_standup = mondays & standup_time

# Tuesday/Thursday office hours: 2-4pm
tue_thu = day_of_week(["tuesday", "thursday"], tz="US/Pacific")
afternoon = time_of_day(start=14*HOUR, duration=2*HOUR, tz="US/Pacific")
office_hours = tue_thu & afternoon

# Find conflicts
conflicts = my_calendar & monday_standup
```

### Finding Best Meeting Times

Use composition to evaluate candidate meeting times:

```python
from calgebra import day_of_week, time_of_day, HOUR, MINUTE
from calgebra.metrics import total_duration

# Team busy time
team_busy = alice_cal | bob_cal | charlie_cal

# Candidate standup times
candidates = {
    "Mon 9am": day_of_week("monday") & time_of_day(start=9*HOUR, duration=30*MINUTE),
    "Tue 10am": day_of_week("tuesday") & time_of_day(start=10*HOUR, duration=30*MINUTE),
    "Wed 2pm": day_of_week("wednesday") & time_of_day(start=14*HOUR, duration=30*MINUTE),
}

# Find option with least conflicts
for name, option in candidates.items():
    conflicts = option & team_busy
    conflict_time = total_duration(conflicts, q_start, q_end)
    print(f"{name}: {conflict_time}s of conflicts")
```

### Timezone Handling

All time window helpers are timezone-aware:

```python
from calgebra import day_of_week, time_of_day, HOUR

# Different timezones for different queries
weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday"]
pacific_hours = (
    day_of_week(weekdays, tz="US/Pacific")
    & time_of_day(start=9*HOUR, duration=8*HOUR, tz="US/Pacific")
)
london_hours = (
    day_of_week(weekdays, tz="Europe/London")
    & time_of_day(start=9*HOUR, duration=8*HOUR, tz="Europe/London")
)

# Find overlap between Pacific and London work hours
overlap = pacific_hours & london_hours
shared_hours = list(overlap[start:end])
```

### Advanced Patterns with `recurring()`

For patterns beyond simple weekly/daily filtering, use `recurring()` directly:

```python
from calgebra import recurring, HOUR, MINUTE

# Bi-weekly meetings (every other Monday)
biweekly_standup = recurring(
    freq="weekly",
    interval=2,  # Every 2 weeks
    day="monday",
    start=9*HOUR + 30*MINUTE,
    duration=30*MINUTE,
    tz="US/Pacific"
)

# First Monday of each month (monthly all-hands)
monthly_allhands = recurring(
    freq="monthly",
    week=1,  # First occurrence
    day="monday",
    start=10*HOUR,
    duration=HOUR,
    tz="UTC"
)

# Last Friday of each month (team social)
end_of_month_social = recurring(
    freq="monthly",
    week=-1,  # Last occurrence
    day="friday",
    start=17*HOUR,
    duration=2*HOUR,
    tz="US/Pacific"
)

# 1st and 15th of every month (payroll processing - full day)
payroll_days = recurring(
    freq="monthly",
    day_of_month=[1, 15],
    tz="UTC"
)

# Quarterly board meetings (first Monday of Jan, Apr, Jul, Oct)
board_meetings = recurring(
    freq="monthly",
    interval=3,  # Every 3 months
    week=1,
    day="monday",
    start=14*HOUR,
    duration=3*HOUR,
    tz="US/Pacific"
)

# Annual events (using yearly frequency)
# Company anniversary party: June 15th at 5pm for 3 hours
annual_party = recurring(
    freq="yearly",
    month=6,
    day_of_month=15,
    start=17*HOUR,
    duration=3*HOUR,
    tz="US/Pacific"
)

# Tax deadlines: April 15th each year
tax_deadline = recurring(
    freq="yearly",
    month=4,
    day_of_month=15,
    tz="UTC"
)

# Multiple annual events: quarterly on specific dates
quarterly_reviews = recurring(
    freq="yearly",
    month=[1, 4, 7, 10],  # Jan, Apr, Jul, Oct
    day_of_month=1,
    start=9*HOUR,
    duration=2*HOUR,
    tz="UTC"
)
```

The `recurring()` function supports:
- **freq**: `"daily"`, `"weekly"`, `"monthly"`, `"yearly"`
- **interval**: Repeat every N units (e.g., `interval=2` for bi-weekly)
- **day**: Day name(s) for weekly/monthly patterns (`"monday"`, `["tuesday", "thursday"]`)
- **week**: Nth occurrence for monthly patterns (`1`=first, `-1`=last, `2`=second, etc.)
- **day_of_month**: Specific day(s) of month (`1`-`31`, or `-1` for last day)
- **month**: Specific month(s) for yearly patterns (`1`-`12`)
- **start** / **duration**: Time window within each occurrence in seconds (use `HOUR`, `MINUTE` constants)
- **tz**: IANA timezone name

## Transformations

Transformations modify the shape or structure of intervals while preserving their identity and metadata.

### Adding Buffer Time with `buffer()`

Add time before and/or after each interval—useful for travel time, setup/teardown, or slack time:

```python
from calgebra import buffer, HOUR, MINUTE

# Add 2 hours before flights for travel and security
blocked_time = buffer(flights, before=2*HOUR)

# Add 15 minutes of buffer on both sides of meetings
busy_time = buffer(meetings, before=15*MINUTE, after=15*MINUTE)

# Check for conflicts with expanded times
conflicts = blocked_time & other_calendar
```

### Merging Nearby Intervals with `merge_within()`

Coalesce intervals that are close together in time—useful for clustering related events or grouping alarms into incidents:

```python
from calgebra import merge_within, MINUTE

# Treat alarms within 15 minutes as one incident
incidents = merge_within(alarms, gap=15*MINUTE)

# Group meetings scheduled within 5 minutes into busy blocks
busy_blocks = merge_within(meetings, gap=5*MINUTE)

# Filter to specific day
monday_incidents = incidents & day_of_week("monday")
```

**Key Difference from `flatten()`:**
- `merge_within(gap=X)`: Merges intervals separated by **at most** `X` seconds, preserving metadata from the first interval in each group
- `flatten()`: Merges **all** adjacent or overlapping intervals (gap=0), creating new minimal `Interval` objects without custom metadata

Use `merge_within()` when you need to preserve event metadata and control the merge threshold. Use `flatten()` for simple coalescing.

### Composing Transformations

Transformations are composable with all other operations:

```python
from calgebra import buffer, merge_within, day_of_week, HOUR, MINUTE

# Complex workflow: buffer events, merge nearby ones, then intersect
buffered_events = buffer(events, before=30*MINUTE, after=15*MINUTE)
incident_groups = merge_within(buffered_events, gap=10*MINUTE)
weekday_incidents = incident_groups & day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"])
```

## Extending calgebra

### Custom Intervals

Intervals are cloned internally (for intersection, difference, metrics, etc.) using
`dataclasses.replace`, so your subclasses **must** be dataclasses (and freezing them
is recommended to match the core type). Add your own fields by subclassing
`Interval`:

```python
from dataclasses import dataclass
from calgebra import Interval

@dataclass(frozen=True, kw_only=True)
class NamedInterval(Interval):
    name: str
    priority: int
```

### Custom Properties

For simple field access, use the `field()` helper:

```python
from calgebra import field, one_of

# Quick field access by name
priority = field('priority')
name = field('name')

high_priority = priority >= 8
is_standup = name == "standup"

# Or use lambdas for type safety and IDE support
priority = field(lambda e: e.priority)
urgent = timeline & (priority >= 8)

# Computed properties work too
tag_count = field(lambda e: len(e.tags))
multi_tagged = timeline & (tag_count >= 2)
```

For collection fields (sets, lists, tuples), use `has_any()` or `has_all()`:

```python
from calgebra import field, has_any, has_all

# Match events with ANY of the specified tags
tags = field('tags')  # tags: set[str]
work_events = timeline & has_any(tags, {"work", "urgent"})

# Match events with ALL of the specified tags
critical_work = timeline & has_all(tags, {"work", "urgent"})

# Works with lists too
labels = field('labels')  # labels: list[str]
todo_items = timeline & has_any(labels, {"todo", "important"})
```

**Note:** Use `one_of()` for scalar fields (strings, ints), and `has_any()`/`has_all()` for collection fields (sets, lists, tuples).

For more complex logic, subclass `Property` directly:

```python
from calgebra import Property
from typing import override

class IsUrgent(Property[NamedInterval]):
    @override
    def apply(self, event: NamedInterval) -> bool:
        return event.priority >= 8 and "urgent" in event.tags

urgent = timeline & IsUrgent()
```

### Custom Timelines

For simple static collections of intervals, use the `timeline()` helper:

```python
from calgebra import timeline, Interval

# Quick and easy - no subclassing needed
my_events = timeline(
    Interval(start=1000, end=2000),
    Interval(start=5000, end=6000),
)
```

For more complex data sources (databases, APIs, generators), implement your own:

```python
from collections.abc import Iterable
from calgebra import Timeline, Interval, flatten, time_of_day, HOUR
from typing import override

class DatabaseTimeline(Timeline[Interval]):
    def __init__(self, db_connection):
        self.db = db_connection
    
    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Interval]:
        # Query database with bounds
        query = "SELECT start, end FROM events WHERE ..."
        for row in self.db.execute(query, (start, end)):
            yield Interval(start=row['start'], end=row['end'])

# When both timelines have metadata, use `flatten` for single coalesced spans:
coalesced = flatten(calendar_a & calendar_b)

# Intersecting with mask recurring patterns automatically preserves metadata:
work_events = calendar_a & time_of_day(start=9*HOUR, duration=8*HOUR)

# See "Auto-Flattening and When to Use flatten()" section for details
```

## Advanced Patterns

### Combining Multiple Filters

```python
from calgebra import hours, one_of

# Multiple conditions
work_meetings = (
    my_calendar
    & (hours >= 1) 
    & (hours <= 2) 
    & one_of(category, {"work", "planning"})
)

results = list(work_meetings[start:end])
```

### Multi-way Operations

```python
# Union accepts multiple sources
all_team = calendar_a | calendar_b | calendar_c | calendar_d

# Intersection too
all_free = ~calendar_a & ~calendar_b & ~calendar_c
```

### Chaining Operations

```python
# Build complex queries step by step
candidate_times = (
    workhours                  # Start with business hours
    - (team_a | team_b)        # Remove when anyone is busy  
    & (hours >= 1.5)           # Must be at least 90 minutes
    & (hours <= 3)             # But not longer than 3 hours
)

# Execute the query
results = list(candidate_times[start:end])
```

## Tips & Tricks

### Use Property Comparisons

All standard comparison operators work:
- `==`, `!=` - equality
- `<`, `<=`, `>`, `>=` - ordering
- `one_of(property, values)` - membership

### Filters vs Timelines

- **Filters** test conditions: `hours >= 2`
- **Timelines** provide intervals: `my_calendar[start:end]`
- You can `&` them together but not `|` them (type error!)
- `Filter` is exported for type hints but you create filters via property comparisons

### Unbounded Intervals

Intervals can now have `None` for start or end to represent infinity:

```python
# Everything after a certain point
future = Interval(start=cutoff_time, end=None)

# Everything before a certain point  
past = Interval(start=None, end=cutoff_time)

# All time
all_time = Interval(start=None, end=None)

# Complement can work with unbounded queries
free = ~busy
all_free_time = list(free[None:None])  # Works!

# Compose freely - bounds can come from other timelines
available = (~busy) & business_hours
slots = list(available[:])  # Bounded by business_hours
```

### Composition is Lazy, Slicing Executes

```python
# Build up the query - no data fetched yet!
query = (calendar_a | calendar_b) & (hours >= 2)

# Slicing executes the query and returns an iterable
results = list(query[start:end])

# You can't operate on sliced results
# ❌ Wrong: events = query[start:end] | other[start:end]
# ✅ Right: combined = query | other; events = list(combined[start:end])
```

### Auto-Flattening and When to Use `flatten()`

calgebra automatically optimizes intersections based on whether timelines contain mask intervals (like recurring patterns) or metadata-rich events:

**Automatic Flattening** (no `flatten()` needed):
```python
from calgebra import day_of_week, time_of_day, HOUR

# Mask & Mask → Auto-flattened (1 interval per overlap)
weekdays = day_of_week(["monday", "tuesday", "wednesday", "thursday", "friday"])
business_hours = weekdays & time_of_day(start=9*HOUR, duration=8*HOUR)

# Rich & Mask → Preserves rich metadata (only yields from rich source)
work_meetings = my_calendar & time_of_day(start=9*HOUR, duration=8*HOUR)
```

**When You Still Need `flatten()`**:
```python
from calgebra import flatten

# 1. Coalescing union results for display
all_busy = flatten(alice_cal | bob_cal | charlie_cal)

# 2. Converting metadata-rich intervals to mask intervals
simple_coverage = flatten(enriched_calendar)

# 3. When both sources have metadata and you want single coalesced spans
combined = flatten(calendar_a & calendar_b)  # Without flatten: yields 2 intervals per overlap
```

**Metrics** automatically flatten when needed:
```python
from calgebra.metrics import total_duration, max_duration, min_duration, count_intervals, coverage_ratio

merged = alice_calendar | bob_calendar

# All helpers flatten internally where needed
busy_seconds = total_duration(merged, start, end)
longest_busy = max_duration(merged, start, end)
shortest_busy = min_duration(merged, start, end)
meeting_count = count_intervals(alice_calendar, start, end)
utilization = coverage_ratio(merged, start, end)
```

The helpers clamp to the provided bounds, so partially overlapping intervals report their coverage inside the window.
