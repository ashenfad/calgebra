"""Utility constants and helpers for calgebra.

Time unit constants represent durations in seconds.
These are used throughout the API for consistent time representation.
"""

from datetime import date, datetime, time
from typing import Callable, overload
from zoneinfo import ZoneInfo

from dateutil.parser import isoparse

# Time unit constants (all values in seconds)
SECOND = 1
MINUTE = 60
HOUR = 3600
DAY = 86400
WEEK = 604800
MONTH = 2678400
YEAR = 31536000


def at_tz(tz: str) -> Callable[..., datetime]:
    """Create a timezone-aware datetime factory.

    Returns a function that creates datetime objects in the specified timezone.
    Useful for ergonomic datetime creation when querying timelines.

    Args:
        tz: IANA timezone name (e.g., "US/Pacific", "Europe/London", "UTC")

    Returns:
        A function that accepts date/datetime strings, date/datetime objects,
        or datetime components and returns timezone-aware datetime objects.

    Examples:
        >>> from calgebra import at_tz
        >>> from datetime import date, datetime
        >>>
        >>> # Create a factory for Pacific time
        >>> at = at_tz("US/Pacific")
        >>>
        >>> # Parse date strings (midnight in specified timezone)
        >>> at("2024-01-01")
        datetime(2024, 1, 1, 0, 0, tzinfo=ZoneInfo('US/Pacific'))
        >>>
        >>> # Parse datetime strings
        >>> at("2024-01-01T15:30:00")
        datetime(2024, 1, 1, 15, 30, tzinfo=ZoneInfo('US/Pacific'))
        >>>
        >>> # From date object (midnight in specified timezone)
        >>> at(date(2024, 1, 1))
        datetime(2024, 1, 1, 0, 0, tzinfo=ZoneInfo('US/Pacific'))
        >>>
        >>> # From naive datetime object (attach timezone)
        >>> at(datetime(2024, 1, 1, 15, 30))
        datetime(2024, 1, 1, 15, 30, tzinfo=ZoneInfo('US/Pacific'))
        >>>
        >>> # Create from components
        >>> at(2024, 1, 1)
        datetime(2024, 1, 1, 0, 0, tzinfo=ZoneInfo('US/Pacific'))
        >>>
        >>> at(2024, 1, 1, 15, 30)
        datetime(2024, 1, 1, 15, 30, tzinfo=ZoneInfo('US/Pacific'))
        >>>
        >>> # Use with timeline slicing
        >>> timeline[at("2024-01-01"):at("2024-01-31")]
        >>>
        >>> # Mix with other timezones
        >>> eastern = at_tz("US/Eastern")
        >>> timeline[at("2024-01-01"):eastern("2024-12-31")]
    """
    zone = ZoneInfo(tz)

    @overload
    def at(date_or_datetime: str) -> datetime: ...

    @overload
    def at(d: date) -> datetime: ...

    @overload
    def at(dt: datetime) -> datetime: ...

    @overload
    def at(
        year: int,
        month: int,
        day: int,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
    ) -> datetime: ...

    def at(*args, **kwargs) -> datetime:
        """Create a timezone-aware datetime in the factory's timezone.

        Accepts either:
        - A date/datetime string in ISO 8601: "2024-01-01" or "2024-01-01T15:30:00"
        - A date object: date(2024, 1, 1) -> midnight in timezone
        - A naive datetime object: datetime(2024, 1, 1, 15, 30) -> attach timezone
        - Datetime components: (year, month, day, hour=0, minute=0, second=0)

        Returns:
            A timezone-aware datetime object in the factory's timezone.

        Raises:
            ValueError: If string/datetime already has a conflicting timezone
            TypeError: If arguments don't match any accepted pattern
        """
        # String input
        if len(args) == 1 and isinstance(args[0], str):
            dt_str = args[0]
            try:
                parsed = isoparse(dt_str)
            except ValueError as e:
                raise ValueError(
                    f"Invalid date/datetime string: {dt_str!r}\n"
                    f"Expected ISO 8601 like 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SS'\n"
                    f"Error: {e}"
                ) from e

            # If it parsed as a datetime with timezone, that's a conflict
            if isinstance(parsed, datetime) and parsed.tzinfo is not None:
                raise ValueError(
                    f"Date/datetime string already has timezone: {dt_str!r}\n"
                    f"at_tz() creates timezone-aware datetimes, not conversion.\n"
                    f"Either:\n"
                    f"  - Remove tz from string\n"
                    f"  - Use datetime.fromisoformat() directly for conversion"
                )

            # Date-only string -> midnight in specified timezone
            if not isinstance(parsed, datetime):
                return datetime.combine(parsed, time.min, tzinfo=zone)

            # Naive datetime string -> apply timezone
            return parsed.replace(tzinfo=zone)

        # Datetime object input (must check before date since datetime is subclass)
        if len(args) == 1 and isinstance(args[0], datetime):
            dt = args[0]
            if dt.tzinfo is not None:
                raise ValueError(
                    f"datetime already has timezone: {dt.tzinfo}\n"
                    f"at_tz() creates timezone-aware datetimes, not conversion.\n"
                    f"Either:\n"
                    f"  - Pass a naive datetime (no tzinfo)\n"
                    f"  - Use dt.astimezone() for conversion"
                )
            return dt.replace(tzinfo=zone)

        # Date object input -> midnight in specified timezone
        if len(args) == 1 and isinstance(args[0], date):
            return datetime.combine(args[0], time.min, tzinfo=zone)

        # Args input (year, month, day, ...)
        if args and isinstance(args[0], int):
            # Add timezone to kwargs
            if "tzinfo" in kwargs:
                raise TypeError(
                    "Cannot specify tzinfo in arguments when using at_tz() factory.\n"
                    f"The factory already sets timezone to {zone.key}"
                )
            return datetime(*args, **kwargs, tzinfo=zone)

        raise TypeError(
            f"at() accepts either:\n"
            f"  - Date/datetime string: at('2024-01-01'), at('2024-01-01T15:30:00')\n"
            f"  - Date object: at(date(2024, 1, 1))\n"
            f"  - Naive datetime: at(datetime(2024, 1, 1, 15, 30))\n"
            f"  - Datetime components: at(2024, 1, 1), at(2024, 1, 1, 15, 30)\n"
            f"Got: {args}"
        )

    return at
