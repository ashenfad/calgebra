"""Tests for the caching module."""

import time
from dataclasses import dataclass
from typing import Any

import pytest
from typing_extensions import override

from calgebra import Interval, Timeline, cached, timeline
from calgebra.cache import CachedTimeline, CoverInterval


def sink_items(cached_tl: CachedTimeline) -> list:
    """Helper to get all items from the sink as a list."""
    return list(cached_tl._sink.fetch(None, None))


def cover_items(cached_tl: CachedTimeline) -> list:
    """Helper to get all cover intervals as a list."""
    return list(cached_tl._cover.fetch(None, None))


@dataclass(frozen=True, kw_only=True)
class Event(Interval):
    """Test interval with id for stitching."""

    id: str
    title: str = ""


@dataclass(frozen=True, kw_only=True)
class CustomEvent(Interval):
    """Test interval with custom key field."""

    uid: str
    name: str = ""


class TrackingTimeline(Timeline[Event]):
    """Timeline that tracks fetch calls for testing."""

    def __init__(self, source: Timeline[Event]):
        self.source = source
        self.fetch_count = 0
        self.fetch_ranges: list[tuple[int | None, int | None]] = []

    @override
    def fetch(
        self, start: int | None, end: int | None, *, reverse: bool = False
    ) -> Any:
        self.fetch_count += 1
        self.fetch_ranges.append((start, end))
        yield from self.source.fetch(start, end, reverse=reverse)


class TestCachedTimelineBasics:
    """Basic caching functionality tests."""

    def test_cache_hit_avoids_source_fetch(self):
        """Subset queries should hit cache without fetching from source."""
        source = timeline(
            Event(start=100, end=200, id="e1"),
            Event(start=300, end=400, id="e2"),
        )
        tracked = TrackingTimeline(source)
        cached_tl = cached(tracked, ttl=60)

        # First query populates cache
        list(cached_tl[100:400])
        assert tracked.fetch_count == 1

        # Subset query should hit cache
        list(cached_tl[150:350])
        assert tracked.fetch_count == 1  # No new fetch

    def test_cache_miss_fetches_from_source(self):
        """Disjoint queries should fetch from source."""
        source = timeline(
            Event(start=100, end=200, id="e1"),
            Event(start=500, end=600, id="e2"),
        )
        tracked = TrackingTimeline(source)
        cached_tl = cached(tracked, ttl=60)

        # First query
        list(cached_tl[100:200])
        assert tracked.fetch_count == 1

        # Disjoint query should fetch
        list(cached_tl[500:600])
        assert tracked.fetch_count == 2

    def test_partial_cache_hit_fetches_only_gaps(self):
        """Overlapping queries should only fetch uncached portions."""
        source = timeline(
            Event(start=100, end=200, id="e1"),
            Event(start=300, end=400, id="e2"),
            Event(start=500, end=600, id="e3"),
        )
        tracked = TrackingTimeline(source)
        cached_tl = cached(tracked, ttl=60)

        # Cache [100:400]
        list(cached_tl[100:400])
        assert tracked.fetch_count == 1
        assert tracked.fetch_ranges[-1] == (100, 400)

        # Query [200:600] - should only fetch [400:600]
        list(cached_tl[200:600])
        assert tracked.fetch_count == 2
        assert tracked.fetch_ranges[-1] == (400, 600)

    def test_returns_correct_events(self):
        """Cached timeline should return correct events."""
        source = timeline(
            Event(start=100, end=200, id="e1", title="First"),
            Event(start=300, end=400, id="e2", title="Second"),
        )
        cached_tl = cached(source, ttl=60)

        result = list(cached_tl[100:400])
        assert len(result) == 2
        assert result[0].id == "e1"
        assert result[1].id == "e2"

    def test_respects_query_bounds(self):
        """Results should be filtered to query bounds."""
        source = timeline(
            Event(start=100, end=200, id="e1"),
            Event(start=300, end=400, id="e2"),
            Event(start=500, end=600, id="e3"),
        )
        cached_tl = cached(source, ttl=60)

        # Query subset
        result = list(cached_tl[250:450])
        assert len(result) == 1
        assert result[0].id == "e2"


class TestCachedTimelineStitching:
    """Tests for boundary stitching of split intervals."""

    def test_stitches_interval_spanning_cache_boundary(self):
        """Intervals split across cache boundaries should be stitched."""
        source = timeline(
            Event(start=100, end=200, id="e1"),
            Event(start=250, end=450, id="e2"),  # Spans boundary
            Event(start=500, end=600, id="e3"),
        )
        cached_tl = cached(source, ttl=60)

        # Cache first half
        list(cached_tl[100:350])
        assert len(sink_items(cached_tl)) == 2  # e1, partial e2

        # Cache second half - should stitch e2
        list(cached_tl[350:600])
        assert len(sink_items(cached_tl)) == 3  # e1, stitched e2, e3

        # Verify e2 is stitched
        e2 = [e for e in sink_items(cached_tl) if e.id == "e2"][0]
        assert e2.start == 250
        assert e2.end == 450

    def test_stitches_multiple_intervals_at_boundary(self):
        """Multiple intervals at same boundary should all be stitched."""
        source = timeline(
            Event(start=200, end=400, id="e1"),  # Spans 300
            Event(start=250, end=350, id="e2"),  # Also spans 300
        )
        cached_tl = cached(source, ttl=60)

        list(cached_tl[200:300])
        list(cached_tl[300:400])

        # Both should be stitched
        items = sink_items(cached_tl)
        assert len(items) == 2
        e1 = [e for e in items if e.id == "e1"][0]
        e2 = [e for e in items if e.id == "e2"][0]
        assert e1.start == 200 and e1.end == 400
        assert e2.start == 250 and e2.end == 350

    def test_no_stitch_for_different_ids(self):
        """Intervals with different ids at boundary should not be stitched."""
        source = timeline(
            Event(start=200, end=300, id="e1"),
            Event(start=300, end=400, id="e2"),
        )
        cached_tl = cached(source, ttl=60)

        list(cached_tl[200:300])
        list(cached_tl[300:400])

        # Should remain separate
        assert len(sink_items(cached_tl)) == 2

    def test_stitch_across_three_segments(self):
        """Interval spanning three cache segments should stitch correctly."""
        source = timeline(
            Event(start=100, end=500, id="e1"),
        )
        cached_tl = cached(source, ttl=60)

        # Cache in three parts
        list(cached_tl[100:200])
        list(cached_tl[200:400])
        list(cached_tl[400:500])

        # Should be one stitched interval
        items = sink_items(cached_tl)
        assert len(items) == 1
        e1 = items[0]
        assert e1.start == 100
        assert e1.end == 500


class TestCachedTimelineTTL:
    """Tests for TTL-based expiration."""

    def test_expired_cover_triggers_refetch(self):
        """Expired cache segments should be refetched."""
        source = timeline(
            Event(start=100, end=200, id="e1"),
        )
        tracked = TrackingTimeline(source)
        cached_tl = cached(tracked, ttl=0.05)  # 50ms TTL

        # Populate cache
        list(cached_tl[100:200])
        assert tracked.fetch_count == 1

        # Wait for expiration
        time.sleep(0.1)

        # Should refetch
        list(cached_tl[100:200])
        assert tracked.fetch_count == 2

    def test_non_expired_cover_uses_cache(self):
        """Non-expired cache segments should be used."""
        source = timeline(
            Event(start=100, end=200, id="e1"),
        )
        tracked = TrackingTimeline(source)
        cached_tl = cached(tracked, ttl=1.0)  # 1 second TTL

        # Populate cache
        list(cached_tl[100:200])
        assert tracked.fetch_count == 1

        # Immediate re-query should use cache
        list(cached_tl[100:200])
        assert tracked.fetch_count == 1

    def test_partial_expiration_fetches_expired_portion(self):
        """Only expired portions should be refetched."""
        source = timeline(
            Event(start=100, end=500, id="e1"),
        )
        tracked = TrackingTimeline(source)
        cached_tl = cached(tracked, ttl=0.15)

        # Cache first segment
        list(cached_tl[100:300])

        # Wait a bit, cache second segment
        time.sleep(0.1)
        list(cached_tl[300:500])

        # Wait for first segment to expire (but not second)
        time.sleep(0.1)

        tracked.fetch_ranges.clear()
        tracked.fetch_count = 0

        # Query spanning both - should only fetch expired portion
        list(cached_tl[100:500])

        # Should have fetched the expired [100:300] portion
        assert tracked.fetch_count == 1
        assert tracked.fetch_ranges[0] == (100, 300)


class TestCachedTimelinePurge:
    """Tests for purge and fracturing on eviction."""

    def test_purge_removes_fully_covered_interval(self):
        """Intervals fully within purged range should be removed."""
        source = timeline(
            Event(start=100, end=200, id="e1"),
            Event(start=300, end=400, id="e2"),
        )
        cached_tl = cached(source, ttl=0.05)

        list(cached_tl[100:200])
        list(cached_tl[300:400])
        assert len(sink_items(cached_tl)) == 2

        # Wait for expiration
        time.sleep(0.1)

        # Trigger eviction with any query
        list(cached_tl[500:600])

        # Both should be purged
        assert len(sink_items(cached_tl)) == 0

    def test_purge_fractures_spanning_interval(self):
        """Intervals spanning purge boundary should be fractured."""
        source = timeline(
            Event(start=100, end=500, id="e1"),
        )
        cached_tl = cached(source, ttl=0.15)

        # Cache first segment
        list(cached_tl[100:300])

        # Cache second segment (stitches)
        time.sleep(0.1)
        list(cached_tl[300:500])

        # Verify stitched
        items = sink_items(cached_tl)
        assert len(items) == 1
        assert items[0].end == 500

        # Wait for first segment to expire
        time.sleep(0.1)

        # Query second segment (triggers eviction of first)
        list(cached_tl[400:500])

        # Should have fractured - only [300:500] remains
        items = sink_items(cached_tl)
        assert len(items) == 1
        e1 = items[0]
        assert e1.start == 300
        assert e1.end == 500


class TestCachedTimelineKeyField:
    """Tests for key field configuration."""

    def test_default_key_is_id(self):
        """Default key field should be 'id'."""
        source = timeline(Event(start=100, end=200, id="e1"))
        cached_tl = cached(source, ttl=60)
        assert cached_tl._key_fields == ("id",)

    def test_custom_key_field(self):
        """Custom key field should be used."""
        source = timeline(CustomEvent(start=100, end=200, uid="u1"))
        cached_tl = cached(source, ttl=60, key="uid")
        assert cached_tl._key_fields == ("uid",)

    def test_compound_key_field(self):
        """Compound key fields should work."""

        @dataclass(frozen=True, kw_only=True)
        class MultiKeyEvent(Interval):
            source_id: str
            event_id: str

        source = timeline(
            MultiKeyEvent(start=100, end=200, source_id="s1", event_id="e1")
        )
        cached_tl = cached(source, ttl=60, key=("source_id", "event_id"))
        assert cached_tl._key_fields == ("source_id", "event_id")

    def test_missing_key_field_raises(self):
        """Missing key field should raise TypeError."""

        @dataclass(frozen=True, kw_only=True)
        class NoIdEvent(Interval):
            name: str

        source = timeline(NoIdEvent(start=100, end=200, name="test"))
        cached_tl = cached(source, ttl=60)

        with pytest.raises(TypeError, match="missing key field"):
            list(cached_tl[100:200])

    def test_stitching_uses_custom_key(self):
        """Stitching should use the configured key field."""
        source = timeline(
            CustomEvent(start=200, end=400, uid="u1", name="Test"),
        )
        cached_tl = cached(source, ttl=60, key="uid")

        list(cached_tl[200:300])
        list(cached_tl[300:400])

        # Should be stitched using uid
        items = sink_items(cached_tl)
        assert len(items) == 1
        assert items[0].start == 200
        assert items[0].end == 400


class TestCachedTimelineMask:
    """Tests for mask timeline handling."""

    def test_mask_timeline_no_key_required(self):
        """Mask timelines should not require a key field."""
        from calgebra import HOUR, time_of_day

        work_hours = time_of_day(start=9 * HOUR, duration=8 * HOUR, tz="UTC")
        cached_tl = cached(work_hours, ttl=60)

        assert cached_tl._is_mask is True
        assert cached_tl._key_fields is None

        # Should work without error
        result = list(cached_tl[0:86400])
        assert len(result) == 1

    def test_mask_timeline_caches_correctly(self):
        """Mask timelines should cache and serve from cache."""
        from calgebra import HOUR, time_of_day

        work_hours = time_of_day(start=9 * HOUR, duration=8 * HOUR, tz="UTC")

        class TrackingMask(Timeline[Interval]):
            def __init__(self, source: Timeline[Interval]):
                self.source = source
                self.fetch_count = 0

            @property
            def _is_mask(self) -> bool:
                return True

            @override
            def fetch(
                self, start: int | None, end: int | None, *, reverse: bool = False
            ) -> Any:
                self.fetch_count += 1
                yield from self.source.fetch(start, end, reverse=reverse)

        tracked = TrackingMask(work_hours)
        cached_tl = cached(tracked, ttl=60)

        list(cached_tl[0:86400])
        assert tracked.fetch_count == 1

        list(cached_tl[0:86400])
        assert tracked.fetch_count == 1  # Cache hit


class TestCachedTimelineBounds:
    """Tests for bounded query requirement."""

    def test_unbounded_start_raises(self):
        """Unbounded start should raise ValueError."""
        source = timeline(Event(start=100, end=200, id="e1"))
        cached_tl = cached(source, ttl=60)

        with pytest.raises(ValueError, match="bounded queries"):
            list(cached_tl[None:200])

    def test_unbounded_end_raises(self):
        """Unbounded end should raise ValueError."""
        source = timeline(Event(start=100, end=200, id="e1"))
        cached_tl = cached(source, ttl=60)

        with pytest.raises(ValueError, match="bounded queries"):
            list(cached_tl[100:None])

    def test_both_unbounded_raises(self):
        """Both bounds unbounded should raise ValueError."""
        source = timeline(Event(start=100, end=200, id="e1"))
        cached_tl = cached(source, ttl=60)

        with pytest.raises(ValueError, match="bounded queries"):
            list(cached_tl[None:None])


class TestCachedTimelineReverse:
    """Tests for reverse iteration."""

    def test_reverse_iteration_works(self):
        """Reverse iteration should return events in reverse order."""
        source = timeline(
            Event(start=100, end=200, id="e1"),
            Event(start=300, end=400, id="e2"),
            Event(start=500, end=600, id="e3"),
        )
        cached_tl = cached(source, ttl=60)

        result = list(cached_tl[100:600:-1])
        assert len(result) == 3
        assert result[0].id == "e3"
        assert result[1].id == "e2"
        assert result[2].id == "e1"


class TestCoverInterval:
    """Tests for CoverInterval class."""

    def test_cover_interval_creation(self):
        """CoverInterval should store start, end, and created."""
        cover = CoverInterval(start=100, end=200, created=12345.0)
        assert cover.start == 100
        assert cover.end == 200
        assert cover.created == 12345.0

    def test_cover_interval_hashable(self):
        """CoverInterval should be hashable."""
        cover = CoverInterval(start=100, end=200, created=12345.0)
        hash(cover)  # Should not raise

    def test_cover_interval_equality(self):
        """CoverInterval equality should check all fields."""
        cover1 = CoverInterval(start=100, end=200, created=12345.0)
        cover2 = CoverInterval(start=100, end=200, created=12345.0)
        cover3 = CoverInterval(start=100, end=200, created=99999.0)

        assert cover1 == cover2
        assert cover1 != cover3


class TestOverlappingMethod:
    """Tests for the overlapping() method on Timeline."""

    def test_overlapping_returns_containing_intervals(self):
        """overlapping() should return intervals containing the point."""
        t = timeline(
            Interval(start=100, end=300),
            Interval(start=200, end=400),
            Interval(start=500, end=600),
        )

        result = list(t.overlapping(250))
        assert len(result) == 2
        assert result[0].start == 100
        assert result[1].start == 200

    def test_overlapping_single_interval(self):
        """overlapping() with single containing interval."""
        t = timeline(
            Interval(start=100, end=300),
            Interval(start=500, end=600),
        )

        result = list(t.overlapping(150))
        assert len(result) == 1
        assert result[0].start == 100

    def test_overlapping_no_match(self):
        """overlapping() with no containing intervals returns empty."""
        t = timeline(
            Interval(start=100, end=200),
            Interval(start=300, end=400),
        )

        result = list(t.overlapping(250))
        assert len(result) == 0

    def test_overlapping_at_boundary(self):
        """overlapping() at interval boundary."""
        t = timeline(
            Interval(start=100, end=200),
            Interval(start=200, end=300),
        )

        # At 200: first ends (exclusive), second starts
        result = list(t.overlapping(200))
        assert len(result) == 1
        assert result[0].start == 200

    def test_overlapping_returns_unclipped(self):
        """overlapping() should return full unclipped intervals."""
        t = timeline(
            Interval(start=100, end=500),
        )

        # Query at point 250
        result = list(t.overlapping(250))
        assert len(result) == 1
        # Should be full interval, not clipped
        assert result[0].start == 100
        assert result[0].end == 500


class TestCachedTimelineICalLike:
    """Tests simulating iCalendar-style usage with uid field."""

    @dataclass(frozen=True, kw_only=True)
    class ICalLikeEvent(Interval):
        """Simulates ICalEvent structure."""

        uid: str
        summary: str = ""
        description: str | None = None

    def test_ical_style_caching_with_uid(self):
        """iCal-style events should cache and stitch using uid."""
        source = timeline(
            self.ICalLikeEvent(
                start=100, end=400, uid="event-001", summary="Long Meeting"
            ),
            self.ICalLikeEvent(
                start=500, end=600, uid="event-002", summary="Short Meeting"
            ),
        )
        cached_tl = cached(source, ttl=60, key="uid")

        # Query first half
        list(cached_tl[100:250])

        # Query second half - should stitch event-001
        list(cached_tl[250:600])

        # Verify stitching
        items = sink_items(cached_tl)
        assert len(items) == 2
        event1 = [e for e in items if e.uid == "event-001"][0]
        assert event1.start == 100
        assert event1.end == 400
        assert event1.summary == "Long Meeting"

    def test_ical_style_preserves_metadata_after_stitch(self):
        """Stitched iCal events should preserve all metadata."""
        source = timeline(
            self.ICalLikeEvent(
                start=200,
                end=400,
                uid="uid-123",
                summary="Team Sync",
                description="Weekly team sync meeting",
            ),
        )
        cached_tl = cached(source, ttl=60, key="uid")

        list(cached_tl[200:300])
        list(cached_tl[300:400])

        # Verify stitched event has all metadata
        items = sink_items(cached_tl)
        assert len(items) == 1
        event = items[0]
        assert event.uid == "uid-123"
        assert event.summary == "Team Sync"
        assert event.description == "Weekly team sync meeting"
        assert event.start == 200
        assert event.end == 400


class TestCachedTimelineMultipleGaps:
    """Tests for handling multiple gaps in a single query."""

    def test_fills_multiple_gaps(self):
        """Query spanning multiple gaps should fill all of them."""
        source = timeline(
            Event(start=100, end=150, id="e1"),
            Event(start=250, end=300, id="e2"),
            Event(start=400, end=450, id="e3"),
        )
        tracked = TrackingTimeline(source)
        cached_tl = cached(tracked, ttl=60)

        # Cache middle segment only
        list(cached_tl[200:350])
        assert tracked.fetch_count == 1

        tracked.fetch_ranges.clear()

        # Query entire range - should fill two gaps
        list(cached_tl[50:500])

        # Should have fetched [50:200] and [350:500]
        assert len(tracked.fetch_ranges) == 2
        fetched_ranges = set(tracked.fetch_ranges)
        assert (50, 200) in fetched_ranges
        assert (350, 500) in fetched_ranges

    def test_cover_tracks_all_segments(self):
        """Cover should track all fetched segments."""
        source = timeline(
            Event(start=100, end=200, id="e1"),
        )
        cached_tl = cached(source, ttl=60)

        list(cached_tl[0:100])
        list(cached_tl[200:300])
        list(cached_tl[400:500])

        cover_ranges = [(c.start, c.end) for c in cover_items(cached_tl)]
        assert (0, 100) in cover_ranges
        assert (200, 300) in cover_ranges
        assert (400, 500) in cover_ranges
