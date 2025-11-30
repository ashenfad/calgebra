"""Tests for reverse iteration support in timelines."""

from datetime import datetime, timezone
from itertools import islice

import pytest

from calgebra import (
    Interval,
    day_of_week,
    flatten,
    recurring,
    time_of_day,
)
from calgebra.core import Timeline
from calgebra.mutable.memory import timeline
from calgebra.transform import buffer, merge_within
from calgebra.util import DAY, HOUR


class SimpleTimeline(Timeline[Interval]):
    """Test timeline backed by static intervals."""

    def __init__(self, *events: Interval):
        self._events = tuple(sorted(events, key=lambda e: (e.start, e.end)))

    def fetch(self, start, end, *, reverse: bool = False):
        matching = [
            event
            for event in self._events
            if not (start is not None and event.end < start)
            and not (end is not None and event.start > end)
        ]
        if reverse:
            yield from reversed(matching)
        else:
            yield from matching


# === Step validation tests ===


def test_step_validation_rejects_invalid_step():
    """Test that invalid step values are rejected."""
    tl = timeline(Interval(start=0, end=100))

    with pytest.raises(ValueError, match="only supports step of 1 or -1"):
        list(tl[0:100:2])

    with pytest.raises(ValueError, match="only supports step of 1 or -1"):
        list(tl[0:100:0])

    with pytest.raises(ValueError, match="only supports step of 1 or -1"):
        list(tl[0:100:-2])


def test_step_none_defaults_to_forward():
    """Test that step=None defaults to forward iteration."""
    tl = timeline(
        Interval(start=100, end=200),
        Interval(start=300, end=400),
    )

    result = list(tl[0:500])
    assert result == [Interval(start=100, end=200), Interval(start=300, end=400)]


def test_step_1_is_forward():
    """Test that step=1 iterates forward."""
    tl = timeline(
        Interval(start=100, end=200),
        Interval(start=300, end=400),
    )

    result = list(tl[0:500:1])
    assert result == [Interval(start=100, end=200), Interval(start=300, end=400)]


# === Bounds normalization tests ===


def test_reverse_normalizes_bounds():
    """Test that reverse iteration normalizes bounds to [min, max)."""
    tl = timeline(
        Interval(start=100, end=200),
        Interval(start=300, end=400),
    )

    # Both orderings should give same intervals, just reversed
    result1 = list(tl[500:0:-1])
    result2 = list(tl[0:500:-1])

    assert result1 == result2
    assert result1 == [Interval(start=300, end=400), Interval(start=100, end=200)]


# === Memory timeline reverse tests ===


def test_memory_timeline_reverse_iteration():
    """Test basic reverse iteration on MemoryTimeline."""
    tl = timeline(
        Interval(start=100, end=200),
        Interval(start=300, end=400),
        Interval(start=500, end=600),
    )

    result = list(tl[0:700:-1])
    assert result == [
        Interval(start=500, end=600),
        Interval(start=300, end=400),
        Interval(start=100, end=200),
    ]


def test_memory_timeline_reverse_with_islice():
    """Test 'last N events' pattern with reverse iteration."""
    tl = timeline(
        Interval(start=100, end=200),
        Interval(start=300, end=400),
        Interval(start=500, end=600),
        Interval(start=700, end=800),
        Interval(start=900, end=1000),
    )

    # Get last 2 events ending before timestamp 850
    # Note: Query [0:850) clips intervals to bounds, so we look for events
    # that start before 850
    last_2 = list(islice(tl[0:850:-1], 2))
    assert last_2 == [
        Interval(start=700, end=800),
        Interval(start=500, end=600),
    ]


# === Union reverse tests ===


def test_union_reverse_merges_correctly():
    """Test that union reverse merges multiple streams correctly."""
    tl1 = timeline(Interval(start=100, end=200), Interval(start=500, end=600))
    tl2 = timeline(Interval(start=300, end=400), Interval(start=700, end=800))

    combined = tl1 | tl2

    # Forward
    forward = list(combined[0:900])
    assert forward == [
        Interval(start=100, end=200),
        Interval(start=300, end=400),
        Interval(start=500, end=600),
        Interval(start=700, end=800),
    ]

    # Reverse
    reverse = list(combined[0:900:-1])
    assert reverse == [
        Interval(start=700, end=800),
        Interval(start=500, end=600),
        Interval(start=300, end=400),
        Interval(start=100, end=200),
    ]


# === Intersection reverse tests ===


def test_intersection_reverse():
    """Test that intersection supports reverse iteration."""
    # Use flatten to coalesce overlapping intervals from intersection
    tl1 = timeline(Interval(start=0, end=100), Interval(start=200, end=300))
    tl2 = timeline(Interval(start=50, end=250))

    combined = flatten(tl1 & tl2)

    forward = list(combined[0:400])
    # Intersection overlaps: [50, 100) and [200, 250)
    assert len(forward) == 2

    reverse = list(combined[0:400:-1])
    assert reverse == list(reversed(forward))


# === Complement reverse tests ===


def test_complement_reverse():
    """Test that complement supports reverse iteration."""
    tl = timeline(Interval(start=100, end=200), Interval(start=300, end=400))

    complement = ~tl

    forward = list(complement[0:500])
    # Gaps: [0, 100), [200, 300), [400, 500)
    assert forward == [
        Interval(start=0, end=100),
        Interval(start=200, end=300),
        Interval(start=400, end=500),
    ]

    reverse = list(complement[0:500:-1])
    assert reverse == list(reversed(forward))


# === Difference reverse tests ===


def test_difference_reverse():
    """Test that difference supports reverse iteration."""
    source = timeline(Interval(start=0, end=100), Interval(start=200, end=300))
    subtractor = timeline(Interval(start=50, end=250))

    diff = source - subtractor

    forward = list(diff[0:400])
    # [0, 50) and [250, 300)
    assert forward == [
        Interval(start=0, end=50),
        Interval(start=250, end=300),
    ]

    reverse = list(diff[0:400:-1])
    assert reverse == list(reversed(forward))


# === Filtered reverse tests ===


def test_filtered_reverse():
    """Test that filtered timelines support reverse iteration."""
    from calgebra import hours

    tl = timeline(
        Interval(start=0, end=1800),  # 30 min
        Interval(start=2000, end=6000),  # ~1.1 hr
        Interval(start=7000, end=15000),  # ~2.2 hr
    )

    long_events = tl & (hours >= 1)

    forward = list(long_events[0:20000])
    assert len(forward) == 2

    reverse = list(long_events[0:20000:-1])
    assert reverse == list(reversed(forward))


# === Transform reverse tests ===


def test_buffer_reverse():
    """Test that buffered timelines support reverse iteration."""
    tl = timeline(Interval(start=100, end=200), Interval(start=400, end=500))

    buffered = buffer(tl, before=10, after=20)

    forward = list(buffered[0:600])
    assert forward == [
        Interval(start=90, end=220),
        Interval(start=390, end=520),
    ]

    reverse = list(buffered[0:600:-1])
    assert reverse == list(reversed(forward))


def test_merge_within_reverse():
    """Test that merge_within supports reverse iteration."""
    tl = timeline(
        Interval(start=0, end=100),
        Interval(start=110, end=200),  # Gap of 10
        Interval(start=300, end=400),  # Gap of 100
    )

    merged = merge_within(tl, gap=50)

    forward = list(merged[0:500])
    # First two should merge, third stays separate
    assert forward == [
        Interval(start=0, end=200),
        Interval(start=300, end=400),
    ]

    reverse = list(merged[0:500:-1])
    assert reverse == list(reversed(forward))


# === Recurrence reverse tests ===


def test_recurrence_reverse_requires_end_bound():
    """Test that reverse iteration on recurrence requires end bound."""
    mondays = recurring(freq="weekly", day="monday", tz="UTC")

    # Some start (Monday Jan 6, 2025)
    jan6 = int(datetime(2025, 1, 6, tzinfo=timezone.utc).timestamp())

    # Forward works with just start
    forward = list(islice(mondays[jan6:], 3))
    assert len(forward) == 3

    # Reverse requires end
    with pytest.raises(ValueError, match="Reverse iteration requires finite end"):
        list(mondays[::-1])


def test_recurrence_reverse_basic():
    """Test basic reverse iteration on recurring patterns."""
    mondays = recurring(freq="weekly", day="monday", tz="UTC")

    # Monday Jan 6, 2025
    jan6 = int(datetime(2025, 1, 6, tzinfo=timezone.utc).timestamp())
    # Feb 10, 2025
    feb10 = int(datetime(2025, 2, 10, tzinfo=timezone.utc).timestamp())

    forward = list(mondays[jan6:feb10])
    reverse = list(mondays[jan6:feb10:-1])

    assert len(forward) == len(reverse)
    assert reverse == list(reversed(forward))


def test_recurrence_last_n_pattern():
    """Test 'last N occurrences' pattern with reverse iteration."""
    daily = recurring(freq="daily", start=9 * HOUR, duration=HOUR, tz="UTC")

    # Get last 5 days before a timestamp
    now = int(datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc).timestamp())
    some_start = now - 30 * DAY

    last_5 = list(islice(daily[some_start:now:-1], 5))
    assert len(last_5) == 5

    # Should be in reverse chronological order
    for i in range(len(last_5) - 1):
        assert last_5[i].start > last_5[i + 1].start


# === Flatten reverse tests ===


def test_flatten_reverse():
    """Test that flatten supports reverse iteration."""
    tl1 = timeline(Interval(start=0, end=100), Interval(start=50, end=150))
    tl2 = timeline(Interval(start=200, end=300))

    combined = tl1 | tl2
    flattened = flatten(combined)

    forward = list(flattened[0:400])
    assert forward == [
        Interval(start=0, end=150),
        Interval(start=200, end=300),
    ]

    reverse = list(flattened[0:400:-1])
    assert reverse == list(reversed(forward))


# === Day of week / time of day reverse tests ===


def test_day_of_week_reverse():
    """Test reverse iteration on day_of_week patterns."""
    weekdays = day_of_week(
        ["monday", "tuesday", "wednesday", "thursday", "friday"], tz="UTC"
    )

    # One week window
    jan6 = int(datetime(2025, 1, 6, tzinfo=timezone.utc).timestamp())
    jan13 = int(datetime(2025, 1, 13, tzinfo=timezone.utc).timestamp())

    forward = list(weekdays[jan6:jan13])
    reverse = list(weekdays[jan6:jan13:-1])

    # Should have 5 weekdays
    assert len(forward) == 1  # day_of_week returns flattened, so contiguous days merge
    assert reverse == list(reversed(forward))


def test_composed_reverse():
    """Test reverse iteration on composed time windows."""
    weekdays = day_of_week(
        ["monday", "tuesday", "wednesday", "thursday", "friday"], tz="UTC"
    )
    work_hours = time_of_day(start=9 * HOUR, duration=8 * HOUR, tz="UTC")
    business_hours = weekdays & work_hours

    # One week window
    jan6 = int(datetime(2025, 1, 6, tzinfo=timezone.utc).timestamp())
    jan13 = int(datetime(2025, 1, 13, tzinfo=timezone.utc).timestamp())

    forward = list(business_hours[jan6:jan13])
    reverse = list(business_hours[jan6:jan13:-1])

    assert len(forward) > 0
    assert reverse == list(reversed(forward))


# === Empty results tests ===


def test_reverse_empty_result():
    """Test reverse iteration on empty results."""
    tl = timeline()

    result = list(tl[0:100:-1])
    assert result == []


def test_reverse_single_interval():
    """Test reverse iteration with single interval."""
    tl = timeline(Interval(start=50, end=100))

    result = list(tl[0:200:-1])
    assert result == [Interval(start=50, end=100)]


# === GCSA Calendar reverse tests ===


def test_gcsa_calendar_reverse_requires_end_bound():
    """Test that reverse iteration on Calendar requires end bound."""
    from unittest.mock import MagicMock

    from calgebra.gcsa import Calendar

    # Create mock calendar
    mock_client = MagicMock()
    mock_client.get_calendar.return_value = MagicMock(timezone="UTC")
    mock_client.get_events.return_value = iter([])

    cal = Calendar("test@example.com", "Test Calendar", client=mock_client)

    with pytest.raises(ValueError, match="Reverse iteration on Calendar requires"):
        list(cal[::-1])


def test_gcsa_calendar_reverse_with_mock():
    """Test reverse iteration on Calendar with mocked events."""
    from unittest.mock import MagicMock

    from calgebra.gcsa import Calendar

    # Create mock events
    mock_event1 = MagicMock()
    mock_event1.id = "event1"
    mock_event1.summary = "First Event"
    mock_event1.description = None
    mock_event1.start = datetime(2025, 1, 10, 10, 0, tzinfo=timezone.utc)
    mock_event1.end = datetime(2025, 1, 10, 11, 0, tzinfo=timezone.utc)
    mock_event1.timezone = "UTC"
    mock_event1.recurring_event_id = None
    mock_event1.reminders = []
    mock_event1.default_reminders = True

    mock_event2 = MagicMock()
    mock_event2.id = "event2"
    mock_event2.summary = "Second Event"
    mock_event2.description = None
    mock_event2.start = datetime(2025, 1, 20, 14, 0, tzinfo=timezone.utc)
    mock_event2.end = datetime(2025, 1, 20, 15, 0, tzinfo=timezone.utc)
    mock_event2.timezone = "UTC"
    mock_event2.recurring_event_id = None
    mock_event2.reminders = []
    mock_event2.default_reminders = True

    # Create mock calendar
    mock_client = MagicMock()
    mock_client.get_calendar.return_value = MagicMock(timezone="UTC")

    # Return events for any time window query
    mock_client.get_events.return_value = iter([mock_event1, mock_event2])

    cal = Calendar("test@example.com", "Test Calendar", client=mock_client)

    # Query window
    jan1 = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    feb1 = int(datetime(2025, 2, 1, tzinfo=timezone.utc).timestamp())

    # Forward iteration
    forward = list(cal[jan1:feb1])
    assert len(forward) == 2
    assert forward[0].summary == "First Event"
    assert forward[1].summary == "Second Event"

    # For reverse, we need to reset the mock to return events again
    mock_client.get_events.return_value = iter([mock_event1, mock_event2])

    # Reverse iteration
    reverse = list(cal[jan1:feb1:-1])
    assert len(reverse) == 2
    assert reverse[0].summary == "Second Event"
    assert reverse[1].summary == "First Event"

