from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Generic, TypeVar
from zoneinfo import ZoneInfo

import pytest
from typing_extensions import override

from calgebra.core import Intersection, Timeline, flatten, intersection, union
from calgebra.interval import Interval
from calgebra.metrics import (
    count_intervals,
    coverage_ratio,
    max_duration,
    min_duration,
    total_duration,
)
from calgebra.mutable.memory import timeline
from calgebra.properties import (
    Property,
    end,
    field,
    has_all,
    has_any,
    hours,
    minutes,
    one_of,
    seconds,
    start,
)


@dataclass(frozen=True, kw_only=True)
class LabeledInterval(Interval):
    label: str


class Label(Property[LabeledInterval]):
    @override
    def apply(self, event: LabeledInterval) -> str:
        return event.label


@dataclass(frozen=True, kw_only=True)
class TaggedInterval(Interval):
    category: str
    priority: int


@dataclass(frozen=True, kw_only=True)
class CollectionInterval(Interval):
    tags: set[str]
    labels: list[str]


Ivl = TypeVar("Ivl", bound=Interval)


class DummyTimeline(Timeline[Ivl], Generic[Ivl]):
    """Simple timeline backed by a static set of intervals."""

    def __init__(self, *events: Ivl):
        self._events: tuple[Ivl, ...] = tuple(
            sorted(events, key=lambda event: (event.start, event.end))
        )

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Ivl]:
        for event in self._events:
            if start is not None and event.end < start:
                continue
            if end is not None and event.start > end:
                break
            yield event


def test_fetch_respects_bounds() -> None:
    timeline = DummyTimeline(
        Interval(start=0, end=5),
        Interval(start=10, end=15),
        Interval(start=20, end=25),
    )

    assert list(timeline[:]) == [
        Interval(start=0, end=5),
        Interval(start=10, end=15),
        Interval(start=20, end=25),
    ]

    # Intervals are clipped to query bounds
    # Slice [9:21] -> query [9, 20]
    assert list(timeline[9:21]) == [
        Interval(start=10, end=15),
        Interval(start=20, end=21),  # Clipped to query end (21)
    ]

    # Slice [:15] -> query [..., 14]
    assert list(timeline[:15]) == [
        Interval(start=0, end=5),
        Interval(start=10, end=15),  # Clipped to query end (15)
    ]

    # Intervals are clipped to query bounds
    assert list(timeline[12:]) == [
        Interval(start=12, end=15),  # Clipped to query start
        Interval(start=20, end=25),
    ]


def test_union_preserves_ordering() -> None:
    left = DummyTimeline(Interval(start=0, end=5), Interval(start=10, end=12))
    right = DummyTimeline(Interval(start=3, end=4), Interval(start=20, end=22))

    merged = list((left | right)[:])

    assert merged == [
        Interval(start=0, end=5),
        Interval(start=3, end=4),
        Interval(start=10, end=12),
        Interval(start=20, end=22),
    ]


def test_union_helper_matches_operator() -> None:
    timelines = [
        DummyTimeline(Interval(start=0, end=2)),
        DummyTimeline(Interval(start=1, end=3)),
        DummyTimeline(Interval(start=5, end=6)),
    ]

    chained = timelines[0] | timelines[1] | timelines[2]
    functional = union(*timelines)

    assert list(chained[:]) == list(functional[:])


def test_intersection_yields_overlaps() -> None:
    primary = DummyTimeline(
        Interval(start=0, end=5),
        Interval(start=10, end=15),
    )
    secondary = DummyTimeline(
        Interval(start=3, end=12),
        Interval(start=13, end=18),
    )

    result = list((primary & secondary)[:])

    assert result == [
        Interval(start=3, end=5),
        Interval(start=3, end=5),
        Interval(start=10, end=12),
        Interval(start=10, end=12),
        Interval(start=13, end=15),
        Interval(start=13, end=15),
    ]


def test_intersection_inclusive_edges() -> None:
    # With exclusive end intervals, we need overlapping intervals
    # [5,6) and [5,6) overlap fully
    # [10,16) and [15,20) overlap at [15,16)
    primary = DummyTimeline(
        Interval(start=5, end=6),
        Interval(start=10, end=16),
    )
    secondary = DummyTimeline(
        Interval(start=5, end=6),
        Interval(start=15, end=20),
    )

    assert list((primary & secondary)[:]) == [
        Interval(start=5, end=6),
        Interval(start=5, end=6),
        Interval(start=15, end=16),
        Interval(start=15, end=16),
    ]


def test_intersection_helper_matches_operator() -> None:
    timelines = [
        DummyTimeline(Interval(start=0, end=5), Interval(start=10, end=15)),
        DummyTimeline(Interval(start=3, end=12)),
        DummyTimeline(Interval(start=13, end=20)),
    ]

    chained = timelines[0] & timelines[1] & timelines[2]
    functional = intersection(*timelines)

    assert list(chained[:]) == list(functional[:])


def test_complement_returns_gaps() -> None:
    timeline = DummyTimeline(
        Interval(start=10, end=12),
        Interval(start=15, end=17),
    )

    # Slice [10:20] -> query [10, 19]
    complement = list((~timeline)[10:20])

    assert complement == [
        Interval(start=12, end=15),
        Interval(start=17, end=20),
    ]


def test_complement_yields_mask_intervals() -> None:
    """Complement always yields mask Intervals, even when source has metadata."""
    timeline = DummyTimeline(
        LabeledInterval(start=10, end=12, label="focus"),
        LabeledInterval(start=15, end=17, label="focus"),
    )

    # Slice [10:20] -> query [10, 19]
    complement = list((~timeline)[10:20])

    # Gaps are mask Intervals (not LabeledIntervals)
    assert complement == [
        Interval(start=12, end=15),
        Interval(start=17, end=20),
    ]

    # Verify they're actually mask Interval objects
    assert all(type(gap) == Interval for gap in complement)


def test_filter_applies_property_comparisons() -> None:
    timeline = DummyTimeline(
        Interval(start=5, end=10),
        Interval(start=12, end=13),
        Interval(start=20, end=25),
    )

    filtered = timeline & (start >= 12)
    filtered_end = timeline & (end <= 13)

    assert list(filtered[:]) == [
        Interval(start=12, end=13),
        Interval(start=20, end=25),
    ]

    assert list(filtered_end[:]) == [
        Interval(start=5, end=10),
        Interval(start=12, end=13),
    ]


def test_one_of_works_with_subclassed_intervals() -> None:
    timeline = DummyTimeline(
        LabeledInterval(start=0, end=5, label="focus"),
        LabeledInterval(start=10, end=12, label="break"),
        LabeledInterval(start=20, end=25, label="focus"),
    )

    focus_only = timeline & one_of(Label(), {"focus"})

    assert list(focus_only[:]) == [
        LabeledInterval(start=0, end=5, label="focus"),
        LabeledInterval(start=20, end=25, label="focus"),
    ]


def test_property_equality_operator() -> None:
    equals_focus = Label() == "focus"

    assert equals_focus.apply(LabeledInterval(start=0, end=5, label="focus")) is True
    assert equals_focus.apply(LabeledInterval(start=5, end=10, label="break")) is False


def test_property_inequality_operator() -> None:
    not_focus = Label() != "focus"

    assert not_focus.apply(LabeledInterval(start=0, end=5, label="focus")) is False
    assert not_focus.apply(LabeledInterval(start=5, end=10, label="break")) is True


def test_union_with_filter_raises() -> None:
    timeline = DummyTimeline(Interval(start=0, end=5))

    with pytest.raises(TypeError, match="Cannot union"):
        _ = timeline | (start >= 0)


def test_filter_union_with_timeline_raises() -> None:
    with pytest.raises(TypeError, match="Cannot union"):
        _ = (start >= 0) | DummyTimeline(Interval(start=0, end=5))


def test_filter_union_disjunction() -> None:
    mid = start >= 10
    late = start >= 20

    combined = mid | late

    assert combined.apply(Interval(start=9, end=10)) is False
    assert combined.apply(Interval(start=12, end=13)) is True
    assert combined.apply(Interval(start=25, end=30)) is True


def test_filter_and_conjunction() -> None:
    mid = start >= 10
    short = seconds <= 3

    both = mid & short

    assert both.apply(Interval(start=9, end=15)) is False
    assert both.apply(Interval(start=10, end=12)) is True
    assert both.apply(Interval(start=20, end=25)) is False


def test_filter_and_timeline_symmetric() -> None:
    timeline = DummyTimeline(
        Interval(start=0, end=2),
        Interval(start=10, end=12),
    )

    duration_filter = seconds <= 3
    start_filter = start >= 10

    filtered_left = timeline & duration_filter
    filtered_right = duration_filter & timeline
    ordered = start_filter & timeline

    assert (
        list(filtered_left[:])
        == list(filtered_right[:])
        == [
            Interval(start=0, end=2),
            Interval(start=10, end=12),
        ]
    )

    assert list(ordered[:]) == [Interval(start=10, end=12)]


def test_duration_properties_count_inclusive_bounds() -> None:
    # With exclusive end intervals, [10, 13) has duration 3
    interval = Interval(start=10, end=13)

    assert seconds.apply(interval) == 3
    assert minutes.apply(interval) == pytest.approx(3 / 60)
    assert hours.apply(interval) == pytest.approx(3 / 3600)


def test_filter_slice_not_supported() -> None:
    with pytest.raises(NotImplementedError):
        _ = (start >= 0)[0:1]


def test_complement_supports_unbounded_queries() -> None:
    """Test that complement now supports unbounded queries."""
    timeline = DummyTimeline(Interval(start=0, end=5))

    # Unbounded end works
    gaps = list((~timeline)[:10])
    assert len(gaps) > 0

    # Unbounded start works
    gaps = list((~timeline)[0:])
    assert len(gaps) > 0

    # Fully unbounded works
    gaps = list((~timeline)[:])
    assert len(gaps) > 0


def test_complement_handles_empty_source() -> None:
    empty = DummyTimeline()

    # Slice [10:12] -> query [10, 12)
    assert list((~empty)[10:12]) == [Interval(start=10, end=12)]


def test_complement_coalesces_adjacent_segments() -> None:
    timeline = DummyTimeline(
        Interval(start=0, end=2),
        Interval(start=3, end=5),
        Interval(start=10, end=12),
    )

    # With exclusive intervals: [0,2), [3,5), [10,12)
    # Gaps are: [2,3) and [5,10)
    # Slice [0:12] -> query [0, 12)
    assert list((~timeline)[0:12]) == [
        Interval(start=2, end=3),
        Interval(start=5, end=10),
    ]


def test_intersection_with_no_sources() -> None:
    assert list(Intersection()[:]) == []


def test_intersection_single_source_identity() -> None:
    timeline = DummyTimeline(
        Interval(start=0, end=5),
        Interval(start=10, end=15),
    )

    assert list(Intersection(timeline)[:]) == list(timeline[:])


def test_intersection_preserves_adjacent_fragments() -> None:
    left = DummyTimeline(
        Interval(start=0, end=4),
        Interval(start=5, end=10),
    )
    right = DummyTimeline(
        Interval(start=2, end=8),
    )

    fragments = list((left & right)[:])
    assert fragments == [
        Interval(start=2, end=4),
        Interval(start=2, end=4),
        Interval(start=5, end=8),
        Interval(start=5, end=8),
    ]

    # With exclusive intervals: left has [0,4) and [5,10), right has [2,8)
    # Intersections: [2,4) and [5,8)
    # These two fragments are NOT adjacent (gap at [4,5)), so flatten doesn't merge them
    assert list(flatten(left & right)[0:10]) == [
        Interval(start=2, end=4),
        Interval(start=5, end=8),
    ]


def test_intersection_touching_edges_inclusive() -> None:
    # With exclusive end intervals, [0, 5) and [5, 10) don't overlap
    # They touch at the boundary but don't share any time
    left = DummyTimeline(Interval(start=0, end=5))
    right = DummyTimeline(Interval(start=5, end=10))

    # No intersection because left ends at 5 (exclusive) and right starts at 5
    assert list((left & right)[:]) == []


def test_intersection_handles_exhausted_iterators() -> None:
    """Test that intersection correctly handles exhausted iterators.

    This tests the bug fix where intersection would stop prematurely when an iterator
    was exhausted, missing overlaps with remaining intervals from other sources.

    Scenario:
    - Timeline A: Contains intervals [100, 200) and [150, 160) (overlapping within A)
    - Timeline B (solid/query bounds): Contains interval [0, 200)
    - Intersection A & B should return both [100, 200) and [150, 160) since both overlap with [0, 200)
    """
    from calgebra.core import solid

    # Timeline A: has two overlapping intervals internally
    # Interval A1: [100, 200) - longer interval
    # Interval A2: [150, 160) - shorter interval contained within A1
    timeline_a = timeline(
        Interval(start=100, end=200),  # A1
        Interval(start=150, end=160),  # A2 (contained in A1)
    )

    # Timeline B (solid/query bounds): single interval [0, 200)
    query_start = 0
    query_end = 200

    # Intersect the two timelines
    # Both intervals from timeline_a overlap with solid's [0, 200), so both should be returned
    result = list((timeline_a & solid)[query_start:query_end])

    # Both intervals should be returned (they both overlap with solid's interval)
    assert len(result) == 2, (
        f"Expected 2 intervals, got {len(result)}. "
        f"When intersecting timeline_a (with overlapping intervals) and solid, "
        f"both intervals from timeline_a that overlap with solid should be returned."
    )
    assert result[0].start == 100 and result[0].end == 200
    assert result[1].start == 150 and result[1].end == 160


def test_intersection_preserves_metadata_from_all_sources() -> None:
    primary = DummyTimeline(
        LabeledInterval(start=0, end=5, label="primary"),
    )
    secondary = DummyTimeline(
        LabeledInterval(start=2, end=6, label="secondary"),
    )

    overlaps = list((primary & secondary)[:])

    assert overlaps == [
        LabeledInterval(start=2, end=5, label="primary"),
        LabeledInterval(start=2, end=5, label="secondary"),
    ]


def test_complement_returns_empty_when_fully_covered() -> None:
    timeline = DummyTimeline(Interval(start=0, end=10))

    assert list((~timeline)[0:10]) == []


def test_difference_removes_overlaps() -> None:
    timeline = DummyTimeline(
        Interval(start=0, end=5),
        Interval(start=10, end=15),
    )
    subtractor = DummyTimeline(Interval(start=3, end=12))

    assert list((timeline - subtractor)[:]) == [
        Interval(start=0, end=3),
        Interval(start=12, end=15),
    ]


def test_difference_splits_events_by_multiple_subtractions() -> None:
    timeline = DummyTimeline(Interval(start=0, end=10))
    subtractor = DummyTimeline(
        Interval(start=2, end=3),
        Interval(start=5, end=6),
    )

    assert list((timeline - subtractor)[:]) == [
        Interval(start=0, end=2),
        Interval(start=3, end=5),
        Interval(start=6, end=10),
    ]


def test_difference_without_overlap_returns_original_event() -> None:
    timeline = DummyTimeline(Interval(start=0, end=5))
    subtractor = DummyTimeline(Interval(start=10, end=12))

    assert list((timeline - subtractor)[:]) == [Interval(start=0, end=5)]


def test_total_duration_flattens_union() -> None:
    timeline = DummyTimeline(
        Interval(start=0, end=5),
        Interval(start=10, end=15),
    )
    overlap = DummyTimeline(
        Interval(start=3, end=12),
    )

    combined = timeline | overlap

    # total_duration uses slicing internally
    # total_duration(tl, 0, 15) -> tl[0:15] -> query [0, 15)
    # Combined covers [0, 15) fully (0-5, 3-12, 10-15)
    # Query [0, 15) is fully covered -> duration 15
    assert total_duration(combined, 0, 15) == 15


def test_flatten_returns_coalesced_intervals() -> None:
    timeline = DummyTimeline(
        Interval(start=0, end=5),
        Interval(start=10, end=15),
    )
    overlap = DummyTimeline(
        Interval(start=3, end=12),
    )

    flattened = flatten(timeline | overlap)

    # Slice [0:15] -> query [0, 15)
    assert list(flattened[0:15]) == [Interval(start=0, end=15)]


def test_max_duration_reports_longest_run() -> None:
    timeline = DummyTimeline(
        Interval(start=0, end=2),
        Interval(start=5, end=9),
    )

    assert max_duration(timeline, 0, 10) == Interval(start=5, end=9)


def test_min_duration_reports_shortest_run() -> None:
    timeline = DummyTimeline(
        Interval(start=0, end=2),
        Interval(start=5, end=9),
    )

    assert min_duration(timeline, 0, 10) == Interval(start=0, end=2)


def test_max_duration_can_use_flatten() -> None:
    timeline = DummyTimeline(
        Interval(start=0, end=2),
        Interval(start=5, end=9),
    )
    overlap = DummyTimeline(Interval(start=2, end=6))

    assert max_duration(flatten(timeline | overlap), 0, 10) == Interval(start=0, end=9)


def test_min_duration_can_use_flatten() -> None:
    timeline = DummyTimeline(
        Interval(start=0, end=2),
        Interval(start=5, end=9),
    )
    overlap = DummyTimeline(Interval(start=2, end=6))

    assert min_duration(flatten(timeline | overlap), 0, 10) == Interval(start=0, end=9)


def test_count_intervals_counts_slice_results() -> None:
    timeline = DummyTimeline(
        Interval(start=0, end=2),
        Interval(start=5, end=9),
    )

    assert count_intervals(timeline, 0, 10) == 2


def test_coverage_ratio_returns_fraction() -> None:
    timeline = DummyTimeline(
        Interval(start=0, end=4),
        Interval(start=5, end=5),
    )

    # Covered time = 4 + 1 = 5; window span = 6
    # coverage_ratio(tl, 0, 6) -> tl[0:6] -> query [0, 6)
    # Timeline has [0, 4) (duration 4) and [5, 5) (duration 0 - empty!)
    # Wait, [5, 5) is empty in exclusive intervals.
    # Let's adjust the test case to have non-empty intervals.
    timeline = DummyTimeline(
        Interval(start=0, end=4),
        Interval(start=5, end=6),
    )
    # Covered time = 4 + 1 = 5; window span = 6
    # coverage_ratio(tl, 0, 6) -> tl[0:6] -> query [0, 6)
    # Timeline has [0, 4) (duration 4) and [5, 6) (duration 1)
    # Query [0, 6) intersects both fully.
    # Covered duration = 5. Window duration = 6. Ratio = 5/6
    assert coverage_ratio(timeline, 0, 6) == 5 / 6


def test_timeline_accepts_timezone_aware_datetime_slicing() -> None:
    """Test that timelines accept timezone-aware datetime objects in slices."""
    # Create timeline with known timestamps
    # Jan 1, 2025 00:00:00 UTC = 1735689600
    # Jan 31, 2025 23:59:59 UTC = 1738367999
    timeline = DummyTimeline(
        Interval(start=1735689600, end=1735776000),  # Jan 1-2, 2025
        Interval(start=1738281600, end=1738367999),  # Jan 30-31, 2025
    )

    # Slice with timezone-aware datetimes
    start_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2025, 1, 31, 23, 59, 59, tzinfo=timezone.utc)

    results = list(timeline[start_dt:end_dt])
    assert len(results) == 2
    assert results[0].start == 1735689600
    # end_dt is Jan 31 23:59:59. Exclusive slice -> query ends at ...59
    # So the interval [..., ...99] is clipped to [..., ...99]
    assert results[1].end == 1738367999


def test_timeline_rejects_date_objects() -> None:
    """Test that timelines reject date objects (require timezone-aware datetime)."""
    timeline = DummyTimeline(
        Interval(start=1735689600, end=1735776000),  # Jan 1-2, 2025
    )

    # Date objects are no longer supported
    start_date = date(2025, 1, 1)
    end_date = date(2025, 1, 31)

    with pytest.raises(TypeError, match="timezone-aware datetime"):
        list(timeline[start_date:end_date])


def test_timeline_rejects_naive_datetime() -> None:
    """Test that timelines reject naive (timezone-unaware) datetime objects."""
    timeline = DummyTimeline(Interval(start=0, end=100))

    naive_dt = datetime(2025, 1, 1)  # No timezone

    with pytest.raises(TypeError, match="timezone-aware datetime"):
        list(timeline[naive_dt : datetime(2025, 12, 31)])


def test_timeline_datetime_slicing_with_different_timezones() -> None:
    """Test that datetime slicing works correctly with different timezones."""
    # Jan 1, 2025 00:00:00 UTC = 1735689600
    timeline = DummyTimeline(
        Interval(start=1735689600, end=1735776000),
    )

    # Same moment in time, different timezone representations
    utc_dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    pacific_dt = datetime(2024, 12, 31, 16, 0, 0, tzinfo=ZoneInfo("US/Pacific"))

    # Both should return the same results (same timestamp)
    results_utc = list(timeline[utc_dt:])
    results_pacific = list(timeline[pacific_dt:])

    assert results_utc == results_pacific


def test_composed_timeline_accepts_datetime_slicing() -> None:
    """Test that composed timelines (union, intersection) accept datetime slicing."""
    timeline1 = DummyTimeline(Interval(start=1735689600, end=1735776000))
    timeline2 = DummyTimeline(Interval(start=1735732800, end=1735819200))

    # Test union with datetime slicing
    union_tl = timeline1 | timeline2
    start_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2025, 1, 3, tzinfo=timezone.utc)

    union_results = list(union_tl[start_dt:end_dt])
    assert len(union_results) == 2

    # Test intersection with datetime slicing
    intersection_tl = timeline1 & timeline2
    intersection_results = list(intersection_tl[start_dt:end_dt])
    assert len(intersection_results) > 0


def test_datetime_slicing_uses_full_day_boundaries() -> None:
    """Test that datetime slicing with day boundaries works correctly."""
    # Create interval that starts at midnight and ends at 23:59:59
    # Jan 1, 2025 00:00:00 UTC = 1735689600
    # Jan 1, 2025 23:59:59 UTC = 1735775999
    timeline = DummyTimeline(
        Interval(start=1735689600, end=1735775999),
    )

    # Slice with datetime at day boundaries
    # start: Jan 1 00:00:00
    # end: Jan 1 23:59:59
    # Exclusive slice -> query [..., ...58]
    # So the interval [..., ...99] is clipped to [..., ...98]
    start_dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(2025, 1, 1, 23, 59, 59, tzinfo=timezone.utc)
    results = list(timeline[start_dt:end_dt])
    assert len(results) == 1
    assert results[0].start == 1735689600
    assert results[0].end == 1735775999


def test_mixed_int_and_datetime_slicing() -> None:
    """Test that int and datetime slicing can be mixed."""
    timeline = DummyTimeline(
        Interval(start=1735689600, end=1735776000),
    )

    # Mix int and datetime
    start_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end_int = 1735776000

    results = list(timeline[start_dt:end_int])
    assert len(results) == 1


def test_timeline_helper_creates_static_timeline() -> None:
    """Test that timeline() helper creates a working timeline."""
    tl = timeline(
        Interval(start=0, end=5),
        Interval(start=10, end=15),
        Interval(start=20, end=25),
    )

    # Should behave like any other timeline
    results = list(tl[0:30])
    assert results == [
        Interval(start=0, end=5),
        Interval(start=10, end=15),
        Interval(start=20, end=25),
    ]


def test_timeline_helper_sorts_intervals() -> None:
    """Test that timeline() helper sorts intervals by (start, end)."""
    tl = timeline(
        Interval(start=20, end=25),
        Interval(start=0, end=5),
        Interval(start=10, end=15),
    )

    results = list(tl[:])
    assert results == [
        Interval(start=0, end=5),
        Interval(start=10, end=15),
        Interval(start=20, end=25),
    ]


def test_timeline_helper_preserves_subclass_type() -> None:
    """Test that timeline() preserves subclassed interval types."""
    tl = timeline(
        LabeledInterval(start=0, end=5, label="first"),
        LabeledInterval(start=10, end=15, label="second"),
    )

    results = list(tl[:])
    assert len(results) == 2
    assert isinstance(results[0], LabeledInterval)
    assert results[0].label == "first"
    assert results[1].label == "second"


def test_timeline_helper_works_with_custom_properties() -> None:
    """Test that timeline() works with custom properties on subclassed intervals."""
    tl = timeline(
        LabeledInterval(start=0, end=5, label="focus"),
        LabeledInterval(start=10, end=15, label="break"),
        LabeledInterval(start=20, end=25, label="focus"),
    )

    # Filter using custom property
    label = Label()
    focus_only = tl & (label == "focus")

    results = list(focus_only[:])
    assert len(results) == 2
    assert all(r.label == "focus" for r in results)


def test_timeline_helper_composable() -> None:
    """Test that timeline() helper results are composable with other operations."""
    tl1 = timeline(
        Interval(start=0, end=5),
        Interval(start=10, end=15),
    )
    tl2 = timeline(
        Interval(start=3, end=12),
    )

    # Union
    union_result = list((tl1 | tl2)[:])
    assert len(union_result) == 3

    # Intersection
    intersection_result = list((tl1 & tl2)[:])
    assert len(intersection_result) > 0

    # Difference
    diff_result = list((tl1 - tl2)[:])
    assert len(diff_result) > 0

    # Complement
    # Slice [0:20] -> query [0, 19]
    complement_result = list((~tl1)[0:20])
    assert len(complement_result) > 0


def test_timeline_helper_respects_bounds() -> None:
    """Test that timeline() helper respects slice bounds."""
    tl = timeline(
        Interval(start=0, end=5),
        Interval(start=10, end=15),
        Interval(start=20, end=25),
    )

    # Intervals are clipped to query bounds
    # Slice [9:21] -> query [9, 21)
    assert list(tl[9:21]) == [
        Interval(start=10, end=15),
        Interval(start=20, end=21),  # Clipped to query end (21)
    ]

    # Slice [:15] -> query [..., 15)
    assert list(tl[:15]) == [
        Interval(start=0, end=5),
        Interval(start=10, end=15),  # Fully included in query
    ]

    # Intervals are clipped to query bounds
    assert list(tl[12:]) == [
        Interval(start=12, end=15),  # Clipped to query start
        Interval(start=20, end=25),
    ]


def test_field_helper_with_string_accessor() -> None:
    """Test that field() helper works with string field names."""
    tl = DummyTimeline(
        TaggedInterval(start=0, end=5, category="work", priority=5),
        TaggedInterval(start=10, end=15, category="personal", priority=3),
        TaggedInterval(start=20, end=25, category="work", priority=9),
    )

    # Filter using string field name
    category_prop = field("category")
    work_events = tl & one_of(category_prop, {"work"})

    results = list(work_events[:])
    assert len(results) == 2
    assert all(event.category == "work" for event in results)


def test_field_helper_with_lambda_accessor() -> None:
    """Test that field() helper works with lambda accessors."""
    tl = DummyTimeline(
        TaggedInterval(start=0, end=5, category="work", priority=5),
        TaggedInterval(start=10, end=15, category="personal", priority=3),
        TaggedInterval(start=20, end=25, category="work", priority=9),
    )

    # Filter using lambda accessor
    priority_prop = field(lambda e: e.priority)
    high_priority = tl & (priority_prop >= 8)

    results = list(high_priority[:])
    assert len(results) == 1
    assert results[0].priority == 9


def test_field_helper_with_computed_property() -> None:
    """Test that field() helper works with computed properties."""
    tl = DummyTimeline(
        TaggedInterval(start=0, end=5, category="work", priority=5),
        TaggedInterval(start=10, end=15, category="personal-health", priority=3),
        TaggedInterval(start=20, end=25, category="work", priority=9),
    )

    # Computed property: length of category string
    category_length = field(lambda e: len(e.category))
    long_category = tl & (category_length >= 10)

    results = list(long_category[:])
    assert len(results) == 1
    assert results[0].category == "personal-health"


def test_field_helper_comparison_with_manual_property() -> None:
    """Test that field() helper produces same results as manual Property subclass."""
    tl = DummyTimeline(
        LabeledInterval(start=0, end=5, label="focus"),
        LabeledInterval(start=10, end=15, label="break"),
        LabeledInterval(start=20, end=25, label="focus"),
    )

    # Manual property class
    manual = tl & (Label() == "focus")

    # field() helper with lambda
    helper = tl & (field(lambda e: e.label) == "focus")

    assert list(manual[:]) == list(helper[:])


def test_has_any_with_set_field() -> None:
    """Test has_any with set-typed fields."""
    tl = DummyTimeline(
        CollectionInterval(start=0, end=5, tags={"work"}, labels=["important"]),
        CollectionInterval(start=10, end=15, tags={"personal"}, labels=["health"]),
        CollectionInterval(
            start=20, end=25, tags={"work", "urgent"}, labels=["critical"]
        ),
    )

    # Match events with "work" tag
    tags = field("tags")
    work_events = tl & has_any(tags, {"work"})

    results = list(work_events[:])
    assert len(results) == 2
    assert all("work" in event.tags for event in results)


def test_has_any_rejects_string_properties() -> None:
    """has_any should reject scalar string properties."""
    tl = DummyTimeline(
        TaggedInterval(start=0, end=5, category="work", priority=5),
    )

    with pytest.raises(TypeError, match=r"has_any\(\) must return an iterable"):
        list((tl & has_any(field("category"), {"work"}))[:])


def test_has_any_with_list_field() -> None:
    """Test has_any with list-typed fields."""
    tl = DummyTimeline(
        CollectionInterval(start=0, end=5, tags={"a"}, labels=["important", "todo"]),
        CollectionInterval(start=10, end=15, tags={"b"}, labels=["health"]),
        CollectionInterval(start=20, end=25, tags={"c"}, labels=["todo", "urgent"]),
    )

    # Match events with "todo" label
    labels = field("labels")
    todo_events = tl & has_any(labels, {"todo", "urgent"})

    results = list(todo_events[:])
    assert len(results) == 2
    assert all(
        any(label in ["todo", "urgent"] for label in event.labels) for event in results
    )


def test_has_any_with_multiple_matches() -> None:
    """Test has_any matches when ANY value is present."""
    tl = DummyTimeline(
        CollectionInterval(start=0, end=5, tags={"work"}, labels=[]),
        CollectionInterval(start=10, end=15, tags={"personal"}, labels=[]),
        CollectionInterval(start=20, end=25, tags={"work", "urgent"}, labels=[]),
    )

    tags = field("tags")
    # Should match both "work" and "work,urgent" events
    work_or_urgent = tl & has_any(tags, {"work", "urgent"})

    results = list(work_or_urgent[:])
    assert len(results) == 2


def test_has_all_with_set_field() -> None:
    """Test has_all with set-typed fields."""
    tl = DummyTimeline(
        CollectionInterval(start=0, end=5, tags={"work"}, labels=[]),
        CollectionInterval(start=10, end=15, tags={"work", "urgent"}, labels=[]),
        CollectionInterval(
            start=20, end=25, tags={"work", "urgent", "critical"}, labels=[]
        ),
    )

    # Match events with BOTH "work" AND "urgent" tags
    tags = field("tags")
    critical_work = tl & has_all(tags, {"work", "urgent"})

    results = list(critical_work[:])
    assert len(results) == 2
    assert all({"work", "urgent"}.issubset(event.tags) for event in results)


def test_has_all_rejects_string_properties() -> None:
    """has_all should reject scalar string properties."""
    tl = DummyTimeline(
        TaggedInterval(start=0, end=5, category="work", priority=5),
    )

    with pytest.raises(TypeError, match=r"has_all\(\) must return an iterable"):
        list((tl & has_all(field("category"), {"work"}))[:])


def test_has_all_with_single_value() -> None:
    """Test has_all with a single required value."""
    tl = DummyTimeline(
        CollectionInterval(start=0, end=5, tags={"work"}, labels=[]),
        CollectionInterval(start=10, end=15, tags={"personal"}, labels=[]),
        CollectionInterval(start=20, end=25, tags={"work", "urgent"}, labels=[]),
    )

    tags = field("tags")
    work_events = tl & has_all(tags, {"work"})

    results = list(work_events[:])
    assert len(results) == 2
    assert all("work" in event.tags for event in results)


def test_has_all_requires_all_values() -> None:
    """Test has_all only matches when ALL values are present."""
    tl = DummyTimeline(
        CollectionInterval(start=0, end=5, tags={"work"}, labels=[]),
        CollectionInterval(start=10, end=15, tags={"work", "urgent"}, labels=[]),
        CollectionInterval(
            start=20, end=25, tags={"work", "urgent", "critical"}, labels=[]
        ),
    )

    tags = field("tags")
    # Should only match events with all three tags
    triple_tagged = tl & has_all(tags, {"work", "urgent", "critical"})

    results = list(triple_tagged[:])
    assert len(results) == 1
    assert results[0].tags == {"work", "urgent", "critical"}


def test_has_any_with_lambda_accessor() -> None:
    """Test has_any works with lambda accessors."""
    tl = DummyTimeline(
        CollectionInterval(start=0, end=5, tags={"work"}, labels=[]),
        CollectionInterval(start=10, end=15, tags={"personal"}, labels=[]),
    )

    # Use lambda for type-safe access
    work_events = tl & has_any(field(lambda e: e.tags), {"work"})

    results = list(work_events[:])
    assert len(results) == 1
    assert "work" in results[0].tags


def test_has_all_with_lambda_accessor() -> None:
    """Test has_all works with lambda accessors."""
    tl = DummyTimeline(
        CollectionInterval(start=0, end=5, tags={"work"}, labels=[]),
        CollectionInterval(start=10, end=15, tags={"work", "urgent"}, labels=[]),
    )

    # Use lambda for type-safe access
    critical = tl & has_all(field(lambda e: e.tags), {"work", "urgent"})

    results = list(critical[:])
    assert len(results) == 1
    assert results[0].tags == {"work", "urgent"}
