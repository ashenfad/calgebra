"""Tests for transform operations with unbounded intervals."""

import pytest

from calgebra import Interval, buffer, merge_within, timeline


def test_buffer_with_unbounded_past():
    """Test that buffer handles unbounded past intervals."""
    tl = timeline(Interval(start=None, end=1000))

    # Buffering unbounded past, then querying with finite bounds clips to query bounds
    buffered = buffer(tl, before=100, after=100)
    result = list(buffered[0:2000])

    assert len(result) == 1
    assert result[0].start == 0  # Clipped to query start
    assert result[0].end == 1100  # End gets buffered


def test_buffer_with_unbounded_future():
    """Test that buffer handles unbounded future intervals."""
    tl = timeline(Interval(start=1000, end=None))

    # Buffering unbounded future, then querying with finite bounds clips to query bounds
    buffered = buffer(tl, before=100, after=100)
    result = list(buffered[0:2000])

    assert len(result) == 1
    assert result[0].start == 900  # Start gets buffered
    assert result[0].end == 2000  # Clipped to query end


def test_buffer_with_all_time():
    """Test that buffer handles fully unbounded intervals."""
    tl = timeline(Interval(start=None, end=None))

    # Buffering all time, then querying with finite bounds clips to query bounds
    buffered = buffer(tl, before=100, after=100)
    result = list(buffered[0:2000])

    assert len(result) == 1
    assert result[0].start == 0  # Clipped to query start
    assert result[0].end == 2000  # Clipped to query end


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
    # First interval: unbounded past, clipped to query start
    assert result[0].start == 0  # Clipped to query start
    assert result[0].end == 1100
    # Second interval: bounded
    assert result[1].start == 1900
    assert result[1].end == 3100
    # Third interval: unbounded future, clipped to query end
    assert result[2].start == 4900
    assert result[2].end == 10000  # Clipped to query end


def test_merge_within_merges_unbounded_with_bounded():
    """Test that merge_within can merge unbounded with bounded if gap is small."""
    tl = timeline(
        Interval(start=None, end=1000),
        Interval(start=1100, end=2000),  # Gap of 99 seconds
    )

    # Gap is 99 seconds, which is <= 1000, so they merge
    # Query with finite bounds clips to query bounds
    merged = merge_within(tl, gap=1000)
    result = list(merged[0:3000])

    assert len(result) == 1
    assert result[0].start == 0  # Clipped to query start
    assert result[0].end == 2000  # Extends to end of second interval


def test_merge_within_unbounded_future():
    """Test merge_within with unbounded future intervals."""
    tl = timeline(
        Interval(start=1000, end=2000),
        Interval(start=2100, end=None),  # Gap of 99 seconds, unbounded end
    )

    # Gap is 99 seconds, which is <= 1000, so they merge
    # Query with finite bounds clips to query bounds
    merged = merge_within(tl, gap=1000)
    result = list(merged[0:3000])

    assert len(result) == 1
    assert result[0].start == 1000  # Preserves bounded start
    assert result[0].end == 3000  # Clipped to query end


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


def test_merge_within_absorbs_finite_inside_unbounded_future():
    """merge_within should absorb finite intervals that lie within an unbounded span."""
    tl = timeline(
        Interval(start=0, end=None),
        Interval(start=100, end=200),
    )

    # The unbounded interval absorbs the bounded one
    # Query with finite bounds clips to query bounds
    merged = merge_within(tl, gap=0)
    result = list(merged[0:500])

    assert result == [Interval(start=0, end=500)]  # Clipped to query end


def test_buffer_rejects_negative_before():
    """Test that buffer raises ValueError for negative before."""
    tl = timeline(Interval(start=1000, end=2000))

    with pytest.raises(ValueError, match="before must be non-negative"):
        buffer(tl, before=-100)


def test_buffer_rejects_negative_after():
    """Test that buffer raises ValueError for negative after."""
    tl = timeline(Interval(start=1000, end=2000))

    with pytest.raises(ValueError, match="after must be non-negative"):
        buffer(tl, after=-100)
