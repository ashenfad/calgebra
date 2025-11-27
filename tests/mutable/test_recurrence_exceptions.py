"""Test recurrence exceptions (removing single instances)."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from calgebra import Interval
from calgebra.mutable.memory import MemoryTimeline
from calgebra.recurrence import RecurringPattern


@dataclass(frozen=True, kw_only=True)
class Event(Interval):
    summary: str = ""
    recurring_event_id: str | None = None


def test_remove_single_recurring_instance():
    """Test removing a single instance of a recurring series."""
    mem = MemoryTimeline()

    # Add weekly pattern
    pattern = RecurringPattern(
        freq="weekly",
        day="monday",
        interval_class=Event,
        summary="Weekly Sync"
    )
    mem.add(pattern)

    # Fetch first 4 instances
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 2, 1, tzinfo=timezone.utc)
    events = list(mem[start:end])

    assert len(events) >= 4
    instance_to_remove = events[1]  # Remove the second one

    # Remove just this instance
    results = mem.remove(instance_to_remove)
    assert results[0].success

    # Verify it's gone but others remain
    events_after = list(mem[start:end])
    assert len(events_after) == len(events) - 1

    # Check that the removed one is missing
    assert instance_to_remove not in events_after

    # Check that others are still there
    assert events[0] in events_after
    assert events[2] in events_after


def test_remove_instance_persists_exdate():
    """Test that exdates persist across fetches."""
    mem = MemoryTimeline()

    pattern = RecurringPattern(
        freq="daily",
        interval_class=Event,
        summary="Daily"
    )
    mem.add(pattern)

    # Fetch today's instance
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    events = list(mem[now:now+timedelta(seconds=100)])
    instance = events[0]

    # Remove it
    mem.remove(instance)

    # Fetch again
    events_after = list(mem[now:now+timedelta(seconds=100)])
    assert len(events_after) == 0

    # Fetch wider range
    events_wider = list(mem[now:now+timedelta(seconds=86400*2)])
    assert len(events_wider) == 1  # Next day should be there


def test_remove_instance_without_id_fails_gracefully():
    """Test removing an instance that looks recurring but has no ID match."""
    mem = MemoryTimeline()

    # Create an event that looks like it belongs to a series but doesn't
    fake_event = Event(
        start=100,
        end=200,
        summary="Fake",
        recurring_event_id="nonexistent"
    )

    # Try to remove
    results = mem.remove(fake_event)

    # Should fail because it's not in static storage AND not in recurring patterns
    assert not results[0].success
    assert "not found" in str(results[0].error).lower()
