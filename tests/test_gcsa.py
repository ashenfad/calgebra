from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from calgebra.gcsa import Calendar


class _StubEvent:
    def __init__(
        self,
        *,
        id: str,
        summary: str,
        start: datetime | date,
        end: datetime | date,
        description: str | None = None,
        timezone: str | None = None,
    ) -> None:
        self.id = id
        self.summary = summary
        self.start = start
        self.end = end
        self.description = description
        self.timezone = timezone


class _StubGoogleCalendar:
    def __init__(self, events: list[_StubEvent]):
        self._events = events
        self.calls: list[dict[str, object]] = []

    def get_events(self, **kwargs) -> list[_StubEvent]:
        self.calls.append(kwargs)
        return list(self._events)


def _build_calendar(
    events: list[_StubEvent],
    *,
    calendar_id: str = "primary",
    calendar_summary: str = "Primary",
) -> tuple[Calendar, _StubGoogleCalendar]:
    client = _StubGoogleCalendar(events)
    calendar = Calendar(calendar_id, calendar_summary, client=client)
    return calendar, client


def test_fetch_converts_exact_second_end_to_inclusive_previous_second() -> None:
    zone = ZoneInfo("UTC")
    start = datetime(2025, 1, 1, 10, 0, 0, tzinfo=zone)
    end = datetime(2025, 1, 1, 10, 30, 0, tzinfo=zone)

    event = _StubEvent(id="evt-1", summary="Meeting", start=start, end=end)
    calendar, client = _build_calendar([event])

    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())

    results = list(calendar[start_ts:end_ts])

    assert len(results) == 1
    fetched = results[0]
    assert fetched.start == start_ts
    assert fetched.end == end_ts - 1
    assert fetched.end - fetched.start + 1 == 30 * 60
    assert fetched.calendar_id == "primary"
    assert fetched.calendar_summary == "Primary"

    # Verify API call parameters (now in UTC)
    kwargs = client.calls[0]
    assert kwargs["time_min"] == start.astimezone(ZoneInfo("UTC"))
    assert kwargs["time_max"] == end.astimezone(ZoneInfo("UTC")) + timedelta(seconds=1)
    assert kwargs["calendar_id"] == "primary"


def test_fetch_keeps_fractional_second_end_within_elapsed_second() -> None:
    zone = ZoneInfo("UTC")
    start = datetime(2025, 1, 1, 10, 0, 0, tzinfo=zone)
    end = datetime(2025, 1, 1, 10, 30, 0, 500_000, tzinfo=zone)

    event = _StubEvent(id="evt-2", summary="Partial", start=start, end=end)
    calendar, _ = _build_calendar([event])

    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())

    fetched = list(calendar[start_ts:end_ts])[0]
    assert fetched.start == start_ts
    assert fetched.end == end_ts
    assert fetched.calendar_summary == "Primary"


def test_fetch_supports_all_day_events_from_dates() -> None:
    zone_name = "America/New_York"
    zone = ZoneInfo(zone_name)

    start_date = date(2025, 1, 1)
    end_date = date(2025, 1, 2)

    # Event has its own timezone specified
    event = _StubEvent(
        id="evt-3", 
        summary="All Day", 
        start=start_date, 
        end=end_date,
        timezone=zone_name
    )
    calendar, _ = _build_calendar([event])

    expected_start_ts = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=zone).timestamp())
    expected_end_ts = int(datetime(2025, 1, 1, 23, 59, 59, tzinfo=zone).timestamp())

    fetched = list(calendar[expected_start_ts:expected_end_ts])[0]
    assert fetched.start == expected_start_ts
    assert fetched.end == expected_end_ts
    assert fetched.calendar_id == "primary"
    assert fetched.calendar_summary == "Primary"
