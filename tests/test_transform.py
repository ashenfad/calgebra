"""Tests for timeline transformation operations."""

from collections.abc import Iterable
from dataclasses import dataclass

from typing_extensions import override

from calgebra import Interval, Timeline, buffer, merge_within, minutes


@dataclass(frozen=True, kw_only=True)
class Event(Interval):
    """Test event with metadata."""

    label: str


class SimpleTimeline(Timeline[Interval]):
    """Test timeline backed by static intervals."""

    def __init__(self, *events: Interval):
        self._events = tuple(sorted(events, key=lambda e: (e.start, e.end)))

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Interval]:
        for event in self._events:
            if start is not None and event.end < start:
                continue
            if end is not None and event.start > end:
                break
            yield event


class EventTimeline(Timeline[Event]):
    """Test timeline with metadata."""

    def __init__(self, *events: Event):
        self._events = tuple(sorted(events, key=lambda e: (e.start, e.end)))

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Event]:
        for event in self._events:
            if start is not None and event.end < start:
                continue
            if end is not None and event.start > end:
                break
            yield event


# buffer() tests


def test_buffer_adds_time_before() -> None:
    """Test that buffer adds time before interval starts."""
    timeline = SimpleTimeline(
        Interval(start=100, end=200),
        Interval(start=300, end=400),
    )

    buffered = buffer(timeline, before=50)
    result = list(buffered[0:500])

    assert result == [
        Interval(start=50, end=200),  # 100-50 = 50
        Interval(start=250, end=400),  # 300-50 = 250
    ]


def test_buffer_adds_time_after() -> None:
    """Test that buffer adds time after interval ends."""
    timeline = SimpleTimeline(
        Interval(start=100, end=200),
        Interval(start=300, end=400),
    )

    buffered = buffer(timeline, after=50)
    result = list(buffered[0:500])

    assert result == [
        Interval(start=100, end=250),  # 200+50 = 250
        Interval(start=300, end=450),  # 400+50 = 450
    ]


def test_buffer_adds_time_both_sides() -> None:
    """Test that buffer adds time on both sides."""
    timeline = SimpleTimeline(Interval(start=100, end=200))

    buffered = buffer(timeline, before=25, after=50)
    result = list(buffered[0:300])

    assert result == [Interval(start=75, end=250)]  # 100-25, 200+50


def test_buffer_default_does_nothing() -> None:
    """Test that buffer with no parameters is identity."""
    timeline = SimpleTimeline(
        Interval(start=100, end=200),
        Interval(start=300, end=400),
    )

    buffered = buffer(timeline)
    result = list(buffered[0:500])

    assert result == [
        Interval(start=100, end=200),
        Interval(start=300, end=400),
    ]


def test_buffer_preserves_metadata() -> None:
    """Test that buffer preserves interval metadata."""
    timeline = EventTimeline(
        Event(start=100, end=200, label="meeting"),
        Event(start=300, end=400, label="focus"),
    )

    buffered = buffer(timeline, before=30, after=30)
    result = list(buffered[0:500])

    assert result == [
        Event(start=70, end=230, label="meeting"),
        Event(start=270, end=430, label="focus"),
    ]


def test_buffer_can_create_overlaps() -> None:
    """Test that buffer can cause intervals to overlap."""
    timeline = SimpleTimeline(
        Interval(start=100, end=150),
        Interval(start=200, end=250),
    )

    # Large buffer causes overlap
    buffered = buffer(timeline, after=100)
    result = list(buffered[0:400])

    # Intervals now overlap (first ends at 250, second starts at 200)
    assert result == [
        Interval(start=100, end=250),
        Interval(start=200, end=350),
    ]


def test_buffer_respects_query_bounds() -> None:
    """Test that buffer respects slice bounds."""
    timeline = SimpleTimeline(
        Interval(start=100, end=200),
        Interval(start=300, end=400),
    )

    buffered = buffer(timeline, before=50, after=50)

    # Query subset - intervals are clipped to query bounds
    result = list(buffered[200:350])

    # First interval extends to 250 (overlaps query start), clipped to start at 200
    # Second interval starts at 250 (within query), clipped to end at 350
    assert result == [
        Interval(start=200, end=250),  # Clipped to query start
        Interval(start=250, end=350),  # Clipped to query end
    ]


def test_buffer_flight_use_case() -> None:
    """Test real-world use case: flight with 2-hour pre-travel time."""
    # Flight from 10:00 (36000) to 14:00 (50400)
    flights = SimpleTimeline(Interval(start=36000, end=50400))

    # Need 2 hours (7200 seconds) at airport before flight
    blocked = buffer(flights, before=7200)

    result = list(blocked[0:86400])

    # Should block from 8:00 (28800) to 14:00 (50400)
    assert result == [Interval(start=28800, end=50400)]


def test_buffer_meeting_buffer_use_case() -> None:
    """Test real-world use case: meetings with 15-min buffers."""
    meetings = SimpleTimeline(
        Interval(start=32400, end=36000),  # 9:00-10:00
        Interval(start=39600, end=43200),  # 11:00-12:00
    )

    # 15 minutes (900 seconds) buffer on each side
    busy = buffer(meetings, before=900, after=900)

    result = list(busy[0:86400])

    assert result == [
        Interval(start=31500, end=36900),  # 8:45-10:15
        Interval(start=38700, end=44100),  # 10:45-12:15
    ]


# merge_within() tests


def test_merge_within_merges_close_intervals() -> None:
    """Test that intervals within gap threshold are merged."""
    timeline = SimpleTimeline(
        Interval(start=100, end=110),
        Interval(start=120, end=130),  # Gap of 9 seconds (120-110-1)
        Interval(start=140, end=150),  # Gap of 9 seconds (140-130-1)
    )

    merged = merge_within(timeline, gap=10)
    result = list(merged[0:200])

    # All three should merge (gaps <= 10)
    assert result == [Interval(start=100, end=150)]


def test_merge_within_keeps_distant_intervals_separate() -> None:
    """Test that intervals beyond gap threshold stay separate."""
    timeline = SimpleTimeline(
        Interval(start=100, end=110),
        Interval(start=125, end=135),  # Gap of 14 seconds (125-110-1)
    )

    merged = merge_within(timeline, gap=10)
    result = list(merged[0:200])

    # Gap is 14 > 10, should stay separate
    assert result == [
        Interval(start=100, end=110),
        Interval(start=125, end=135),
    ]


def test_merge_within_exact_gap_threshold() -> None:
    """Test that intervals exactly at gap threshold are merged."""
    timeline = SimpleTimeline(
        Interval(start=100, end=110),
        Interval(start=121, end=130),  # Gap exactly 10 seconds (121-110-1)
    )

    merged = merge_within(timeline, gap=10)
    result = list(merged[0:200])

    # Gap is exactly 10, should merge
    assert result == [Interval(start=100, end=130)]


def test_merge_within_one_second_over_threshold() -> None:
    """Test that intervals one second over threshold stay separate."""
    timeline = SimpleTimeline(
        Interval(start=100, end=110),
        Interval(start=122, end=130),  # Gap is 11 seconds (122-110-1)
    )

    merged = merge_within(timeline, gap=10)
    result = list(merged[0:200])

    # Gap is 11 > 10, should stay separate
    assert result == [
        Interval(start=100, end=110),
        Interval(start=122, end=130),
    ]


def test_merge_within_adjacent_intervals() -> None:
    """Test that adjacent intervals (gap=0) are merged."""
    timeline = SimpleTimeline(
        Interval(start=100, end=110),
        Interval(start=111, end=120),  # Gap of 0 (111-110-1)
    )

    merged = merge_within(timeline, gap=0)
    result = list(merged[0:200])

    # Adjacent intervals should merge even with gap=0
    assert result == [Interval(start=100, end=120)]


def test_merge_within_overlapping_intervals() -> None:
    """Test that overlapping intervals are merged."""
    timeline = SimpleTimeline(
        Interval(start=100, end=120),
        Interval(start=110, end=130),  # Overlaps by 10 seconds
    )

    merged = merge_within(timeline, gap=5)
    result = list(merged[0:200])

    # Overlapping intervals always merge regardless of gap
    assert result == [Interval(start=100, end=130)]


def test_merge_within_preserves_first_interval_metadata() -> None:
    """Test that merge_within preserves metadata from first interval."""
    timeline = EventTimeline(
        Event(start=100, end=110, label="alarm1"),
        Event(start=120, end=130, label="alarm2"),
        Event(start=140, end=150, label="alarm3"),
    )

    merged = merge_within(timeline, gap=15)
    result = list(merged[0:200])

    # All merge, but keep first interval's label
    assert result == [Event(start=100, end=150, label="alarm1")]


def test_merge_within_multiple_groups() -> None:
    """Test that merge_within creates separate groups."""
    timeline = SimpleTimeline(
        Interval(start=100, end=110),
        Interval(start=120, end=130),  # Close to first (gap=9)
        Interval(start=200, end=210),  # Far from second (gap=69)
        Interval(start=220, end=230),  # Close to third (gap=9)
    )

    merged = merge_within(timeline, gap=10)
    result = list(merged[0:300])

    # Should form two groups
    assert result == [
        Interval(start=100, end=130),  # First two merged
        Interval(start=200, end=230),  # Last two merged
    ]


def test_merge_within_single_interval() -> None:
    """Test that single interval passes through unchanged."""
    timeline = SimpleTimeline(Interval(start=100, end=200))

    merged = merge_within(timeline, gap=10)
    result = list(merged[0:300])

    assert result == [Interval(start=100, end=200)]


def test_merge_within_empty_timeline() -> None:
    """Test that empty timeline stays empty."""
    timeline = SimpleTimeline()

    merged = merge_within(timeline, gap=10)
    result = list(merged[0:300])

    assert result == []


def test_merge_within_alarm_incident_use_case() -> None:
    """Test real-world use case: grouping alarms into incidents."""
    # Alarms that fire close together
    alarms = EventTimeline(
        Event(start=1000, end=1010, label="cpu_high"),
        Event(start=1060, end=1070, label="cpu_high"),  # 49 sec later
        Event(start=1120, end=1130, label="cpu_high"),  # 49 sec later
        Event(start=2000, end=2010, label="cpu_high"),  # 869 sec later
    )

    # Treat alarms within 1 minute (60 sec) as same incident
    incidents = merge_within(alarms, gap=60)
    result = list(incidents[0:3000])

    # Should get 2 incidents
    assert len(result) == 2
    assert result[0] == Event(start=1000, end=1130, label="cpu_high")
    assert result[1] == Event(start=2000, end=2010, label="cpu_high")


def test_merge_within_meeting_blocks_use_case() -> None:
    """Test real-world use case: grouping meetings into busy blocks."""
    meetings = SimpleTimeline(
        Interval(start=32400, end=36000),  # 9:00-10:00
        Interval(start=36300, end=39600),  # 10:05-11:00 (5 min gap)
        Interval(start=46800, end=50400),  # 13:00-14:00 (2 hour gap)
    )

    # Group meetings with <= 10 min (600 sec) gap
    blocks = merge_within(meetings, gap=600)
    result = list(blocks[0:86400])

    # First two merge (5 min gap), third separate (2 hour gap)
    assert len(result) == 2
    assert result[0] == Interval(start=32400, end=39600)  # 9:00-11:00 block
    assert result[1] == Interval(start=46800, end=50400)  # 13:00-14:00 separate


# Combined operations tests


def test_buffer_then_merge() -> None:
    """Test composing buffer and merge_within."""
    meetings = SimpleTimeline(
        Interval(start=100, end=150),
        Interval(start=200, end=250),
    )

    # Add 30-second buffer, then merge if within 10 seconds
    buffered = buffer(meetings, before=30, after=30)
    merged = merge_within(buffered, gap=10)
    result = list(merged[0:300])

    # After buffering: [70, 180] and [170, 280]
    # These now overlap! Should merge to single interval
    assert result == [Interval(start=70, end=280)]


def test_merge_then_buffer() -> None:
    """Test composing merge_within and buffer."""
    events = SimpleTimeline(
        Interval(start=100, end=110),
        Interval(start=120, end=130),  # Gap of 9
        Interval(start=200, end=210),  # Gap of 69
    )

    # First merge close events, then add buffer
    merged = merge_within(events, gap=10)
    buffered = buffer(merged, before=20, after=20)
    result = list(buffered[0:300])

    # After merge: [100, 130] and [200, 210]
    # After buffer: [80, 150] and [180, 230]
    assert result == [
        Interval(start=80, end=150),
        Interval(start=180, end=230),
    ]


def test_buffer_composable() -> None:
    """Test that buffer is composable with filters and other operations."""
    timeline = SimpleTimeline(
        Interval(start=0, end=100),
        Interval(start=200, end=300),
    )

    # Buffer, then filter by duration
    from calgebra import hours

    buffered = buffer(timeline, before=50, after=50)
    # After buffering: [-50, 150] (201 seconds) and [150, 350] (201 seconds)
    long_events = buffered & (hours >= 0.05)  # >= 180 seconds (3 minutes)

    result = list(long_events[0:400])
    assert len(result) == 2  # Both intervals are long enough
