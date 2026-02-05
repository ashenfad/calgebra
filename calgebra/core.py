import heapq
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import replace
from datetime import datetime
from functools import reduce
from typing import Any, Generic, Literal, cast, overload

from typing_extensions import override

from calgebra.interval import NEG_INF, POS_INF, Interval, IvlIn, IvlOut


class Timeline(ABC, Generic[IvlOut]):
    @abstractmethod
    def fetch(
        self, start: int | None, end: int | None, *, reverse: bool = False
    ) -> Iterable[IvlOut]:
        """Yield events within the provided bounds.

        Args:
            start: Start timestamp (inclusive), None for unbounded
            end: End timestamp (exclusive), None for unbounded
            reverse: If True, yield events in reverse chronological order

        Returns:
            Iterable of events, ordered by (start, end) ascending if reverse=False,
            or descending if reverse=True.
        """
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
        end_bound = self._coerce_bound(item.stop, "end")
        step = item.step

        # Validate step parameter
        if step is not None and step not in (1, -1):
            raise ValueError(
                f"Timeline slicing only supports step of 1 or -1, got {step}.\n"
                f"Use step=-1 for reverse iteration: timeline[end:start:-1]"
            )

        reverse = step == -1

        # Convert exclusive slice bound to inclusive interval bound
        # Python slicing [start:end] excludes end
        # Our intervals are now exclusive [start, end)
        # So we use the end bound directly
        end = end_bound

        # Normalize bounds for reverse iteration: [min, max) regardless of order
        # This prioritizes calendar semantics over strict Python slice behavior
        if start is not None and end is not None and start > end:
            start, end = end, start

        # Automatically clip intervals to query bounds via intersection with solid
        # timeline
        # This ensures correct behavior for aggregations and set operations
        # Skip clipping if both bounds are unbounded (no clipping needed)
        if start is None and end is None:
            return self.fetch(start, end, reverse=reverse)
        # Cast solid to compatible type since intersection preserves self's type
        return (self & cast("Timeline[IvlOut]", solid)).fetch(
            start, end, reverse=reverse
        )

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

    def overlapping(self, point: int) -> Iterable[IvlOut]:
        """Yield intervals that contain the given point, unclipped.

        This is useful for point-in-time queries like "what's happening now?"
        Unlike slicing, returned intervals are not clipped to query bounds.

        Args:
            point: Unix timestamp to query

        Returns:
            Intervals where start <= point < end
        """
        return self.fetch(point, point + 1)


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
    def fetch(
        self, start: int | None, end: int | None, *, reverse: bool = False
    ) -> Iterable[Interval]:
        # Single interval, reverse doesn't matter
        yield Interval(start=start, end=end)


# Singleton instance for clipping operations
solid: Timeline[Interval] = _SolidTimeline()


def _neg(val: int | None) -> int | None:
    """Negate a timestamp, preserving None for unbounded."""
    return -val if val is not None else None


def _negate_interval(ivl: Interval) -> Interval:
    """Negate timestamps, swapping start/end to maintain start <= end.

    Used to convert reverse iteration into forward iteration:
    negating all timestamps turns descending order into ascending,
    allowing the forward-only sweep to run unmodified in negated space.
    """
    return replace(ivl, start=_neg(ivl.end), end=_neg(ivl.start))


def _negate_stream(stream: Iterable[Interval]) -> Iterable[Interval]:
    """Negate every interval in a stream."""
    return (_negate_interval(ivl) for ivl in stream)


def _flatten_sources(
    sources: Iterable[Timeline[IvlOut]],
    cls: type["Union[IvlOut]"] | type["Intersection[IvlOut]"],
) -> tuple[Timeline[IvlOut], ...]:
    """Flatten nested instances of the same class (Union or Intersection)."""
    flattened: list[Timeline[IvlOut]] = []
    for source in sources:
        if isinstance(source, cls):
            flattened.extend(source.sources)
        else:
            flattened.append(source)
    return tuple(flattened)


class Union(Timeline[IvlOut]):
    def __init__(self, *sources: Timeline[IvlOut]):
        self.sources: tuple[Timeline[IvlOut], ...] = _flatten_sources(sources, Union)

    @property
    @override
    def _is_mask(self) -> bool:
        """Union is mask only if all sources are mask."""
        return all(s._is_mask for s in self.sources)

    @override
    def fetch(
        self, start: int | None, end: int | None, *, reverse: bool = False
    ) -> Iterable[IvlOut]:
        streams = [source.fetch(start, end, reverse=reverse) for source in self.sources]
        # Use finite properties for sorting to handle None (unbounded) values
        if reverse:
            # For reverse, sort descending by (start, end)
            merged = heapq.merge(
                *streams,
                key=lambda e: (-e.finite_start, -e.finite_end),
            )
        else:
            merged = heapq.merge(
                *streams,
                key=lambda e: (e.finite_start, e.finite_end),
            )
        return merged


class _SourceState:
    """Per-source state for the intersection algorithm.

    Tracks the current interval, exhaustion status, and processing history
    for a single source in the intersection.
    """

    def __init__(self, iterator: Iterable[Interval]) -> None:
        self._iterator: Iterator[Interval] = iter(iterator)
        self.current: Interval | None = None
        self.exhausted: bool = False
        self.last_processed_cutoff: int | None = None
        # Initialize with first interval
        self.advance()

    def advance(self) -> bool:
        """Advance to next interval. Returns True if state changed."""
        if self.exhausted:
            return False
        try:
            self.current = next(self._iterator)
            self.last_processed_cutoff = None
            return True
        except StopIteration:
            self.exhausted = True
            # Keep current interval for continued overlap checks with other sources
            return True  # State changed (now exhausted)

    def advance_if_ends_at(self, cutoff: int) -> bool:
        """Advance if current interval ends at cutoff. Returns True if advanced."""
        if (
            self.current is not None
            and self.current.finite_end == cutoff
            and not self.exhausted
        ):
            return self.advance()
        return False

    def advance_if_stalled(self, cutoff: int) -> bool:
        """Advance if processed at cutoff but doesn't end there.

        This handles the case where a mask source advanced but this emit source's
        interval extends past the cutoff. Without this, we'd miss subsequent
        intervals with identical start/end times.
        """
        if (
            self.current is not None
            and not self.exhausted
            and self.last_processed_cutoff == cutoff
            and self.current.finite_end != cutoff
        ):
            return self.advance()
        return False

    def was_processed_at(self, cutoff: int) -> bool:
        """Check if already processed at this cutoff (to avoid duplicates)."""
        return self.last_processed_cutoff == cutoff


class Intersection(Timeline[IvlOut]):
    def __init__(self, *sources: Timeline[IvlOut]):
        self.sources: tuple[Timeline[IvlOut], ...] = _flatten_sources(
            sources, Intersection
        )

    @property
    @override
    def _is_mask(self) -> bool:
        """Intersection is mask only if all sources are mask."""
        return all(s._is_mask for s in self.sources)

    @override
    def fetch(
        self, start: int | None, end: int | None, *, reverse: bool = False
    ) -> Iterable[IvlOut]:
        """Compute intersection using a multi-way merge with sliding window.

        Emit behavior (based on source types):
        - All mask sources: Emit one interval per overlap (auto-flattened)
        - Mixed mask/rich: Emit only from rich sources (preserves metadata)
        - All rich sources: Emit from all sources

        Reverse iteration uses time-negation to reuse the forward-only sweep:
        negate inputs, run forward, negate outputs.
        """
        if not self.sources:
            return ()

        # Determine which sources to emit from based on mask/rich types
        mask_sources = [s._is_mask for s in self.sources]
        if all(mask_sources):
            emit_indices = frozenset([0])  # All mask: emit just one (auto-flatten)
        elif any(mask_sources):
            emit_indices = frozenset(
                i for i, is_mask in enumerate(mask_sources) if not is_mask
            )
        else:
            emit_indices = frozenset(range(len(self.sources)))

        if reverse:
            streams = [
                _negate_stream(s.fetch(start, end, reverse=True)) for s in self.sources
            ]
            return _negate_stream(self._sweep(streams, emit_indices))

        streams = [s.fetch(start, end) for s in self.sources]
        return self._sweep(streams, emit_indices)

    def _sweep(
        self,
        streams: list[Iterable[IvlOut]],
        emit_indices: frozenset[int],
    ) -> Iterable[IvlOut]:
        """Forward-only intersection sweep algorithm.

        Algorithm:
        1. Maintain one "current" interval from each source
        2. Find the overlap region across all current intervals
        3. Yield trimmed copies from emit sources
        4. Advance sources whose intervals end at the overlap boundary
        5. Handle stall condition when emit sources extend past mask boundaries
        6. Repeat until no more overlaps possible
        """
        states = [_SourceState(stream) for stream in streams]

        # Early exit if all sources exhausted on init (no intervals)
        if all(s.exhausted and s.current is None for s in states):
            return

        # Special case: single source intersection is identity
        if len(states) == 1:
            state = states[0]
            while state.current is not None:
                yield state.current
                state.advance()
                if state.exhausted:
                    break  # Don't re-yield the last interval
            return

        while True:
            # Check if all sources have a current interval
            active = [s.current for s in states if s.current is not None]
            if len(active) < len(states):
                return  # Need intervals from ALL sources for intersection

            # Find overlap region across all current intervals
            overlap_start = max(ivl.finite_start for ivl in active)
            overlap_end = min(ivl.finite_end for ivl in active)

            # Emit trimmed intervals from emit sources
            if overlap_start < overlap_end:
                for idx in emit_indices:
                    state = states[idx]
                    if state.current is None or state.was_processed_at(overlap_end):
                        continue
                    # Convert sentinel values back to None for unbounded intervals
                    start_val = overlap_start if overlap_start != NEG_INF else None
                    end_val = overlap_end if overlap_end != POS_INF else None
                    yield replace(state.current, start=start_val, end=end_val)
                    state.last_processed_cutoff = overlap_end

            # Advance sources whose intervals end at the overlap boundary
            cutoff = overlap_end
            advanced = any(s.advance_if_ends_at(cutoff) for s in states)

            # Handle stall condition: emit sources processed but extending past
            # cutoff. This ensures we get all intervals with identical times
            # from same source
            if not advanced:
                advanced = any(
                    states[idx].advance_if_stalled(cutoff) for idx in emit_indices
                )

            if not advanced:
                return  # No progress possible, done


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
    def fetch(
        self, start: int | None, end: int | None, *, reverse: bool = False
    ) -> Iterable[IvlOut]:
        return (
            e
            for e in self.source.fetch(start, end, reverse=reverse)
            if self.filter.apply(e)
        )


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
    def fetch(
        self, start: int | None, end: int | None, *, reverse: bool = False
    ) -> Iterable[IvlOut]:
        """Subtract intervals using a sweep-line algorithm.

        Reverse iteration uses time-negation to reuse the forward-only sweep:
        negate inputs, run forward, negate outputs.
        """
        if not self.subtractors:
            return self.source.fetch(start, end, reverse=reverse)

        if reverse:
            source_stream = _negate_stream(self.source.fetch(start, end, reverse=True))
            sub_streams = [
                _negate_stream(sub.fetch(start, end, reverse=True))
                for sub in self.subtractors
            ]
            return _negate_stream(self._sweep(source_stream, sub_streams))

        source_stream = self.source.fetch(start, end)
        sub_streams = [sub.fetch(start, end) for sub in self.subtractors]
        return self._sweep(source_stream, sub_streams)

    def _sweep(
        self,
        source_stream: Iterable[IvlOut],
        sub_streams: list[Iterable[Any]],
    ) -> Iterable[IvlOut]:
        """Forward-only difference sweep algorithm.

        For each source interval, scan through subtractor intervals and emit the
        remaining non-overlapping fragments. Uses a cursor to track the current
        position within each source interval as we carve out holes.
        """
        # Merge all subtractor streams into one sorted by (start, end)
        merged = heapq.merge(
            *sub_streams,
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
        for event in source_stream:
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
            while current_subtractor and current_subtractor.finite_start <= event_end:
                overlap_start = max(cursor, current_subtractor.finite_start)
                overlap_end = min(event_end, current_subtractor.finite_end)

                if overlap_start < overlap_end:
                    # Emit fragment before the hole (if any)
                    if cursor < overlap_start:
                        # Convert back to None if sentinel value
                        start_val = cursor if cursor != NEG_INF else None
                        end_val = overlap_start if overlap_start != NEG_INF else None
                        yield replace(event, start=start_val, end=end_val)
                    # Move cursor past the hole
                    cursor = overlap_end
                    if cursor >= event_end:
                        break

                # Advance if subtractor ends within this event
                if current_subtractor.finite_end <= event_end:
                    advance_subtractor()
                else:
                    break

            # Emit final fragment after all holes (if any remains)
            if cursor < event_end:
                # Convert back to None if sentinel value
                start_val = cursor if cursor != NEG_INF else None
                end_val = event_end if event_end != POS_INF else None
                yield replace(event, start=start_val, end=end_val)


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
    def fetch(
        self, start: int | None, end: int | None, *, reverse: bool = False
    ) -> Iterable[Interval]:
        """Generate gaps by inverting the source timeline.

        Reverse iteration uses time-negation to reuse the forward-only sweep:
        negate inputs, run forward, negate outputs.
        """
        if reverse:
            source_stream = _negate_stream(self.source.fetch(start, end, reverse=True))
            return _negate_stream(self._sweep(source_stream, _neg(end), _neg(start)))
        return self._sweep(self.source.fetch(start, end), start, end)

    def _sweep(
        self,
        source_stream: Iterable[Interval],
        start: int | None,
        end: int | None,
    ) -> Iterable[Interval]:
        """Forward-only complement sweep algorithm.

        Scan through source intervals and emit intervals for the spaces between
        them. Cursor tracks the start of the next potential gap. Handles
        unbounded queries (start/end can be None).
        """
        # Convert None bounds to sentinels for comparisons
        start_bound = start if start is not None else NEG_INF
        end_bound = end if end is not None else POS_INF
        cursor = start_bound

        for event in source_stream:
            event_start = event.finite_start
            event_end = event.finite_end

            if event_end < start_bound:
                continue
            if event_start > end_bound:
                break

            segment_start = max(event_start, start_bound)
            segment_end = min(event_end, end_bound)

            if segment_end <= cursor:
                continue

            if segment_start > cursor:
                # Emit gap before this event
                # Convert sentinels back to None for unbounded gaps
                gap_start = cursor if cursor != NEG_INF else None
                gap_end = segment_start if segment_start != NEG_INF else None
                yield Interval(start=gap_start, end=gap_end)

            cursor = max(cursor, segment_end)

            if cursor > end_bound:
                return

        if cursor < end_bound:
            # Emit final gap
            # Convert sentinels back to None for unbounded gaps
            gap_start = cursor if cursor != NEG_INF else None
            gap_end = end if end_bound != POS_INF else None
            yield Interval(start=gap_start, end=gap_end)


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
