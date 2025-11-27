"""Test MemoryTimeline with subclassed Intervals and metadata."""

from dataclasses import dataclass
from datetime import datetime, timezone

from calgebra import Interval
from calgebra.mutable.memory import MemoryTimeline
from calgebra.recurrence import RecurringPattern


@dataclass(frozen=True, kw_only=True)
class CalendarEvent(Interval):
    """Custom interval class with extra metadata."""
    summary: str
    location: str | None = None
    attendees: tuple[str, ...] = ()
    recurring_event_id: str | None = None


def test_single_event_metadata_persistence():
    """Test that metadata is preserved for single events."""
    mem = MemoryTimeline()

    event = CalendarEvent(
        start=1000,
        end=2000,
        summary="Team Meeting",
        location="Room A",
        attendees=("alice@example.com", "bob@example.com")
    )

    mem.add(event)

    # Fetch and verify
    results = list(mem[0:3000])
    assert len(results) == 1
    fetched = results[0]

    assert isinstance(fetched, CalendarEvent)
    assert fetched.summary == "Team Meeting"
    assert fetched.location == "Room A"
    assert fetched.attendees == ("alice@example.com", "bob@example.com")


def test_recurring_event_metadata_persistence():
    """Test that metadata is preserved for recurring events."""
    mem = MemoryTimeline()

    # Add recurring pattern with metadata
    pattern = RecurringPattern(
        freq="weekly",
        day="monday",
        interval_class=CalendarEvent,
        summary="Weekly Standup",
        location="Zoom",
        attendees=("team@example.com",)
    )

    mem.add(pattern)

    # Fetch a few instances
    jan_start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    jan_end = int(datetime(2025, 2, 1, tzinfo=timezone.utc).timestamp())

    results = list(mem[jan_start:jan_end])
    assert len(results) > 0

    for event in results:
        assert isinstance(event, CalendarEvent)
        assert event.summary == "Weekly Standup"
        assert event.location == "Zoom"
        assert event.attendees == ("team@example.com",)
        # Should have auto-generated recurring_event_id
        assert event.recurring_event_id is not None


def test_remove_single_event_with_metadata():
    """Test removing a specific single event with metadata."""
    mem = MemoryTimeline()

    ev1 = CalendarEvent(start=100, end=200, summary="Event 1")
    ev2 = CalendarEvent(
        start=100, end=200, summary="Event 2"
    )  # Same time, diff summary

    mem.add(ev1)
    mem.add(ev2)

    assert len(list(mem[0:300])) == 2

    # Remove ev1 specifically
    mem.remove(ev1)

    remaining = list(mem[0:300])
    assert len(remaining) == 1
    assert remaining[0].summary == "Event 2"


def test_remove_recurring_series_with_metadata():
    """Test removing a recurring series using an instance with metadata."""
    mem = MemoryTimeline()

    # Add two overlapping recurring series
    p1 = RecurringPattern(
        freq="weekly", day="monday",
        interval_class=CalendarEvent, summary="Series 1"
    )
    p2 = RecurringPattern(
        freq="weekly", day="monday",
        interval_class=CalendarEvent, summary="Series 2"
    )

    mem.add(p1)
    mem.add(p2)

    # Fetch instances
    jan_start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    jan_end = int(datetime(2025, 2, 1, tzinfo=timezone.utc).timestamp())

    events = list(mem[jan_start:jan_end])
    # Should have mixed events
    assert any(e.summary == "Series 1" for e in events)
    assert any(e.summary == "Series 2" for e in events)

    # Find an instance of Series 1
    s1_instance = next(e for e in events if e.summary == "Series 1")

    # Remove Series 1
    mem.remove_series(s1_instance)

    # Verify only Series 2 remains
    remaining = list(mem[jan_start:jan_end])
    assert all(e.summary == "Series 2" for e in remaining)
    assert len(remaining) > 0


def test_metadata_override_on_add():
    """Test overriding metadata when adding to timeline."""
    mem = MemoryTimeline()

    # Add with override
    event = CalendarEvent(start=100, end=200, summary="Original")
    mem.add(event, summary="Overridden", location="New")

    fetched = list(mem[0:300])[0]
    assert fetched.summary == "Overridden"
    assert fetched.location == "New"
