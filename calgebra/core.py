import heapq
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import replace
from datetime import date, datetime, time, timezone
from functools import reduce
from typing import Any, Generic, Literal, overload, override

from calgebra.interval import Interval, IvlIn, IvlOut


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
        return self.fetch(start, end)

    def _coerce_bound(self, bound: Any, edge: Literal["start", "end"]) -> int | None:
        """Convert slice bounds to integer seconds (Unix timestamps).

        Accepts:
        - int: Passed through as-is (Unix timestamp)
        - datetime: Must be timezone-aware, converted to timestamp
        - date: Converted to start/end of day in UTC
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
                    f"Timeline slice {edge} bound must be a timezone-aware datetime.\n"
                    f"Got naive datetime: {bound!r}\n"
                    f"Hint: Add timezone info:\n"
                    f"  from zoneinfo import ZoneInfo\n"
                    f"  dt = datetime(..., tzinfo=ZoneInfo('UTC'))  "
                    f"# or 'US/Pacific', etc.\n"
                    f"  # Or use timezone.utc for UTC:\n"
                    f"  dt = datetime(..., tzinfo=timezone.utc)"
                )
            return int(bound.timestamp())
        if isinstance(bound, date):
            # Convert date to datetime at start/end of day in UTC
            if edge == "start":
                dt = datetime.combine(bound, time.min, tzinfo=timezone.utc)
            else:  # edge == "end"
                dt = datetime.combine(bound, time.max, tzinfo=timezone.utc)
            return int(dt.timestamp())
        raise TypeError(
            f"Timeline slice {edge} bound must be int, datetime, date, or None.\n"
            f"Got {type(bound).__name__!r}: {bound!r}\n"
            f"Examples:\n"
            f"  timeline[start_ts:end_ts]  # int (Unix seconds)\n"
            f"  timeline[datetime(2025,1,1,tzinfo=timezone.utc):]  "
            f"# timezone-aware datetime\n"
            f"  timeline[date(2025,1,1):date(2025,12,31)]  # date objects"
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
        merged = heapq.merge(*streams, key=lambda e: (e.start, e.end))
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
                overlap_start = max(event.start for event in current)
                overlap_end = min(event.end for event in current)

                # If there's actual overlap, yield trimmed copy from selected sources
                if overlap_start <= overlap_end:
                    for idx in emit_indices:
                        yield replace(
                            current[idx], start=overlap_start, end=overlap_end
                        )

                # Advance any interval that ends at the overlap boundary
                cutoff = overlap_end
                advanced = False
                for idx, event in enumerate(current):
                    if event.end == cutoff:
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
        """Difference preserves the source's maskness (subtractors don't affect type)."""
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
            merged = heapq.merge(
                *(subtractor.fetch(start, end) for subtractor in self.subtractors),
                key=lambda event: (event.start, event.end),
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
                cursor = event.start
                event_end = event.end

                # Skip subtractors that end before our cursor position
                while current_subtractor and current_subtractor.end < cursor:
                    advance_subtractor()

                if current_subtractor is None:
                    yield event
                    continue

                # Process all subtractors that overlap with this event
                while current_subtractor and current_subtractor.start <= event_end:
                    overlap_start = max(cursor, current_subtractor.start)
                    overlap_end = min(event_end, current_subtractor.end)

                    if overlap_start <= overlap_end:
                        # Emit fragment before the hole (if any)
                        if cursor <= overlap_start - 1:
                            yield replace(event, start=cursor, end=overlap_start - 1)
                        # Move cursor past the hole
                        cursor = overlap_end + 1
                        if cursor > event_end:
                            break

                    # Advance if subtractor ends within this event
                    if current_subtractor.end <= event_end:
                        advance_subtractor()
                    else:
                        break

                # Emit final fragment after all holes (if any remains)
                if cursor <= event_end:
                    yield replace(event, start=cursor, end=event_end)

            # Exhaust generator to avoid partially consumed iterators on reuse
            for _ in subtractor_iter:
                pass

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
        """Generate gaps by inverting the source timeline within finite bounds.

        Algorithm: Scan through source intervals and emit intervals for the spaces
        between them. Cursor tracks the start of the next potential gap.
        """
        if start is None or end is None:
            raise ValueError(
                f"Complement (~) requires finite bounds, got start={start}, end={end}.\n"
                f"Complement inverts a timeline, which requires a bounded universe.\n"
                f"Fix: Use explicit bounds when slicing: list((~timeline)[start:end])\n"
                f"Example: list((~busy)[1704067200:1735689599])"
            )

        def generate() -> Iterable[Interval]:
            cursor = start

            for event in self.source.fetch(start, end):
                if event.end < start:
                    continue
                if event.start > end:
                    break

                segment_start = max(event.start, start)
                segment_end = min(event.end, end)

                if segment_end < cursor:
                    continue

                if segment_start > cursor:
                    yield Interval(start=cursor, end=segment_start - 1)

                cursor = max(cursor, segment_end + 1)

                if cursor > end:
                    return

            if cursor <= end:
                yield Interval(start=cursor, end=end)

        return generate()


def flatten(timeline: "Timeline[Any]") -> "Timeline[Interval]":
    """Return a timeline that yields coalesced intervals for the given source.

    Merges overlapping and adjacent intervals into single continuous spans.
    Useful before aggregations or when you need simplified coverage.

    Note: Returns mask Interval objects (custom metadata is lost).
          Requires finite bounds when slicing: flatten(tl)[start:end]

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
            f"union() requires at least one timeline argument.\n"
            f"Example: union(cal_a, cal_b, cal_c)"
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
            f"intersection() requires at least one timeline argument.\n"
            f"Example: intersection(cal_a, cal_b, cal_c)"
        )

    def reducer(acc: "Timeline[IvlOut]", nxt: "Timeline[IvlOut]"):
        return acc & nxt

    return reduce(reducer, timelines)
