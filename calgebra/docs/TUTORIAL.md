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
from calgebra import Timeline

# Fetch intervals between start and end
events = timeline.fetch(start=0, end=10000)

# Or use slice notation (more intuitive!)
events = timeline[0:10000]
```

Timelines are **composable** - you can combine them using operators to create complex queries.

> **Note:** Implementations should yield events sorted by `(start, end)` so that set operations can merge them efficiently.

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

### Difference: `-` (SUBTRACT)

Remove intervals from a timeline:

```python
# Business hours when I'm NOT in meetings
available = workhours - my_calendar

# Get the results
free_time = list(available[start:end])
```

### Complement: `~` (NOT)

Invert a timeline (requires finite bounds):

```python
# All times I'm NOT busy
free = ~my_calendar

# Complement requires finite bounds when slicing
free_intervals = list(free[start:end])
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
from calgebra import Timeline, Interval, hours
from collections.abc import Iterable
from typing import override

# First, create a simple Timeline implementation
class SimpleTimeline(Timeline[Interval]):
    def __init__(self, *events: Interval):
        self.events = sorted(events, key=lambda e: (e.start, e.end))
    
    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Interval]:
        for event in self.events:
            if start is not None and event.end < start:
                continue
            if end is not None and event.start > end:
                break
            yield event

# Define some busy periods (Unix timestamps)
alice_busy = SimpleTimeline(
    Interval(start=1000, end=2000),
    Interval(start=5000, end=6000),
)
bob_busy = SimpleTimeline(
    Interval(start=1500, end=2500),
    Interval(start=7000, end=8000),
)
charlie_busy = SimpleTimeline(
    Interval(start=3000, end=4000),
)

# Compose the query (no data fetched yet!)
busy = alice_busy | bob_busy | charlie_busy
free = ~busy
options = free & (hours >= 1)

# Now fetch the results by slicing (with finite bounds for complement)
meeting_slots = list(options[0:10000])
```

If your timeline produces enriched interval subclasses, override `Timeline._make_complement_interval` so the complement operator keeps that metadata intact.

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

Extract custom fields using `Property`:

```python
from calgebra import Property
from typing import override

class Name(Property[NamedInterval]):
    @override
    def apply(self, event: NamedInterval) -> str:
        return event.name

class Priority(Property[NamedInterval]):
    @override
    def apply(self, event: NamedInterval) -> int:
        return event.priority

# Use in filters
name = Name()
priority = Priority()

high_priority = priority >= 8
is_standup = name == "standup"
```

### Custom Timelines

Implement your own data sources:

```python
from collections.abc import Iterable
from calgebra import Timeline, Interval, flatten
from typing import override

class MyTimeline(Timeline[Interval]):
    def __init__(self, data):
        self.data = data
    
    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Interval]:
        for interval in self.data:
            # Filter to bounds
            if start is not None and interval.end < start:
                continue
            if end is not None and interval.start > end:
                break
            yield interval

# Intersection yields an interval per source, so metadata from each calendar is
# maintained even when spans overlap. Wrap in `flatten` when you need coalesced
# coverage. Flatten yields plain `Interval`s and must be sliced with explicit
# bounds, e.g. `flattened[start:end]`:
coalesced = flatten(calendar_a & calendar_b)
```

### Custom Time Types

Timelines can accept different time bound types:

```python
from datetime import date, datetime, time
from typing import Literal, override

class DatetimeTimeline(Timeline[Event]):
    @override
    def _coerce_bound(
        self,
        bound: date | datetime | None,
        edge: Literal["start", "end"],
    ) -> int | None:
        if bound is None:
            return None
        if isinstance(bound, datetime):
            return int(bound.timestamp())
        if isinstance(bound, date):
            # align to whole-day boundaries
            if edge == "start":
                return int(datetime.combine(bound, time.min).timestamp())
            return int(datetime.combine(bound, time.max).timestamp())
        return super()._coerce_bound(bound, edge)

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Event]:
        # Use integer bounds internally
        ...

# Now you can slice with datetimes!
events = timeline[datetime(2025, 1, 1) : datetime(2025, 12, 31)]
```

> **Tip:** Converting bounds to your canonical time unit (and timezone if needed) is part of the timeline contract. If your implementation stores milliseconds (or buckets like 15-minute slots), normalize the incoming slice bounds inside `_coerce_bound` so callers don’t need to round them manually.

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

### Complement Requires Bounds

```python
free = ~busy

# ❌ This will raise an error (unbounded slice)
results = list(free[:])

# ✅ Always provide finite bounds when slicing complement
results = list(free[start:end])
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

### Flattening and Metrics

```python
from calgebra import flatten, union, intersection
from calgebra.metrics import total_duration, max_duration, min_duration, count_intervals, coverage_ratio

merged = flatten(union(alice_calendar, bob_calendar))
overlaps = intersection(alice_calendar, bob_calendar)

# Aggregate over a window (all helpers live in `calgebra.metrics`)
busy_seconds = total_duration(merged, start, end)
longest_busy = max_duration(merged, start, end)
shortest_busy = min_duration(merged, start, end)
meeting_count = count_intervals(alice_calendar, start, end)
utilization = coverage_ratio(merged, start, end)
```

The helpers clamp to the provided bounds, so partially overlapping intervals report their coverage inside the window.
