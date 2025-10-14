import operator as op
from collections.abc import Iterable
from typing import Any, Callable, Generic, Hashable, Literal, override

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
        return (event.end - event.start + 1) / self.scale


class Start(Property[Interval]):
    @override
    def apply(self, event: Interval) -> int:
        return event.start


class End(Property[Interval]):
    @override
    def apply(self, event: Interval) -> int:
        return event.end


days: Duration[Interval] = Duration("days")
hours: Duration[Interval] = Duration("hours")
minutes: Duration[Interval] = Duration("minutes")
seconds: Duration[Interval] = Duration("seconds")
start: Start = Start()
end: End = End()


def one_of(property: Property[IvlIn], values: Iterable[Hashable]) -> Operator[IvlIn]:
    return Operator(set(values), property, op.contains)
