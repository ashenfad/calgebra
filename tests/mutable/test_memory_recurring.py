"""Test adding RecurringPattern to MemoryTimeline with metadata."""

from datetime import datetime, timezone

from calgebra.mutable.memory import MemoryTimeline


def test_add_recurring_pattern_to_memory():
    """Test adding a RecurringPattern to MemoryTimeline."""
    from calgebra.recurrence import RecurringPattern
    
    mem = MemoryTimeline()

    # Create RecurringPattern directly (not via recurring() which wraps it)
    mondays = RecurringPattern(freq="weekly", day="monday", tz="UTC")

    # Add (metadata would apply if using Event subclass with summary field)
    results = list(mem.add(mondays))

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
    pattern = RecurringPattern(
        freq="weekly",
        day="monday",
        interval_class=Event,
        summary="Original"
    )
    
    # Add with override
    results = list(mem.add(pattern, summary="Overridden"))
    
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


def test_add_timeline_raises_error():
    """Test that adding non-RecurringPattern Timeline raises helpful error."""
    from calgebra import timeline, Interval
    import pytest
    
    mem = MemoryTimeline()
    
    # Create a non-recurring timeline
    tl = timeline(Interval(start=100, end=200))
    
    # Should raise ValueError
    with pytest.raises(ValueError, match="Cannot add Timeline directly"):
        list(mem.add(tl | tl, summary="test"))  # Union is not RecurringPattern
