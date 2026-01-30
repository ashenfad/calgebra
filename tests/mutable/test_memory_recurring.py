"""Test adding RecurringPattern to MemoryTimeline with metadata."""

from datetime import datetime, timezone

from calgebra.mutable.memory import MemoryTimeline
from calgebra.util import HOUR


def test_add_recurring_pattern_to_memory():
    """Test adding a RecurringPattern to MemoryTimeline."""
    from calgebra.recurrence import RecurringPattern

    mem = MemoryTimeline()

    # Create RecurringPattern directly
    mondays = RecurringPattern(freq="weekly", day="monday", tz="UTC")

    # Add a recurring pattern
    results = mem.add(mondays)

    assert len(results) == 1
    assert results[0].success is True

    # Fetch back - should have recurring pattern stored
    jan_2025_start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    jan_2025_end = int(datetime(2025, 2, 1, tzinfo=timezone.utc).timestamp())

    intervals = list(mem[jan_2025_start:jan_2025_end])

    # Should have 4 or 5 Mondays in January 2025
    assert 4 <= len(intervals) <= 5


def test_add_recurring_pattern_metadata_override():
    """Test that metadata in add() overrides pattern metadata."""
    from dataclasses import dataclass

    from calgebra import Interval
    from calgebra.recurrence import RecurringPattern

    @dataclass(frozen=True, kw_only=True)
    class Event(Interval):
        summary: str = ""

    mem = MemoryTimeline()

    # Create pattern with metadata
    pattern = RecurringPattern(freq="weekly", day="monday", interval_class=Event)

    # Add with metadata override
    results = mem.add(pattern, summary="Overridden")

    assert len(results) == 1
    assert results[0].success is True

    # Fetch and check metadata
    jan_2025_start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    jan_2025_end = int(datetime(2025, 1, 8, tzinfo=timezone.utc).timestamp())

    intervals = list(mem[jan_2025_start:jan_2025_end])

    # Should have at least one Monday
    assert len(intervals) >= 1
    # Metadata should be overridden
    assert intervals[0].summary == "Overridden"


def test_recurring_anchor_preserved_in_memory():
    """RecurringPattern with anchored start keeps its phase after storage."""
    from calgebra.recurrence import RecurringPattern

    mem = MemoryTimeline()

    # Every other Monday starting on 2025-01-06 09:00 UTC
    anchor = datetime(2025, 1, 6, 9, tzinfo=timezone.utc)
    pattern = RecurringPattern(
        freq="weekly",
        interval=2,
        day="monday",
        start=anchor,
        duration=HOUR,
        tz="UTC",
    )

    mem.add(pattern)

    jan_start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    feb_start = int(datetime(2025, 2, 1, tzinfo=timezone.utc).timestamp())

    intervals = list(mem[jan_start:feb_start])
    starts = {ivl.start for ivl in intervals}

    first = int(anchor.timestamp())
    second = first + 14 * 24 * 3600  # every other week

    # Bug: currently loses anchor and yields 1/13 and 1/27 instead of 1/6 and 1/20
    assert first in starts
    assert second in starts


def test_add_timeline_raises_error():
    """Test that adding non-RecurringPattern Timeline raises helpful error."""
    import pytest

    from calgebra import Interval, timeline

    mem = MemoryTimeline()

    # Create a non-recurring timeline
    tl = timeline(Interval(start=1, end=2))

    with pytest.raises(ValueError):
        mem.add(tl | tl, summary="test")  # Union is not RecurringPattern
