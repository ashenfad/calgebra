"""Google Calendar integration for calgebra.

This module provides a clean public API for Google Calendar operations.
It re-exports the implementation from `calgebra.mutable.gcsa`.

Example:
    >>> from calgebra.gcsa import calendars, Event, Calendar
    >>> from calgebra import at_tz
    >>>
    >>> # Get all accessible calendars
    >>> cals = calendars()
    >>> primary: Calendar = cals[0]
    >>>
    >>> # Read events
    >>> at = at_tz("US/Pacific")
    >>> events = list(primary[at("2025-01-01"):at("2025-01-31")])
    >>>
    >>> # Add an event
    >>> new_event = Event.from_datetimes(
    ...     start=at(2025, 1, 15, 14, 0),
    ...     end=at(2025, 1, 15, 15, 0),
    ...     summary="Team Meeting",
    ...     calendar_id=primary.calendar_id,
    ...     calendar_summary=primary.calendar_summary,
    ... )
    >>> primary.add(new_event)
"""

# Re-export public API from mutable.gcsa
from calgebra.mutable.gcsa import Calendar, Event, Reminder, calendars

__all__ = ["Event", "Calendar", "Reminder", "calendars"]
