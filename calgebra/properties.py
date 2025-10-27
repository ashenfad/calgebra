import operator as op
from collections.abc import Callable, Iterable
from typing import Any, Generic, Hashable, Literal

from typing_extensions import override

from .core import Filter
from .interval import Interval, IvlIn


class Operator(Filter[IvlIn]):
    def __init__(
        self,
        left: "Property[IvlIn] | Any",
        right: "Property[IvlIn] | Any",
        operator: Callable[[Any, Any], bool],
    ):
        self.left: "Property[IvlIn] | Any" = left
        self.right: "Property[IvlIn] | Any" = right
        self.operator: Callable[[Any, Any], bool] = operator

    @override
    def apply(self, event: IvlIn) -> bool:
        left_val = (
            self.left.apply(event) if isinstance(self.left, Property) else self.left
        )
        right_val = (
            self.right.apply(event) if isinstance(self.right, Property) else self.right
        )
        return self.operator(left_val, right_val)


class Property(Generic[IvlIn]):
    def apply(self, event: IvlIn) -> Any:
        raise NotImplementedError

    def __ge__(self, other: "Property[IvlIn] | Any") -> Operator[IvlIn]:
        return Operator(self, other, op.ge)

    def __le__(self, other: "Property[IvlIn] | Any") -> Operator[IvlIn]:
        return Operator(self, other, op.le)

    def __gt__(self, other: "Property[IvlIn] | Any") -> Operator[IvlIn]:
        return Operator(self, other, op.gt)

    def __lt__(self, other: "Property[IvlIn] | Any") -> Operator[IvlIn]:
        return Operator(self, other, op.lt)

    @override
    def __eq__(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, other: Any
    ) -> Operator[IvlIn]:
        return Operator(self, other, op.eq)

    @override
    def __ne__(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        other: Any,
    ) -> Operator[IvlIn]:
        return Operator(self, other, op.ne)


SCALES = {
    "seconds": 1,
    "minutes": 60,
    "hours": 3600,
    "days": 86400,
}


class Duration(Property[IvlIn]):
    def __init__(self, unit: Literal["seconds", "minutes", "hours", "days"]):
        self.scale: int = SCALES[unit]

    @override
    def apply(self, event: IvlIn) -> float:
        # Handle unbounded intervals (None start or end)
        if event.start is None or event.end is None:
            return float("inf")
        return (event.end - event.start + 1) / self.scale


class Start(Property[Interval]):
    @override
    def apply(self, event: Interval) -> int:
        """Return start bound, treating None as very negative int."""
        return event.finite_start


class End(Property[Interval]):
    @override
    def apply(self, event: Interval) -> int:
        """Return end bound, treating None as very positive int."""
        return event.finite_end


days: Duration[Interval] = Duration("days")
hours: Duration[Interval] = Duration("hours")
minutes: Duration[Interval] = Duration("minutes")
seconds: Duration[Interval] = Duration("seconds")
start: Start = Start()
end: End = End()


def _normalize_collection(op_name: str, prop_val: Any) -> set[Hashable]:
    if isinstance(prop_val, (str, bytes, bytearray)):
        raise TypeError(
            f"{op_name}() must return an iterable of hashable values.\n"
            f"Got scalar {type(prop_val).__name__!r}: {prop_val!r}\n"
            f"Use set/list/tuple fields (e.g. tags) instead of strings."
        )

    try:
        return set(prop_val)
    except TypeError as exc:
        raise TypeError(
            f"{op_name}() must return an iterable of hashable values.\n"
            f"Got {type(prop_val).__name__!r}: {prop_val!r}"
        ) from exc


def one_of(property: Property[IvlIn], values: Iterable[Hashable]) -> Operator[IvlIn]:
    return Operator(set(values), property, op.contains)


def has_any(property: Property[IvlIn], values: Iterable[Hashable]) -> Operator[IvlIn]:
    """Check if a collection property contains any of the given values.

    Useful for filtering intervals with collection fields (sets, lists, etc.)
    where you want to match if ANY value is present.

    Args:
        property: A Property that returns a collection (set, list, tuple, etc.)
        values: Values to check for (will be converted to a set)

    Returns:
        A filter that matches when the property's collection intersects with values.

    Examples:
        >>> from dataclasses import dataclass
        >>> from calgebra import Interval, field, has_any
        >>>
        >>> @dataclass(frozen=True, kw_only=True)
        >>> class Event(Interval):
        ...     tags: set[str]
        >>>
        >>> tags = field('tags')
        >>> work_events = timeline & has_any(tags, {"work", "urgent"})
        >>>
        >>> # With lambda for type safety
        >>> work_events = timeline & has_any(field(lambda e: e.tags), {"work"})
    """
    value_set = set(values)

    def check(prop_val: Any, _: Any) -> bool:
        prop_collection = _normalize_collection("has_any", prop_val)
        return bool(value_set & prop_collection)

    return Operator(property, None, check)


def has_all(property: Property[IvlIn], values: Iterable[Hashable]) -> Operator[IvlIn]:
    """Check if a collection property contains all of the given values.

    Useful for filtering intervals with collection fields (sets, lists, etc.)
    where you want to match only if ALL values are present.

    Args:
        property: A Property that returns a collection (set, list, tuple, etc.)
        values: Values to check for (will be converted to a set)

    Returns:
        A filter that matches when the property's collection is a superset of values.

    Examples:
        >>> from dataclasses import dataclass
        >>> from calgebra import Interval, field, has_all
        >>>
        >>> @dataclass(frozen=True, kw_only=True)
        >>> class Event(Interval):
        ...     tags: set[str]
        >>>
        >>> tags = field('tags')
        >>> critical_work = timeline & has_all(tags, {"work", "urgent"})
        >>>
        >>> # Only matches events with BOTH "work" AND "urgent" tags
    """
    value_set = set(values)

    def check(prop_val: Any, _: Any) -> bool:
        prop_collection = _normalize_collection("has_all", prop_val)
        return value_set.issubset(prop_collection)

    return Operator(property, None, check)


def field(accessor: str | Callable[[Any], Any]) -> Property[Interval]:
    """Create a property from a field name or accessor function.

    This helper makes it easy to create properties for custom interval fields
    without needing to subclass Property.

    Args:
        accessor: Either a field name string or a function that extracts a value
            from an interval.

    Returns:
        A Property that can be used in filters and comparisons.

    Examples:
        >>> from dataclasses import dataclass
        >>> from calgebra import Interval, field, one_of
        >>>
        >>> @dataclass(frozen=True, kw_only=True)
        >>> class Event(Interval):
        ...     tags: set[str]
        ...     priority: int
        >>>
        >>> # Simple field access by name
        >>> tags = field('tags')
        >>> work_events = timeline & one_of(tags, {"work"})
        >>>
        >>> # Type-safe field access with IDE support
        >>> tags = field(lambda e: e.tags)
        >>>
        >>> # Computed properties
        >>> high_priority = timeline & (field(lambda e: e.priority) >= 8)
        >>> tag_count = field(lambda e: len(e.tags))
    """
    if isinstance(accessor, str):

        class FieldProperty(Property[Interval]):
            @override
            def apply(self, event: Interval) -> Any:
                return getattr(event, accessor)

        return FieldProperty()
    else:

        class GetterProperty(Property[Interval]):
            @override
            def apply(self, event: Interval) -> Any:
                return accessor(event)

        return GetterProperty()
