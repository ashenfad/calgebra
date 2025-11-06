import bisect
import heapq
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import replace
from datetime import datetime
from functools import reduce
from typing import Any, Generic, Literal, cast, overload

from typing_extensions import override

from calgebra.interval import NEG_INF, POS_INF, Interval, IvlIn, IvlOut


class Timeline(ABC, Generic[IvlOut]):

    @abstractmethod
    def fetch(self, start: int | None, end: int | None) -> Iterable[IvlOut]:
        """Yield events ordered by start/end within the provided bounds."""
        pass

    @property
    def _is_mask(self) -> bool:
        """True if this timeline only yields mask Interval objects (no metadata).

        When a timeline is marked as mask, intersections can optimize by
        auto-flattening or using asymmetric behavior to preserve metadata
        from rich sources.
        """
        return False

    def __getitem__(self, item: slice) -> Iterable[IvlOut]:
        start = self._coerce_bound(item.start, "start")
        end = self._coerce_bound(item.stop, "end")

        # Automatically clip intervals to query bounds via intersection with solid
        # timeline
        # This ensures correct behavior for aggregations and set operations
        # Skip clipping if both bounds are unbounded (no clipping needed)
        if start is None and end is None:
            return self.fetch(start, end)
        # Cast solid to compatible type since intersection preserves self's type
        return (self & cast("Timeline[IvlOut]", solid)).fetch(start, end)

    def _coerce_bound(self, bound: Any, edge: Literal["start", "end"]) -> int | None:
        """Convert slice bounds to integer seconds (Unix timestamps).

        Accepts:
        - int: Passed through as-is (Unix timestamp)
        - datetime: Must be timezone-aware, converted to timestamp
        - None: Unbounded (passed through)

        Raises:
            TypeError: If bound is an unsupported type or naive datetime
        """
        if bound is None:
            return None
        if isinstance(bound, int):
            return bound
        if isinstance(bound, datetime):
            if bound.tzinfo is None:
                raise TypeError(
                    f"Timeline slice {edge} must be a timezone-aware datetime.\n"
                    f"Got naive datetime: {bound!r}\n"
                    f"Hint: Add timezone info:\n"
                    f"  dt = datetime(..., tzinfo=timezone.utc)\n"
                    f"  from zoneinfo import ZoneInfo\n"
                    f"  dt = datetime(..., tzinfo=ZoneInfo('US/Pacific'))"
                )
            return int(bound.timestamp())
        raise TypeError(
            f"Timeline slice {edge} must be int, timezone-aware datetime, or None.\n"
            f"Got {type(bound).__name__!r}: {bound!r}\n"
            f"Examples:\n"
            f"  timeline[start_ts:end_ts]  # int (Unix seconds)\n"
            f"  timeline[datetime(2025,1,1,tzinfo=timezone.utc):]  "
            f"# timezone-aware datetime\n"
        )

    @overload
    def __or__(self, other: "Timeline[IvlOut]") -> "Timeline[IvlOut]": ...

    @overload
    def __or__(self, other: "Filter[Any]") -> "Timeline[IvlOut]": ...

    def __or__(self, other: "Timeline[IvlOut] | Filter[Any]") -> "Timeline[IvlOut]":
        if isinstance(other, Filter):
            raise TypeError(
                f"Cannot union (|) a Timeline with a Filter.\n"
                f"Got: Timeline | {type(other).__name__}\n"
                f"Hint: Use & to apply filters: timeline & (hours >= 2)\n"
                f"      Use | to combine timelines: timeline_a | timeline_b"
            )
        return Union(self, other)

    @overload
    def __and__(self, other: "Timeline[IvlOut]") -> "Timeline[IvlOut]": ...

    @overload
    def __and__(self, other: "Filter[IvlOut]") -> "Timeline[IvlOut]": ...

    def __and__(self, other: "Timeline[IvlOut] | Filter[IvlOut]") -> "Timeline[IvlOut]":
        if isinstance(other, Filter):
            return Filtered(self, other)
        return Intersection(self, other)

    def __sub__(self, other: "Timeline[IvlOut]") -> "Timeline[IvlOut]":
        return Difference(self, other)

    def __invert__(self) -> "Timeline[IvlOut]":
        return Complement(self)


class Filter(ABC, Generic[IvlIn]):

    @abstractmethod
    def apply(self, event: IvlIn) -> bool:
        pass

    def __getitem__(self, item: slice) -> Iterable[IvlIn]:
        raise NotImplementedError("Not supported for filters")

    @overload
    def __or__(self, other: "Filter[IvlIn]") -> "Filter[IvlIn]": ...

    @overload
    def __or__(self, other: "Timeline[Any]") -> "Filter[IvlIn]": ...

    def __or__(
        self, other: "Filter[IvlIn] | Timeline[Any]"
    ) -> "Filter[IvlIn] | Timeline[Any]":
        if isinstance(other, Timeline):
            raise TypeError(
                f"Cannot union (|) a Filter with a Timeline.\n"
                f"Got: {type(self).__name__} | Timeline\n"
                f"Hint: Use & to apply filters: timeline & (hours >= 2)\n"
                f"      Use | to combine filters: (hours >= 2) | (minutes < 30)"
            )
        return Or(self, other)

    @overload
    def __and__(self, other: "Filter[IvlIn]") -> "Filter[IvlIn]": ...

    @overload
    def __and__(self, other: "Timeline[IvlIn]") -> "Filter[IvlIn]": ...

    def __and__(
        self, other: "Filter[IvlIn] | Timeline[IvlIn]"
    ) -> "Filter[IvlIn] | Timeline[IvlIn]":
        if isinstance(other, Timeline):
            return Filtered(other, self)
        return And(self, other)


class Or(Filter[IvlIn]):
    def __init__(self, *filters: Filter[IvlIn]):
        super().__init__()
        self.filters: tuple[Filter[IvlIn], ...] = filters

    @override
    def apply(self, event: IvlIn) -> bool:
        return any(f.apply(event) for f in self.filters)


class And(Filter[IvlIn]):
    def __init__(self, *filters: Filter[IvlIn]):
        super().__init__()
        self.filters: tuple[Filter[IvlIn], ...] = filters

    @override
    def apply(self, event: IvlIn) -> bool:
        return all(f.apply(event) for f in self.filters)


class _SolidTimeline(Timeline[Interval]):
    """Internal timeline that yields query bounds as a single interval.

    Used for automatic clipping via intersection in Timeline.__getitem__.
    """

    @property
    @override
    def _is_mask(self) -> bool:
        return True

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Interval]:
        yield Interval(start=start, end=end)


# Singleton instance for clipping operations
solid: Timeline[Interval] = _SolidTimeline()


class Union(Timeline[IvlOut]):
    def __init__(self, *sources: Timeline[IvlOut]):
        self.sources: tuple[Timeline[IvlOut], ...] = sources

    @property
    @override
    def _is_mask(self) -> bool:
        """Union is mask only if all sources are mask."""
        return all(s._is_mask for s in self.sources)

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[IvlOut]:
        streams = [source.fetch(start, end) for source in self.sources]
        # Use finite properties for sorting to handle None (unbounded) values
        merged = heapq.merge(*streams, key=lambda e: (e.finite_start, e.finite_end))
        return merged


class Intersection(Timeline[IvlOut]):
    def __init__(self, *sources: Timeline[IvlOut]):
        flattened: list[Timeline[IvlOut]] = []
        for source in sources:
            if isinstance(source, Intersection):
                flattened.extend(source.sources)
            else:
                flattened.append(source)

        self.sources: tuple[Timeline[IvlOut], ...] = tuple(flattened)

    @property
    @override
    def _is_mask(self) -> bool:
        """Intersection is mask only if all sources are mask."""
        return all(s._is_mask for s in self.sources)

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[IvlOut]:
        """Compute intersection using a multi-way merge with sliding window.

        Algorithm: Maintains one "current" interval from each source and advances
        them in lockstep. When all current intervals overlap, yields a trimmed copy
        from sources (behavior depends on source types).

        Auto-flattening optimization:
        - All mask sources: Yields one interval per overlap (auto-flattened)
        - Mixed mask/rich: Yields only from rich sources (preserves metadata)
        - All rich sources: Yields from all sources (preserves metadata)

        Key invariant: overlap_start <= overlap_end means all sources have coverage.
        """
        if not self.sources:
            return ()

        # Determine behavior based on source types
        mask_sources = [s._is_mask for s in self.sources]
        all_mask = all(mask_sources)
        any_mask = any(mask_sources)

        # Get indices of sources to emit from
        if all_mask:
            # All mask: emit just one interval per overlap (auto-flatten)
            emit_indices = [0]
        elif any_mask:
            # Mixed: emit only from rich sources (preserve their metadata)
            emit_indices = [i for i, is_mask in enumerate(mask_sources) if not is_mask]
        else:
            # All rich: emit from all (current behavior)
            emit_indices = list(range(len(self.sources)))

        iterators = [iter(source.fetch(start, end)) for source in self.sources]

        def generate() -> Iterable[IvlOut]:
            # Initialize: get first interval from each source
            try:
                current = [next(iterator) for iterator in iterators]
            except StopIteration:
                return

            while True:
                # Find overlap region across all current intervals
                # Use finite properties to handle None (unbounded) values
                overlap_start = max(event.finite_start for event in current)
                overlap_end = min(event.finite_end for event in current)

                # If there's actual overlap, yield trimmed copy from selected sources
                if overlap_start <= overlap_end:
                    for idx in emit_indices:
                        # Convert sentinel values back to None for unbounded intervals
                        start_val = overlap_start if overlap_start != NEG_INF else None
                        end_val = overlap_end if overlap_end != POS_INF else None
                        yield replace(current[idx], start=start_val, end=end_val)

                # Advance any interval that ends at the overlap boundary
                cutoff = overlap_end
                advanced = False
                for idx, event in enumerate(current):
                    if event.finite_end == cutoff:
                        try:
                            current[idx] = next(iterators[idx])
                            advanced = True
                        except StopIteration:
                            return

                # If no interval advanced, we've exhausted all overlaps
                if not advanced:
                    return

        return generate()


class Filtered(Timeline[IvlOut]):
    def __init__(self, source: Timeline[IvlOut], filter: "Filter[IvlOut]"):
        self.source: Timeline[IvlOut] = source
        self.filter: Filter[IvlOut] = filter

    @property
    @override
    def _is_mask(self) -> bool:
        """Filtered timeline preserves the source's maskness."""
        return self.source._is_mask

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[IvlOut]:
        return (e for e in self.source.fetch(start, end) if self.filter.apply(e))


class Difference(Timeline[IvlOut]):
    def __init__(
        self,
        source: Timeline[IvlOut],
        *subtractors: Timeline[Any],
    ):
        self.source: Timeline[IvlOut] = source
        self.subtractors: tuple[Timeline[Any], ...] = subtractors

    @property
    @override
    def _is_mask(self) -> bool:
        """Difference preserves source's maskness (subtractors don't affect it)."""
        return self.source._is_mask

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[IvlOut]:
        """Subtract intervals using a sweep-line algorithm.

        Algorithm: For each source interval, scan through subtractor intervals
        and emit the remaining non-overlapping fragments. Uses a cursor to track
        the current position within each source interval as we carve out holes.

        The subtractors are merged into a single sorted stream for efficiency.
        """

        def generate() -> Iterable[IvlOut]:
            if not self.subtractors:
                yield from self.source.fetch(start, end)
                return

            # Merge all subtractor streams into one sorted by (start, end)
            # Use finite properties to handle None (unbounded) values
            merged = heapq.merge(
                *(subtractor.fetch(start, end) for subtractor in self.subtractors),
                key=lambda event: (event.finite_start, event.finite_end),
            )
            subtractor_iter = iter(merged)

            try:
                current_subtractor = next(subtractor_iter)
            except StopIteration:
                current_subtractor = None

            def advance_subtractor() -> None:
                nonlocal current_subtractor
                try:
                    current_subtractor = next(subtractor_iter)
                except StopIteration:
                    current_subtractor = None

            # Process each source interval
            for event in self.source.fetch(start, end):
                if current_subtractor is None:
                    yield event
                    continue

                # Track current position within this event as we carve out holes
                # Use finite values for arithmetic operations
                cursor = event.finite_start
                event_end = event.finite_end

                # Skip subtractors that end before our cursor position
                while current_subtractor and current_subtractor.finite_end < cursor:
                    advance_subtractor()

                if current_subtractor is None:
                    yield event
                    continue

                # Process all subtractors that overlap with this event
                while (
                    current_subtractor and current_subtractor.finite_start <= event_end
                ):
                    overlap_start = max(cursor, current_subtractor.finite_start)
                    overlap_end = min(event_end, current_subtractor.finite_end)

                    if overlap_start <= overlap_end:
                        # Emit fragment before the hole (if any)
                        if cursor <= overlap_start - 1:
                            # Convert back to None if sentinel value
                            start_val = cursor if cursor != NEG_INF else None
                            end_val = (
                                overlap_start - 1
                                if overlap_start - 1 != NEG_INF
                                else None
                            )
                            yield replace(event, start=start_val, end=end_val)
                        # Move cursor past the hole
                        cursor = overlap_end + 1
                        if cursor > event_end:
                            break

                    # Advance if subtractor ends within this event
                    if current_subtractor.finite_end <= event_end:
                        advance_subtractor()
                    else:
                        break

                # Emit final fragment after all holes (if any remains)
                if cursor <= event_end:
                    # Convert back to None if sentinel value
                    start_val = cursor if cursor != NEG_INF else None
                    end_val = event_end if event_end != POS_INF else None
                    yield replace(event, start=start_val, end=end_val)

        return generate()


class Complement(Timeline[Interval]):
    def __init__(self, source: Timeline[Any]):
        self.source: Timeline[Any] = source

    @property
    @override
    def _is_mask(self) -> bool:
        """Complement always produces mask Interval objects.

        Gaps represent the absence of events and have no metadata.
        """
        return True

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Interval]:
        """Generate gaps by inverting the source timeline.

        Algorithm: Scan through source intervals and emit intervals for the spaces
        between them. Cursor tracks the start of the next potential gap.

        Can now handle unbounded queries (start/end can be None), yielding
        unbounded gap intervals as needed.
        """

        def generate() -> Iterable[Interval]:
            # Convert None bounds to sentinels for comparisons
            start_bound = start if start is not None else NEG_INF
            end_bound = end if end is not None else POS_INF
            cursor = start_bound

            for event in self.source.fetch(start, end):
                event_start = event.finite_start
                event_end = event.finite_end

                if event_end < start_bound:
                    continue
                if event_start > end_bound:
                    break

                segment_start = max(event_start, start_bound)
                segment_end = min(event_end, end_bound)

                if segment_end < cursor:
                    continue

                if segment_start > cursor:
                    # Emit gap before this event
                    # Convert sentinels back to None for unbounded gaps
                    gap_start = cursor if cursor != NEG_INF else None
                    gap_end = (
                        segment_start - 1 if segment_start - 1 != NEG_INF else None
                    )
                    yield Interval(start=gap_start, end=gap_end)

                cursor = max(cursor, segment_end + 1)

                if cursor > end_bound:
                    return

            if cursor <= end_bound:
                # Emit final gap
                # Convert sentinels back to None for unbounded gaps
                gap_start = cursor if cursor != NEG_INF else None
                gap_end = end if end_bound != POS_INF else None
                yield Interval(start=gap_start, end=gap_end)

        return generate()


class _StaticTimeline(Timeline[IvlOut], Generic[IvlOut]):
    """Timeline backed by a static collection of intervals.

    This is useful for creating timelines from a fixed set of intervals
    without needing to subclass Timeline.
    """

    def __init__(self, intervals: Sequence[IvlOut]):
        # Use finite properties for sorting to handle None (unbounded) values
        self._intervals: tuple[IvlOut, ...] = tuple(
            sorted(intervals, key=lambda e: (e.finite_start, e.finite_end))
        )

        # Build max-end prefix array for efficient query pruning
        # max_end_prefix[i] = max(interval.finite_end for interval in intervals[:i+1])
        self._max_end_prefix: list[int] = []
        max_so_far = float("-inf")
        for interval in self._intervals:
            max_so_far = max(max_so_far, interval.finite_end)
            self._max_end_prefix.append(int(max_so_far))

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[IvlOut]:
        # Use binary search to narrow the range of intervals to check
        # Intervals are sorted by (finite_start, finite_end)

        if not self._intervals:
            return

        start_idx = 0
        end_idx = len(self._intervals)

        # Use max-end prefix to skip intervals that definitely can't overlap
        # Find first position where max_end >= start (all before can be skipped)
        if start is not None:
            start_idx = bisect.bisect_left(self._max_end_prefix, start)

        # Use binary search on starts to find where to stop iterating
        # Find first interval with finite_start > end
        if end is not None:
            end_idx = bisect.bisect_right(
                self._intervals, end, key=lambda interval: interval.finite_start
            )

        # Iterate only through the narrowed range
        for interval in self._intervals[start_idx:end_idx]:
            # Final filter: skip intervals that end before our start bound
            if start is not None and interval.finite_end < start:
                continue
            yield interval


def timeline(*intervals: IvlOut) -> Timeline[IvlOut]:
    """Create a timeline from a collection of intervals.

    This is a convenience function for creating timelines without needing to
    subclass Timeline. The returned timeline is immutable and sorts intervals
    by (start, end).

    Args:
        *intervals: Variable number of interval objects

    Returns:
        Timeline that yields the provided intervals

    Example:
        >>> from calgebra import timeline, Interval
        >>>
        >>> # Create a simple timeline
        >>> my_timeline = timeline(
        ...     Interval(start=1000, end=2000),
        ...     Interval(start=5000, end=6000),
        ... )
        >>>
        >>> # Works with subclassed intervals too
        >>> @dataclass(frozen=True, kw_only=True)
        ... class Event(Interval):
        ...     title: str
        >>>
        >>> events = timeline(
        ...     Event(start=1000, end=2000, title="Meeting"),
        ...     Event(start=5000, end=6000, title="Lunch"),
        ... )
    """
    return _StaticTimeline(intervals)


def flatten(timeline: "Timeline[Any]") -> "Timeline[Interval]":
    """Return a timeline that yields coalesced intervals for the given source.

    Merges overlapping and adjacent intervals into single continuous spans.
    Useful before aggregations or when you need simplified coverage.

    Note: Returns mask Interval objects (custom metadata is lost).
          Supports unbounded queries (start/end can be None).

    Example:
        >>> timeline = union(cal_a, cal_b)  # May have overlaps
        >>> merged = flatten(timeline)
        >>> coverage = list(merged[start:end])  # Non-overlapping intervals
    """

    return ~(~timeline)


def union(*timelines: "Timeline[IvlOut]") -> "Timeline[IvlOut]":
    """Compose timelines with union semantics (equivalent to chaining `|`)."""

    if not timelines:
        raise ValueError(
            "union() requires at least one timeline argument.\n"
            "Example: union(cal_a, cal_b, cal_c)"
        )

    def reducer(acc: "Timeline[IvlOut]", nxt: "Timeline[IvlOut]"):
        return acc | nxt

    return reduce(reducer, timelines)


def intersection(
    *timelines: "Timeline[IvlOut]",
) -> "Timeline[IvlOut]":
    """Compose timelines with intersection semantics (equivalent to chaining `&`)."""

    if not timelines:
        raise ValueError(
            "intersection() requires at least one timeline argument.\n"
            "Example: intersection(cal_a, cal_b, cal_c)"
        )

    def reducer(acc: "Timeline[IvlOut]", nxt: "Timeline[IvlOut]"):
        return acc & nxt

    return reduce(reducer, timelines)
