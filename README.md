# calgebra 🗓️

Set algebra for calendars. Compose lazily and query efficiently.

## Installation

```bash
pip install calgebra

# Or with Google Calendar support
pip install calgebra[google-calendar]

# Or with iCalendar (.ics) file support
pip install calgebra[ical]
```

## Quick Start

```python
from calgebra import day_of_week, time_of_day, at_tz, pprint, hours, HOUR
from itertools import islice

tz = "US/Pacific"
at = at_tz(tz)

# Team calendars
alice, bob, charlie = ...  # Timeline objects (Google Calendar, .ics files, etc.)

# Define when work happens
weekend = day_of_week(["saturday", "sunday"], tz=tz)
weekdays = ~weekend
workhours = time_of_day(start=9*HOUR, duration=8*HOUR, tz=tz)
business_hours = weekdays & workhours

# When is anyone busy?
team_busy = alice | bob | charlie

# Free slots: business hours minus busy, at least 2 hours
free_slots = (business_hours - team_busy) & (hours >= 2)

# Query January 2025
pprint(islice(free_slots[at("2025-01-01"):at("2025-02-01")], 5), tz=tz)
# 2025-01-06 14:00:00 -> 2025-01-06 17:00:00
# 2025-01-08 09:00:00 -> 2025-01-08 12:00:00
# ...
```

**Core Features:**
- **Set operations**: `|` (union), `&` (intersection), `-` (difference), `~` (complement)
- **Lazy composition**: Build complex queries, execute with slicing
- **Recurring patterns**: `day_of_week()`, `time_of_day()`, `recurring()` (RFC 5545)
- **Interval filtering**: `hours >= 2`, `summary == "standup"`, custom properties
- **Google Calendar**: Read/write via `calgebra.gcsa`
- **iCalendar (.ics)**: Load/save standard RFC 5545 files

**→** **[Quick-start](docs/QUICK-START.md)** | **[Tutorial](docs/TUTORIAL.md)** | **[API Reference](docs/API.md)** | **[Google Calendar](docs/GCSA.md)** | **[Demo Video](https://youtu.be/10kG4tw0D4k)**


## License

MIT License - see LICENSE file for details.