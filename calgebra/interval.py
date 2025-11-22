import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

# Sentinels for unbounded intervals
# Use values that leave room for arithmetic operations (±1)
NEG_INF = -(sys.maxsize - 1)
POS_INF = sys.maxsize - 1


@dataclass(frozen=True, kw_only=True)
class Interval:
    start: int | None  # None represents -∞ (unbounded past)
    end: int | None  # None represents +∞ (unbounded future)

    def __post_init__(self) -> None:
        # Only validate when both bounds are finite
        if self.start is not None and self.end is not None:
            if self.start > self.end:
                raise ValueError(
                    f"Interval start ({self.start}) must be <= end ({self.end})"
                )

    @property
    def finite_start(self) -> int:
        """Start bound treating None as very negative int for algorithms."""
        return self.start if self.start is not None else NEG_INF

    @property
    def finite_end(self) -> int:
        """End bound treating None as very positive int for algorithms."""
        return self.end if self.end is not None else POS_INF

    @classmethod
    def from_datetimes(
        cls,
        start: datetime,
        end: datetime,
        **kwargs: Any,
    ) -> "Interval":
        """Create an Interval from timezone-aware datetimes.

        Args:
            start: Start datetime (must be timezone-aware)
            end: End datetime (must be timezone-aware)
            **kwargs: Additional fields for subclasses

        Returns:
            Interval instance with start/end as Unix timestamps

        Raises:
            ValueError: If datetimes are not timezone-aware

        Example:
            >>> from datetime import datetime, timezone
            >>> from calgebra import Interval
            >>> dt1 = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
            >>> dt2 = datetime(2025, 1, 1, 17, 0, tzinfo=timezone.utc)
            >>> interval = Interval.from_datetimes(start=dt1, end=dt2)
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError(
                "Datetimes must be timezone-aware. "
                "Use datetime.replace(tzinfo=...) or at_tz() helper."
            )
        return cls(
            start=int(start.timestamp()),
            end=int(end.timestamp()),
            **kwargs,
        )

    def __str__(self) -> str:
        """Human-friendly string showing range and duration."""
        start_str = str(self.start) if self.start is not None else "-∞"
        end_str = str(self.end) if self.end is not None else "+∞"

        if self.start is not None and self.end is not None:
            duration = self.end - self.start
            return f"Interval({start_str}→{end_str}, {duration}s)"
        else:
            return f"Interval({start_str}→{end_str}, unbounded)"


IvlOut = TypeVar("IvlOut", bound="Interval", covariant=True)
IvlIn = TypeVar("IvlIn", bound="Interval", contravariant=True)
