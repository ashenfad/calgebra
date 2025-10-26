from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from gcsa.google_calendar import GoogleCalendar
from typing_extensions import override

from calgebra.core import Timeline
from calgebra.interval import Interval


@dataclass(frozen=True)
class CalendarItem:
    id: str
    summary: str


@dataclass(frozen=True, kw_only=True)
class Event(Interval):
    id: str
    summary: str
    description: str | None

    @override
    def __str__(self) -> str:
        """Human-friendly string showing event details and duration."""
        duration = self.end - self.start + 1
        return f"Event('{self.summary}', {self.start}→{self.end}, {duration}s)"


def list_calendars() -> list[CalendarItem]:
    """Return calendars accessible to the locally authenticated user."""
    return [
        CalendarItem(e.id, e.summary)
        for e in GoogleCalendar().get_calendar_list()
        if e.id is not None and e.summary is not None
    ]


def _normalize_datetime(
    dt: datetime | date, edge: Literal["start", "end"], zone: ZoneInfo
) -> datetime:
    if not isinstance(dt, datetime):
        dt = datetime.combine(dt, time.min if edge == "start" else time.max)
        dt = dt.replace(tzinfo=zone)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=zone)
    else:
        dt = dt.astimezone(zone)
    return dt.astimezone(timezone.utc)


def _to_timestamp(
    dt: datetime | date, edge: Literal["start", "end"], zone: ZoneInfo
) -> int:
    normalized = _normalize_datetime(dt, edge, zone)

    if edge == "start":
        return int(normalized.replace(microsecond=0).timestamp())

    if not isinstance(dt, datetime):
        start_of_day = _normalize_datetime(dt, "start", zone)
        inclusive = start_of_day - timedelta(seconds=1)
        return int(inclusive.replace(microsecond=0).timestamp())

    if normalized.microsecond == 0:
        normalized -= timedelta(seconds=1)

    return int(normalized.replace(microsecond=0).timestamp())


def _timestamp_to_datetime(ts: int, zone: ZoneInfo) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(zone)


class Calendar(Timeline[Event]):
    """Timeline backed by the Google Calendar API using local credentials."""

    def __init__(
        self,
        calendar: CalendarItem | str,
        *,
        timezone_name: str = "UTC",
        client: GoogleCalendar | None = None,
    ) -> None:
        calendar_id = calendar if isinstance(calendar, str) else calendar.id
        self.calendar: GoogleCalendar = (
            client if client is not None else GoogleCalendar(calendar_id)
        )
        self._zone: ZoneInfo = ZoneInfo(timezone_name)

    @override
    def fetch(self, start: int | None, end: int | None) -> Iterable[Event]:
        start_dt = (
            _timestamp_to_datetime(start, self._zone) if start is not None else None
        )
        # end bounds are inclusive; add a second so Google returns events
        # touching the end
        end_dt = (
            _timestamp_to_datetime(end + 1, self._zone) if end is not None else None
        )
        events_iterable = (
            self.calendar.get_events(  # pyright: ignore[reportUnknownMemberType]
                time_min=start_dt,
                time_max=end_dt,
                timezone=self._zone.key,
                single_events=True,
                order_by="startTime",
            )
        )

        for e in events_iterable:
            if e.id is None or e.summary is None or e.end is None:
                continue
            yield Event(
                id=e.id,
                summary=e.summary,
                description=e.description,
                start=_to_timestamp(e.start, "start", self._zone),
                end=_to_timestamp(e.end, "end", self._zone),
            )
