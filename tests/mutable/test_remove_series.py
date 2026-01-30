"""Test remove_series functionality for MemoryTimeline."""

from dataclasses import dataclass
from datetime import datetime, timezone

from calgebra import Interval
from calgebra.mutable.memory import MemoryTimeline
from calgebra.recurrence import RecurringPattern


@dataclass(frozen=True, kw_only=True)
class Event(Interval):
    """Event with recurring_event_id support."""

    summary: str = ""
    recurring_event_id: str | None = None


def test_remove_series_with_recurring_event_id():
    """Test removing a recurring series by recurring_event_id."""
    mem = MemoryTimeline()

    # Add a recurring pattern with Event class
    mondays = RecurringPattern(
        freq="weekly", day="monday", interval_class=Event, summary="Weekly Meeting"
    )
    results = mem.add(mondays)
    assert results[0].success

    # Fetch intervals
    jan_start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    jan_end = int(datetime(2025, 2, 1, tzinfo=timezone.utc).timestamp())
    intervals = list(mem[jan_start:jan_end])

    # Should have recurring_event_id
    assert len(intervals) > 0
    assert intervals[0].recurring_event_id is not None
    recurring_id = intervals[0].recurring_event_id

    # All intervals should have the same recurring_event_id
    for ivl in intervals:
        assert ivl.recurring_event_id == recurring_id

    # Remove the series
    remove_results = mem.remove_series(intervals[0])
    assert remove_results[0].success

    # Verify series is gone
    intervals_after = list(mem[jan_start:jan_end])
    assert len(intervals_after) == 0


def test_remove_series_not_found():
    """Test removing a non-existent recurring series."""
    mem = MemoryTimeline()

    # Create interval with fake recurring_event_id
    fake_event = Event(
        start=100, end=200, summary="Fake", recurring_event_id="nonexistent"
    )

    # Try to remove
    results = mem.remove_series(fake_event)
    assert not results[0].success
    assert "not found" in str(results[0].error).lower()


def test_remove_series_fallback_to_single():
    """Test that remove_series falls back to remove_interval for non-recurring
    events.
    """
    mem = MemoryTimeline()

    # Add a single event (no recurring_event_id)
    event = Event(start=100, end=200, summary="One-time")
    mem.add(event)

    # Remove via remove_series (should work like remove_interval)
    results = mem.remove_series(event)
    assert results[0].success

    # Verify it's gone
    intervals = list(mem[0:1000])
    assert len(intervals) == 0
