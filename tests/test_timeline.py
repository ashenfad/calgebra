from collections.abc import Iterable
from dataclasses import dataclass
from typing import Generic, TypeVar, override

import pytest

from calgebra.core import Intersection, Timeline, flatten, intersection, union
from calgebra.interval import Interval
from calgebra.metrics import (
    count_intervals,
    coverage_ratio,
    max_duration,
    min_duration,
    total_duration,
)
from calgebra.properties import Property, end, hours, minutes, one_of, seconds, start


@dataclass(frozen=True, kw_only=True)
class LabeledInterval(Interval):
    label: str


class Label(Property[LabeledInterval]):
    @override
    def apply(self, event: LabeledInterval) -> str:
        return event.label


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


class MetadataTimeline(DummyTimeline[LabeledInterval]):
    @override
    def _make_complement_interval(self, start: int, end: int) -> LabeledInterval:
        return LabeledInterval(start=start, end=end, label="free")


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

    assert list(timeline[9:21]) == [
        Interval(start=10, end=15),
        Interval(start=20, end=25),
    ]

    assert list(timeline[:15]) == [
        Interval(start=0, end=5),
        Interval(start=10, end=15),
    ]

    assert list(timeline[12:]) == [
        Interval(start=10, end=15),
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
    primary = DummyTimeline(
        Interval(start=5, end=5),
        Interval(start=10, end=15),
    )
    secondary = DummyTimeline(
        Interval(start=5, end=5),
        Interval(start=15, end=20),
    )

    assert list((primary & secondary)[:]) == [
        Interval(start=5, end=5),
        Interval(start=5, end=5),
        Interval(start=15, end=15),
        Interval(start=15, end=15),
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

    complement = list((~timeline)[10:20])

    assert complement == [
        Interval(start=13, end=14),
        Interval(start=18, end=20),
    ]


def test_complement_preserves_metadata_via_hook() -> None:
    timeline = MetadataTimeline(
        LabeledInterval(start=10, end=12, label="focus"),
        LabeledInterval(start=15, end=17, label="focus"),
    )

    complement = list((~timeline)[10:20])

    assert complement == [
        LabeledInterval(start=13, end=14, label="free"),
        LabeledInterval(start=18, end=20, label="free"),
    ]


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
    interval = Interval(start=10, end=12)

    assert seconds.apply(interval) == 3
    assert minutes.apply(interval) == pytest.approx(3 / 60)
    assert hours.apply(interval) == pytest.approx(3 / 3600)


def test_filter_slice_not_supported() -> None:
    with pytest.raises(NotImplementedError):
        _ = (start >= 0)[0:1]


def test_complement_requires_finite_bounds() -> None:
    timeline = DummyTimeline(Interval(start=0, end=5))

    with pytest.raises(ValueError):
        list((~timeline)[:10])

    with pytest.raises(ValueError):
        list((~timeline)[0:])


def test_complement_handles_empty_source() -> None:
    empty = DummyTimeline()

    assert list((~empty)[10:12]) == [Interval(start=10, end=12)]


def test_complement_coalesces_adjacent_segments() -> None:
    timeline = DummyTimeline(
        Interval(start=0, end=2),
        Interval(start=3, end=5),
        Interval(start=10, end=12),
    )

    # first two intervals should coalesce when computing coverage
    assert list((~timeline)[0:12]) == [Interval(start=6, end=9)]


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

    assert list(flatten(left & right)[0:10]) == [Interval(start=2, end=8)]


def test_intersection_touching_edges_inclusive() -> None:
    left = DummyTimeline(Interval(start=0, end=5))
    right = DummyTimeline(Interval(start=5, end=10))

    assert list((left & right)[:]) == [
        Interval(start=5, end=5),
        Interval(start=5, end=5),
    ]


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
        Interval(start=0, end=2),
        Interval(start=13, end=15),
    ]


def test_difference_splits_events_by_multiple_subtractions() -> None:
    timeline = DummyTimeline(Interval(start=0, end=10))
    subtractor = DummyTimeline(
        Interval(start=2, end=3),
        Interval(start=5, end=6),
    )

    assert list((timeline - subtractor)[:]) == [
        Interval(start=0, end=1),
        Interval(start=4, end=4),
        Interval(start=7, end=10),
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

    assert total_duration(combined, 0, 15) == 16


def test_flatten_returns_coalesced_intervals() -> None:
    timeline = DummyTimeline(
        Interval(start=0, end=5),
        Interval(start=10, end=15),
    )
    overlap = DummyTimeline(
        Interval(start=3, end=12),
    )

    flattened = flatten(timeline | overlap)

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

    # Covered time = 5 + 1 = 6; window span = 6
    assert coverage_ratio(timeline, 0, 5) == 1.0
