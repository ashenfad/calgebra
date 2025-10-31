"""Tests for unbounded interval support (None start/end values)."""

from calgebra import Interval, hours, timeline
from calgebra.interval import NEG_INF, POS_INF


def test_unbounded_interval_creation():
    """Test creating intervals with None bounds."""
    # All time (past to future)
    all_time = Interval(start=None, end=None)
    assert all_time.start is None
    assert all_time.end is None
    assert "unbounded" in str(all_time)

    # Everything before 2000
    past = Interval(start=None, end=2000)
    assert past.start is None
    assert past.end == 2000
    assert "-∞" in str(past)

    # Everything after 1000
    future = Interval(start=1000, end=None)
    assert future.start == 1000
    assert future.end is None
    assert "+∞" in str(future)


def test_unbounded_interval_finite_properties():
    """Test that finite_start/finite_end provide sentinel values."""
    # Unbounded past
    past = Interval(start=None, end=2000)
    assert past.finite_start == NEG_INF
    assert past.finite_end == 2000

    # Unbounded future
    future = Interval(start=1000, end=None)
    assert future.finite_start == 1000
    assert future.finite_end == POS_INF

    # All time
    all_time = Interval(start=None, end=None)
    assert all_time.finite_start == NEG_INF
    assert all_time.finite_end == POS_INF

    # Regular interval unchanged
    regular = Interval(start=1000, end=2000)
    assert regular.finite_start == 1000
    assert regular.finite_end == 2000


def test_complement_with_bounded_query():
    """Test that complement works with bounded queries."""
    # Original behavior: complement with finite bounds
    busy = timeline(
        Interval(start=1000, end=2000),
        Interval(start=5000, end=6000),
    )

    free = ~busy
    gaps = list(free[0:10000])

    # Should get gaps: [0, 999], [2001, 4999], [6001, 10000]
    assert len(gaps) == 3
    assert gaps[0] == Interval(start=0, end=999)
    assert gaps[1] == Interval(start=2001, end=4999)
    assert gaps[2] == Interval(start=6001, end=10000)


def test_complement_with_unbounded_query():
    """Test that complement can now handle unbounded queries."""
    busy = timeline(
        Interval(start=1000, end=2000),
        Interval(start=5000, end=6000),
    )

    free = ~busy

    # Query with no start bound
    future_gaps = list(free[None:10000])
    # Should get: [-∞, 999], [2001, 4999], [6001, 10000]
    assert len(future_gaps) == 3
    assert future_gaps[0].start is None
    assert future_gaps[0].end == 999

    # Query with no end bound
    past_gaps = list(free[0:None])
    # Should get: [0, 999], [2001, 4999], [6001, +∞]
    assert len(past_gaps) == 3
    assert past_gaps[2].start == 6001
    assert past_gaps[2].end is None

    # Query with no bounds at all
    all_gaps = list(free[None:None])
    # Should get: [-∞, 999], [2001, 4999], [6001, +∞]
    assert len(all_gaps) == 3
    assert all_gaps[0].start is None
    assert all_gaps[0].end == 999
    assert all_gaps[2].start == 6001
    assert all_gaps[2].end is None


def test_complement_composition_with_bounded_timeline():
    """Test that complement can compose with bounded timelines."""
    # This is the key use case: complement doesn't require finite bounds
    # if it's intersected with something that provides bounds

    busy = timeline(
        Interval(start=1000, end=2000),
        Interval(start=5000, end=6000),
    )

    # Business hours provides the bounds
    business_hours = timeline(
        Interval(start=0, end=3000),
        Interval(start=4000, end=8000),
    )

    # Free time during business hours
    free = ~busy
    available = free & business_hours

    # Should work even though free is unbounded, because business_hours provides bounds
    slots = list(available[0:10000])

    # Should get the intersection of free time with business hours
    # free: [-∞, 999], [2001, 4999], [6001, +∞]
    # business: [0, 3000], [4000, 8000]
    # intersection: [0, 999], [2001, 3000], [4000, 4999], [6001, 8000]
    assert len(slots) == 4
    assert slots[0] == Interval(start=0, end=999)
    assert slots[1] == Interval(start=2001, end=3000)
    assert slots[2] == Interval(start=4000, end=4999)
    assert slots[3] == Interval(start=6001, end=8000)


def test_unbounded_intervals_with_filters():
    """Test that filters work with unbounded intervals."""
    # Unbounded intervals have infinite duration
    all_time = Interval(start=None, end=None)
    assert hours.apply(all_time) == float("inf")

    past = Interval(start=None, end=2000)
    assert hours.apply(past) == float("inf")

    future = Interval(start=1000, end=None)
    assert hours.apply(future) == float("inf")

    # Regular interval still works
    regular = Interval(start=1000, end=4599)  # 3600 seconds = 1 hour
    assert hours.apply(regular) == 1.0


def test_union_with_unbounded_intervals():
    """Test that union sorts unbounded intervals correctly."""
    bounded = timeline(Interval(start=1000, end=2000))
    unbounded_past = timeline(Interval(start=None, end=500))
    unbounded_future = timeline(Interval(start=5000, end=None))

    # Union should sort correctly using finite_start/finite_end
    # Query with finite bounds clips to query bounds
    combined = bounded | unbounded_past | unbounded_future
    intervals = list(combined[0:10000])

    # Should be sorted: unbounded_past, bounded, unbounded_future
    # All clipped to query bounds
    assert len(intervals) == 3
    assert intervals[0].start == 0  # Clipped to query start
    assert intervals[0].end == 500
    assert intervals[1].start == 1000
    assert intervals[1].end == 2000
    assert intervals[2].start == 5000
    assert intervals[2].end == 10000  # Clipped to query end


def test_intersection_with_unbounded_intervals():
    """Test that intersection handles unbounded intervals correctly."""
    # Unbounded timeline
    all_time = timeline(Interval(start=None, end=None))

    # Bounded timeline
    business_hours = timeline(
        Interval(start=1000, end=2000),
        Interval(start=5000, end=6000),
    )

    # Intersecting unbounded with bounded should yield bounded intervals
    # Note: yields from each source, so 2 intervals per overlap = 4 total
    result = all_time & business_hours
    intervals = list(result[0:10000])

    assert len(intervals) == 4
    # First overlap from all_time, then from business_hours
    assert intervals[0] == Interval(start=1000, end=2000)
    assert intervals[1] == Interval(start=1000, end=2000)
    # Second overlap from all_time, then from business_hours
    assert intervals[2] == Interval(start=5000, end=6000)
    assert intervals[3] == Interval(start=5000, end=6000)


def test_difference_with_unbounded_intervals():
    """Test that difference handles unbounded intervals correctly."""
    # Start with unbounded interval
    all_time = timeline(Interval(start=None, end=None))

    # Subtract bounded intervals
    busy = timeline(
        Interval(start=1000, end=2000),
        Interval(start=5000, end=6000),
    )

    # Difference should carve out the busy times
    # Query with finite bounds clips to query bounds
    free = all_time - busy
    gaps = list(free[0:10000])

    # Should get: [0, 999], [2001, 4999], [6001, 10000]
    # All clipped to query bounds
    assert len(gaps) == 3
    assert gaps[0].start == 0  # Clipped to query start
    assert gaps[0].end == 999
    assert gaps[1] == Interval(start=2001, end=4999)
    assert gaps[2].start == 6001
    assert gaps[2].end == 10000  # Clipped to query end


def test_difference_subtract_unbounded_from_bounded():
    """Test subtracting unbounded interval from bounded ones."""
    bounded = timeline(
        Interval(start=1000, end=5000),
        Interval(start=7000, end=9000),
    )

    # Subtract an unbounded "past" interval
    past = timeline(Interval(start=None, end=3000))

    result = bounded - past
    intervals = list(result[0:10000])

    # Should remove everything up to 3000
    # [1000, 5000] - [-∞, 3000] = [3001, 5000]
    # [7000, 9000] unchanged
    assert len(intervals) == 2
    assert intervals[0] == Interval(start=3001, end=5000)
    assert intervals[1] == Interval(start=7000, end=9000)


def test_flatten_with_unbounded_intervals():
    """Test that flatten handles unbounded intervals."""
    # Overlapping unbounded intervals
    tl = timeline(
        Interval(start=None, end=2000),
        Interval(start=1000, end=None),
    )

    from calgebra import flatten

    # Flatten with bounded query
    flattened = list(flatten(tl)[0:10000])

    # Should coalesce into one interval covering the entire range
    assert len(flattened) == 1
    assert flattened[0] == Interval(start=0, end=10000)


def test_flatten_with_unbounded_query():
    """Test that flatten supports unbounded queries (since it uses double complement)."""
    # Overlapping regular intervals
    tl = timeline(
        Interval(start=1000, end=2000),
        Interval(start=1500, end=2500),
    )

    from calgebra import flatten

    # Flatten with unbounded query should work now!
    flattened = list(flatten(tl)[None:None])

    # Should coalesce into one interval
    assert len(flattened) == 1
    assert flattened[0] == Interval(start=1000, end=2500)


def test_static_timeline_with_unbounded_intervals():
    """Test that static timelines handle unbounded intervals."""
    # Mix of bounded and unbounded
    tl = timeline(
        Interval(start=None, end=1000),
        Interval(start=2000, end=3000),
        Interval(start=5000, end=None),
    )

    # Should sort correctly using finite_start/finite_end
    # Query with finite bounds clips to query bounds
    intervals = list(tl[0:10000])

    assert len(intervals) == 3
    assert intervals[0].start == 0  # Clipped to query start
    assert intervals[0].end == 1000
    assert intervals[1] == Interval(start=2000, end=3000)
    assert intervals[2].start == 5000
    assert intervals[2].end == 10000  # Clipped to query end


def test_unbounded_interval_validation():
    """Test that unbounded intervals pass validation."""
    # These should all be valid
    Interval(start=None, end=None)
    Interval(start=None, end=1000)
    Interval(start=1000, end=None)

    # This should still fail
    try:
        Interval(start=2000, end=1000)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must be <=" in str(e)
