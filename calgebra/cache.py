"""Caching wrapper for timelines with TTL-based expiration.

This module provides a cached() wrapper that caches results from slow upstream
timelines (e.g., Google Calendar) with TTL-based expiration. Supports partial
cache hits, boundary stitching, and efficient eviction.
"""

import heapq
import threading
from collections.abc import Iterable
from dataclasses import dataclass, replace
from time import monotonic
from typing import Any, cast

from typing_extensions import override

from calgebra.core import Timeline
from calgebra.interval import Interval, IvlOut
from calgebra.mutable.memory import MemoryTimeline, timeline


@dataclass(frozen=True, kw_only=True)
class CoverInterval(Interval):
    """Interval tracking a cached time range with creation timestamp for TTL."""

    created: float


class CachedTimeline(Timeline[IvlOut]):
    """Timeline wrapper that caches results with TTL-based expiration.

    Maintains two internal timelines:
    - sink: Cached intervals from the source
    - cover: CoverIntervals tracking which time ranges are cached

    On query:
    1. Evict expired cover segments
    2. Find gaps (uncached ranges) via set difference
    3. Fill gaps from source, stitching at boundaries
    4. Serve from sink
    """

    def __init__(
        self,
        source: Timeline[IvlOut],
        ttl: float,
        key: str | tuple[str, ...] = "id",
    ):
        """Initialize a cached timeline.

        Args:
            source: Upstream timeline to cache
            ttl: Time-to-live in seconds for cached segments
            key: Field name(s) for deduplication/stitching.
                 Default "id". Ignored for mask timelines.
        """
        self.source = source
        self.ttl = ttl

        # Key fields for stitching (None for mask timelines)
        if source._is_mask:
            self._key_fields: tuple[str, ...] | None = None
        else:
            self._key_fields = (key,) if isinstance(key, str) else tuple(key)

        # Track if we've validated key fields
        self._key_validated = False

        # Cached intervals storage
        self._sink: MemoryTimeline = MemoryTimeline()

        # Cover tracking - which ranges we've fetched
        self._cover: MemoryTimeline = MemoryTimeline()

        # Expiry heap: (expires_at, cover_interval)
        self._expiry_heap: list[tuple[float, CoverInterval]] = []

        # Serialize evict/fill/stitch so concurrent fetches don't corrupt state
        self._lock = threading.Lock()

    @property
    @override
    def _is_mask(self) -> bool:
        return self.source._is_mask

    @override
    def fetch(
        self, start: int | None, end: int | None, *, reverse: bool = False
    ) -> Iterable[IvlOut]:
        """Fetch intervals, using cache where available.

        Args:
            start: Start timestamp (inclusive), must not be None
            end: End timestamp (exclusive), must not be None
            reverse: If True, yield intervals in reverse chronological order

        Returns:
            Cached or freshly fetched intervals

        Raises:
            ValueError: If start or end is None (unbounded queries not supported)
        """
        if start is None or end is None:
            raise ValueError(
                "Cached timelines require bounded queries.\n"
                "Use: cached_timeline[start:end] with explicit bounds."
            )

        with self._lock:
            # 1. Evict expired covers
            self._evict_expired()

            # 2. Find gaps (query range minus known cover) and fill from source
            query = timeline(Interval(start=start, end=end))
            for gap in (query - self._cover).fetch(start, end):
                self._fill_gap(cast(int, gap.start), cast(int, gap.end))

            # 3. Serve from sink (materialized while holding the lock)
            result = list(self._fetch_sink(start, end, reverse=reverse))

        yield from result

    def _fill_gap(self, gap_start: int, gap_end: int) -> None:
        """Fetch gap from source and add to cache."""
        # Fetch from source, clipping to gap bounds
        # This ensures intervals don't extend beyond the covered range
        # and enables proper stitching at boundaries
        for ivl in self.source.fetch(gap_start, gap_end):
            # Validate key fields on first interval (lazy validation)
            if not self._key_validated and self._key_fields is not None:
                self._get_key(ivl)  # Raises TypeError if missing
                self._key_validated = True

            # Clip interval to gap bounds
            clipped_start = ivl.start
            clipped_end = ivl.end

            if ivl.start is not None and ivl.start < gap_start:
                clipped_start = gap_start
            if ivl.end is not None and ivl.end > gap_end:
                clipped_end = gap_end

            # Only add if there's content after clipping
            if clipped_start is not None and clipped_end is not None:
                if clipped_start >= clipped_end:
                    continue

            if clipped_start != ivl.start or clipped_end != ivl.end:
                ivl = replace(ivl, start=clipped_start, end=clipped_end)

            self._sink.add(ivl)

        # Record coverage
        cover = CoverInterval(start=gap_start, end=gap_end, created=monotonic())
        self._cover.add(cover)
        heapq.heappush(self._expiry_heap, (cover.created + self.ttl, cover))

        # Stitch at boundaries
        self._stitch_at(gap_start)
        self._stitch_at(gap_end)

    def _stitch_at(self, point: int) -> None:
        """Stitch intervals at a boundary point."""
        if self._key_fields is None:
            # Mask timeline - no stitching needed
            return

        # Find intervals ending at point (left side)
        left = [ivl for ivl in self._sink.overlapping(point - 1) if ivl.end == point]

        # Find intervals starting at point (right side)
        right = [ivl for ivl in self._sink.overlapping(point) if ivl.start == point]

        if not left or not right:
            return

        # Match by key and merge
        left_by_key = {self._get_key(ivl): ivl for ivl in left}
        right_by_key = {self._get_key(ivl): ivl for ivl in right}

        for key in left_by_key.keys() & right_by_key.keys():
            if key is None:
                continue
            l_ivl, r_ivl = left_by_key[key], right_by_key[key]
            merged = replace(l_ivl, end=r_ivl.end)
            self._sink.remove(l_ivl)
            self._sink.remove(r_ivl)
            self._sink.add(merged)

    def _get_key(self, ivl: Interval) -> tuple[Any, ...] | None:
        """Extract deduplication key from interval."""
        if self._key_fields is None:
            return None

        try:
            return tuple(getattr(ivl, f) for f in self._key_fields)
        except AttributeError as e:
            raise TypeError(
                f"Cannot cache {type(ivl).__name__}: missing key field '{e.name}'.\n"
                f"Expected: {self._key_fields}\n"
                f"Hint: cached(..., key='your_id_field')"
            ) from e

    def _fetch_sink(
        self, start: int, end: int, reverse: bool = False
    ) -> Iterable[IvlOut]:
        """Fetch from sink with optional reverse."""
        # MemoryTimeline.fetch() handles filtering and ordering
        yield from self._sink.fetch(start, end, reverse=reverse)

    def _evict_expired(self) -> None:
        """Remove expired cover segments and their cached data."""
        now = monotonic()
        while self._expiry_heap and self._expiry_heap[0][0] <= now:
            _, cover = heapq.heappop(self._expiry_heap)

            # Cover might have been removed already (shouldn't happen with TTL-only)
            try:
                self._cover.remove(cover)
            except ValueError:
                continue

            # Purge sink for this cover range
            # (cover always has bounded start/end since we create them that way)
            self._purge_sink(cast(int, cover.start), cast(int, cover.end))

    def _purge_sink(self, start: int, end: int) -> None:
        """Remove/trim intervals within [start, end) from sink."""
        # Collect affected intervals (unclipped)
        affected = list(self._sink.fetch(start, end))

        # Remove each affected interval and re-add trimmed fragments
        for ivl in affected:
            self._sink.remove(ivl)

            # Re-insert trimmed fragments outside the purge range
            if ivl.start is not None and ivl.start < start:
                left = replace(ivl, end=start)
                self._sink.add(left)
            if ivl.end is not None and ivl.end > end:
                right = replace(ivl, start=end)
                self._sink.add(right)


def cached(
    source: Timeline[IvlOut],
    ttl: float,
    key: str | tuple[str, ...] = "id",
) -> CachedTimeline[IvlOut]:
    """Wrap a timeline with TTL-based caching.

    Creates a cached timeline that stores results from the source and serves
    them from cache on subsequent queries. Supports partial cache hits -
    only uncached portions of a query range are fetched from source.

    Args:
        source: Upstream timeline to cache (e.g., Google Calendar)
        ttl: Time-to-live in seconds for cached segments
        key: Field name(s) for interval deduplication. Default "id".
             Use "uid" for iCalendar sources.
             Ignored for mask timelines.

    Returns:
        CachedTimeline wrapping the source

    Example:
        >>> from calgebra import cached, at_tz
        >>> from calgebra.gcsa import calendars
        >>>
        >>> cals = calendars()
        >>> my_cal = cached(cals[0], ttl=600)  # 10 minute cache
        >>>
        >>> at = at_tz("US/Pacific")
        >>> events = list(my_cal[at("2025-01-01"):at("2025-02-01")])
        >>> # Subsequent queries in this range hit cache
        >>> events2 = list(my_cal[at("2025-01-15"):at("2025-01-20")])
    """
    return CachedTimeline(source, ttl, key)
