from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from calgebra.mutable.gcsa import GoogleCalendarTimeline


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

    def get_events(
        self,
        *,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        single_events: bool = True,
        order_by: str = "startTime",
        calendar_id: str | None = None,
    ):
        self.calls.append(
            {
                "time_min": time_min,
                "time_max": time_max,
                "single_events": single_events,
                "order_by": order_by,
                "calendar_id": calendar_id,
            }
        )
        # Return iterator (gcsa returns an iterator)
        return iter(self._events)

    def get_calendar_list(self):
        return []


def _build_calendar(
    events: list[_StubEvent],
    *,
    calendar_id: str = "primary",
    calendar_summary: str = "Primary",
) -> tuple[GoogleCalendarTimeline, _StubGoogleCalendar]:
    stub = _StubGoogleCalendar(events)
    calendar = GoogleCalendarTimeline(
        calendar_id=calendar_id,
        calendar_summary=calendar_summary,
        client=stub,
    )
    return calendar, stub


def test_fetch_converts_exact_second_end_to_inclusive_previous_second() -> None:
    """Test that exact second boundaries are handled correctly with exclusive ends."""
    zone = ZoneInfo("UTC")
    start_dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=zone)
    end_dt = datetime(2025, 1, 1, 12, 0, 1, tzinfo=zone)

    event = _StubEvent(
        id="evt-1",
        summary="Test",
        start=start_dt,
        end=end_dt,
        timezone="UTC",
    )
    calendar, _ = _build_calendar([event])

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    fetched = list(calendar[start_ts:end_ts])
    assert len(fetched) == 1
    assert fetched[0].start == start_ts
    assert fetched[0].end == end_ts
    assert fetched[0].calendar_id == "primary"
    assert fetched[0].calendar_summary == "Primary"


def test_fetch_keeps_fractional_second_end_within_elapsed_second() -> None:
    """Test that fractional seconds are handled correctly."""
    zone = ZoneInfo("UTC")
    start_dt = datetime(2025, 1, 1, 10, 0, 0, tzinfo=zone)
    end_dt = datetime(2025, 1, 1, 10, 30, 0, 500000, tzinfo=zone)  # 30 minutes + 0.5 seconds

    event = _StubEvent(
        id="evt-2",
        summary="Partial",
        start=start_dt,
        end=end_dt,
        timezone="UTC",
    )
    calendar, _ = _build_calendar([event])

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    fetched = list(calendar[start_ts : end_ts + 1])[0]
    assert fetched.start == start_ts
    # With exclusive ends, the fractional second 10:30:00.5 gets truncated to 10:30:00
    # So the end is 10:30:00, which is end_ts
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
        timezone=zone_name,
    )
    calendar, _ = _build_calendar([event])

    # With exclusive ends, the all-day event covers [start_of_day, end_of_day)
    # But Google returns the next day as the exclusive end
    expected_start_ts = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=zone).timestamp())
    expected_end_ts = int(datetime(2025, 1, 2, 0, 0, 0, tzinfo=zone).timestamp())

    fetched = list(calendar[expected_start_ts : expected_end_ts])[0]
    assert fetched.start == expected_start_ts
    assert fetched.end == expected_end_ts
    assert fetched.calendar_id == "primary"
    assert fetched.calendar_summary == "Primary"


def test_calendar_str_includes_ids_and_summary() -> None:
    calendar, _ = _build_calendar(
        [], calendar_id="team@company.com", calendar_summary="Team Calendar"
    )
    assert (
        str(calendar)
        == "GoogleCalendarTimeline(id='team@company.com', summary='Team Calendar')"
    )

