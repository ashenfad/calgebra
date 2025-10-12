import heapq
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import replace
from functools import reduce
from typing import Any, Generic, Literal, cast, overload, override

from calgebra.interval import Interval, IvlIn, IvlOut


class Timeline(ABC, Generic[IvlOut]):

    @abstractmethod
    def fetch(self, start: int | None, end: int | None) -> Iterable[IvlOut]:
        """Yield events ordered by start/end within the provided bounds."""
        pass

    def _make_complement_interval(self, start: int, end: int) -> IvlOut:
        """Construct a gap interval produced by complement operations."""

        return cast(IvlOut, Interval(start=start, end=end))

    def __getitem__(self, item: slice) -> Iterable[IvlOut]:
        start = self._coerce_bound(item.start, "start")
        end = self._coerce_bound(item.stop, "end")
        return self.fetch(start, end)

    def _coerce_bound(self, bound: Any, edge: Literal["start", "end"]) -> int | None:
        if bound is None:
            return None
        if isinstance(bound, int):
            return bound
        raise TypeError(
            f"Timeline slice {edge} bound must be an int or None, got {type(bound)!r}"
        )

    @overload
    def __or__(self, other: "Timeline[IvlOut]") -> "Timeline[IvlOut]": ...

    @overload
    def __or__(self, other: "Filter[Any]") -> "Timeline[IvlOut]": ...

    def __or__(self, other: "Timeline[IvlOut] | Filter[Any]") -> "Timeline[IvlOut]":
        if isinstance(other, Filter):
            raise ValueError("Cannot union a source with a filter")
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
            raise ValueError("Cannot union a filter with a source")
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

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[IvlOut]:
        if not self.sources:
            return ()

        iterators = [iter(source.fetch(start, end)) for source in self.sources]

        def generate() -> Iterable[IvlOut]:
            try:
                current = [next(iterator) for iterator in iterators]
            except StopIteration:
                return

            while True:
                overlap_start = max(event.start for event in current)
                overlap_end = min(event.end for event in current)

                if overlap_start <= overlap_end:
                    for event in current:
                        yield replace(event, start=overlap_start, end=overlap_end)

                cutoff = overlap_end
                advanced = False
                for idx, event in enumerate(current):
                    if event.end == cutoff:
                        try:
                            current[idx] = next(iterators[idx])
                            advanced = True
                        except StopIteration:
                            return

                if not advanced:
                    return

        return generate()


class Filtered(Timeline[IvlOut]):
    def __init__(self, source: Timeline[IvlOut], filter: "Filter[IvlOut]"):
        self.source: Timeline[IvlOut] = source
        self.filter: Filter[IvlOut] = filter

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

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[IvlOut]:
        def generate() -> Iterable[IvlOut]:
            if not self.subtractors:
                yield from self.source.fetch(start, end)
                return

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

            for event in self.source.fetch(start, end):
                if current_subtractor is None:
                    yield event
                    continue

                cursor = event.start
                event_end = event.end

                while current_subtractor and current_subtractor.end < cursor:
                    advance_subtractor()

                if current_subtractor is None:
                    yield event
                    continue

                while current_subtractor and current_subtractor.start <= event_end:
                    overlap_start = max(cursor, current_subtractor.start)
                    overlap_end = min(event_end, current_subtractor.end)

                    if overlap_start <= overlap_end:
                        if cursor <= overlap_start - 1:
                            yield replace(event, start=cursor, end=overlap_start - 1)
                        cursor = overlap_end + 1
                        if cursor > event_end:
                            break

                    if current_subtractor.end <= event_end:
                        advance_subtractor()
                    else:
                        break

                if cursor <= event_end:
                    yield replace(event, start=cursor, end=event_end)

            # exhaust generator to avoid partially consumed iterators on reuse
            for _ in subtractor_iter:
                pass

        return generate()


class Complement(Timeline[IvlOut]):
    def __init__(self, source: Timeline[IvlOut]):
        self.source: Timeline[IvlOut] = source

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[IvlOut]:
        if start is None or end is None:
            raise ValueError("Complement requires finite start and end bounds")

        def generate() -> Iterable[IvlOut]:
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
                    yield self.source._make_complement_interval(
                        cursor, segment_start - 1
                    )

                cursor = max(cursor, segment_end + 1)

                if cursor > end:
                    return

            if cursor <= end:
                yield self.source._make_complement_interval(cursor, end)

        return generate()


def flatten(timeline: "Timeline[Any]") -> "Timeline[Interval]":
    """Return a timeline that yields coalesced intervals for the given source."""

    return ~(~timeline)


def union(*timelines: "Timeline[IvlOut]") -> "Timeline[IvlOut]":
    """Compose timelines with union semantics (equivalent to chaining `|`)."""

    if not timelines:
        raise ValueError("union requires at least one timeline")

    def reducer(acc: "Timeline[IvlOut]", nxt: "Timeline[IvlOut]"):
        return acc | nxt

    return reduce(reducer, timelines)


def intersection(
    *timelines: "Timeline[IvlOut]",
) -> "Timeline[IvlOut]":
    """Compose timelines with intersection semantics (equivalent to chaining `&`)."""

    if not timelines:
        raise ValueError("intersection requires at least one timeline")

    def reducer(acc: "Timeline[IvlOut]", nxt: "Timeline[IvlOut]"):
        return acc & nxt

    return reduce(reducer, timelines)
