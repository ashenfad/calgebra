"""Tests for MemoryTimeline."""

from calgebra import Interval
from calgebra.mutable.memory import MemoryTimeline


def test_create_empty_memory_timeline():
    """Test creating an empty MemoryTimeline."""
    mem = MemoryTimeline()

    # Empty fetch
    result = list(mem[0:100])
    assert len(result) == 0


def test_add_single_interval():
    """Test adding a single interval to MemoryTimeline."""
    mem = MemoryTimeline()

    # Add an interval
    results = mem.add(Interval(start=10, end=20))

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].event is not None
    assert results[0].event.start == 10
    assert results[0].event.end == 20


def test_add_and_fetch_interval():
    """Test that added intervals can be fetched."""
    mem = MemoryTimeline()

    # Add interval
    mem.add(Interval(start=10, end=20))

    # Fetch it back
    result = list(mem[0:100])

    assert len(result) == 1
    assert result[0].start == 10
    assert result[0].end == 20


def test_add_multiple_intervals():
    """Test adding multiple intervals."""
    mem = MemoryTimeline()

    # Add three intervals
    intervals = [
        Interval(start=10, end=20),
        Interval(start=30, end=40),
        Interval(start=50, end=60),
    ]
    for interval in intervals:
        mem.add(interval)

    # Fetch them back
    result = list(mem[0:100])

    assert len(result) == 3


def test_add_with_metadata():
    """Test adding intervals with metadata kwargs."""
    from dataclasses import dataclass

    @dataclass(frozen=True, kw_only=True)
    class Event(Interval):
        summary: str = ""

    mem = MemoryTimeline()

    # Add with metadata
    results = mem.add(Event(start=10, end=20), summary="Meeting")

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].event == Event(start=10, end=20, summary="Meeting")


def test_initial_intervals():
    """Test creating MemoryTimeline with initial intervals."""
    intervals = [
        Interval(start=10, end=20),
        Interval(start=30, end=40),
    ]

    mem = MemoryTimeline(intervals)

    # Fetch them back
    result = list(mem[0:100])

    assert len(result) == 2


def test_remove_interval():
    """Test removing an interval by ID."""
    mem = MemoryTimeline()

    # Add interval
    add_results = mem.add(Interval(start=10, end=20))
    added_event = add_results[0].event

    # Verify it's there
    assert len(list(mem[0:100])) == 1

    # Remove it
    remove_results = mem.remove(added_event)

    assert len(remove_results) == 1
    assert remove_results[0].success is True

    # Verify it's gone
    assert len(list(mem[0:100])) == 0


def test_remove_nonexistent_interval():
    """Test that removing non-existent interval returns error."""
    mem = MemoryTimeline()

    # Add interval
    mem.add(Interval(start=10, end=20))

    # Try to remove a different interval (not the one we added)
    fake_interval = Interval(start=30, end=40)
    # It should still work because SortedList uses equality
    results = mem.remove(fake_interval)

    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error is not None


def test_fetch_range_filtering():
    """Test that fetch respects start/end bounds."""
    mem = MemoryTimeline()

    # Add intervals at different times
    mem.add(Interval(start=10, end=20))
    mem.add(Interval(start=50, end=60))
    mem.add(Interval(start=90, end=100))

    # Fetch middle range
    result = list(mem[40:80])

    assert len(result) == 1
    assert result[0].start == 50


def test_memory_timeline_iterator_results():
    """Test that write operations return iterators."""
    mem = MemoryTimeline()

    # add() should return iterator
    add_result = mem.add(Interval(start=10, end=20))
    assert hasattr(add_result, "__iter__")

    # Consume it
    results = list(add_result)
    assert len(results) == 1
