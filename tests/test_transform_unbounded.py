"""Tests for transform operations with unbounded intervals."""

from calgebra import Interval, buffer, merge_within, timeline
from calgebra.util import HOUR, MINUTE


def test_buffer_with_unbounded_past():
    """Test that buffer handles unbounded past intervals."""
    tl = timeline(Interval(start=None, end=1000))

    # Buffering unbounded past should keep start as None
    buffered = buffer(tl, before=100, after=100)
    result = list(buffered[0:2000])

    assert len(result) == 1
    assert result[0].start is None  # Still unbounded
    assert result[0].end == 1100  # End gets buffered


def test_buffer_with_unbounded_future():
    """Test that buffer handles unbounded future intervals."""
    tl = timeline(Interval(start=1000, end=None))

    # Buffering unbounded future should keep end as None
    buffered = buffer(tl, before=100, after=100)
    result = list(buffered[0:2000])

    assert len(result) == 1
    assert result[0].start == 900  # Start gets buffered
    assert result[0].end is None  # Still unbounded


def test_buffer_with_all_time():
    """Test that buffer handles fully unbounded intervals."""
    tl = timeline(Interval(start=None, end=None))

    # Buffering all time keeps it unbounded
    buffered = buffer(tl, before=100, after=100)
    result = list(buffered[0:2000])

    assert len(result) == 1
    assert result[0].start is None
    assert result[0].end is None


def test_buffer_mixed_bounded_unbounded():
    """Test that buffer handles mix of bounded and unbounded intervals."""
    tl = timeline(
        Interval(start=None, end=1000),
        Interval(start=2000, end=3000),
        Interval(start=5000, end=None),
    )

    buffered = buffer(tl, before=100, after=100)
    result = list(buffered[0:10000])

    assert len(result) == 3
    # First interval: unbounded past
    assert result[0].start is None
    assert result[0].end == 1100
    # Second interval: bounded
    assert result[1].start == 1900
    assert result[1].end == 3100
    # Third interval: unbounded future
    assert result[2].start == 4900
    assert result[2].end is None


def test_merge_within_merges_unbounded_with_bounded():
    """Test that merge_within can merge unbounded with bounded if gap is small."""
    tl = timeline(
        Interval(start=None, end=1000),
        Interval(start=1100, end=2000),  # Gap of 99 seconds
    )

    # Gap is 99 seconds, which is <= 1000, so they merge
    merged = merge_within(tl, gap=1000)
    result = list(merged[0:3000])

    assert len(result) == 1
    assert result[0].start is None  # Preserves unbounded start
    assert result[0].end == 2000  # Extends to end of second interval


def test_merge_within_unbounded_future():
    """Test merge_within with unbounded future intervals."""
    tl = timeline(
        Interval(start=1000, end=2000),
        Interval(start=2100, end=None),  # Gap of 99 seconds, unbounded end
    )

    # Gap is 99 seconds, which is <= 1000, so they merge
    merged = merge_within(tl, gap=1000)
    result = list(merged[0:3000])

    assert len(result) == 1
    assert result[0].start == 1000  # Preserves bounded start
    assert result[0].end is None  # Extends to unbounded end


def test_merge_within_preserves_bounded_merging():
    """Test that merge_within still works for bounded intervals."""
    tl = timeline(
        Interval(start=1000, end=2000),
        Interval(start=2050, end=3000),  # Within gap
    )

    merged = merge_within(tl, gap=100)
    result = list(merged[0:4000])

    # Should merge
    assert len(result) == 1
    assert result[0] == Interval(start=1000, end=3000)
