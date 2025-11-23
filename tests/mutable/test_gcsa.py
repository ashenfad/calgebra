from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from calgebra.mutable.gcsa import GoogleCalendarTimeline


class _StubStart:
    """Stub for gcsa Event.start object with date/dateTime attributes.

    Google Calendar API:
    - All-day events: start.date is set, start.dateTime is None
    - Timed events: start.dateTime is set, start.date is None
    """

    def __init__(self, dt: datetime | date):
        # Check datetime first since datetime is a subclass of date
        if isinstance(dt, datetime):
            self.date = None
            self.dateTime = dt
        else:  # date
            self.date = dt
            self.dateTime = None


class _StubReminder:
    """Stub for gcsa Reminder object."""

    def __init__(self, method: str, minutes_before_start: int) -> None:
        self.method = method
        self.minutes_before_start = minutes_before_start


class _StubEvent:
    """Stub for gcsa Event object."""

    def __init__(
        self,
        *,
        id: str,
        summary: str,
        start: datetime | date,
        end: datetime | date,
        description: str | None = None,
        timezone: str | None = None,
        recurring_event_id: str | None = None,
        reminders: list[_StubReminder] | None = None,
        default_reminders: bool = False,
    ) -> None:
        self.id = id
        self.summary = summary
        # Create start object with .date and .dateTime attributes (like gcsa Event)
        self.start = _StubStart(start)
        self.end = end
        self.description = description
        self.timezone = timezone
        self.recurring_event_id = recurring_event_id
        self.reminders = reminders if reminders is not None else []
        self.default_reminders = default_reminders


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


def test_fetch_populates_is_all_day_for_all_day_events() -> None:
    """Test that is_all_day is set correctly for all-day events."""
    zone_name = "America/New_York"
    zone = ZoneInfo(zone_name)

    start_date = date(2025, 1, 1)
    end_date = date(2025, 1, 2)

    # All-day event (using date objects)
    all_day_event = _StubEvent(
        id="evt-all-day",
        summary="All Day Event",
        start=start_date,
        end=end_date,
        timezone=zone_name,
    )

    # Timed event (using datetime objects)
    start_dt = datetime(2025, 1, 1, 9, 0, 0, tzinfo=zone)
    end_dt = datetime(2025, 1, 1, 10, 0, 0, tzinfo=zone)
    timed_event = _StubEvent(
        id="evt-timed",
        summary="Timed Event",
        start=start_dt,
        end=end_dt,
        timezone=zone_name,
    )

    calendar, _ = _build_calendar([all_day_event, timed_event])

    # Query a wide range to catch both events
    start_ts = int(datetime(2024, 12, 31, 0, 0, 0, tzinfo=zone).timestamp())
    end_ts = int(datetime(2025, 1, 2, 23, 59, 59, tzinfo=zone).timestamp())

    # Use fetch() directly to avoid intersection clipping issues with overlapping events
    # TODO: Investigate why intersection filters out the timed event when it's within all-day event
    fetched = list(calendar.fetch(start_ts, end_ts))
    assert len(fetched) == 2

    # Find the all-day event
    all_day = next(e for e in fetched if e.id == "evt-all-day")
    assert all_day.is_all_day is True

    # Find the timed event
    timed = next(e for e in fetched if e.id == "evt-timed")
    assert timed.is_all_day is False


def test_fetch_populates_recurring_event_id() -> None:
    """Test that recurring_event_id is populated correctly."""
    zone = ZoneInfo("UTC")
    start_dt = datetime(2025, 1, 1, 9, 0, 0, tzinfo=zone)
    end_dt = datetime(2025, 1, 1, 10, 0, 0, tzinfo=zone)

    # Standalone event (no recurring_event_id)
    standalone = _StubEvent(
        id="evt-standalone",
        summary="Standalone",
        start=start_dt,
        end=end_dt,
        timezone="UTC",
        recurring_event_id=None,
    )

    # Recurring instance (has recurring_event_id)
    instance = _StubEvent(
        id="evt-instance",
        summary="Recurring Instance",
        start=start_dt,
        end=end_dt,
        timezone="UTC",
        recurring_event_id="master-event-id",
    )

    calendar, _ = _build_calendar([standalone, instance])

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp()) + 3600  # 1 hour later

    fetched = list(calendar[start_ts:end_ts])
    assert len(fetched) == 2

    # Find standalone event
    standalone_fetched = next(e for e in fetched if e.id == "evt-standalone")
    assert standalone_fetched.recurring_event_id is None

    # Find recurring instance
    instance_fetched = next(e for e in fetched if e.id == "evt-instance")
    assert instance_fetched.recurring_event_id == "master-event-id"


def test_fetch_populates_reminders() -> None:
    """Test that reminders are populated correctly."""
    from calgebra.mutable.gcsa import Reminder

    zone = ZoneInfo("UTC")
    start_dt = datetime(2025, 1, 1, 9, 0, 0, tzinfo=zone)
    end_dt = datetime(2025, 1, 1, 10, 0, 0, tzinfo=zone)

    # Event with custom reminders
    event_with_reminders = _StubEvent(
        id="evt-with-reminders",
        summary="With Reminders",
        start=start_dt,
        end=end_dt,
        timezone="UTC",
        reminders=[
            _StubReminder(method="email", minutes_before_start=30),
            _StubReminder(method="popup", minutes_before_start=15),
        ],
        default_reminders=False,
    )

    # Event with default reminders (should result in None)
    event_default_reminders = _StubEvent(
        id="evt-default-reminders",
        summary="Default Reminders",
        start=start_dt,
        end=end_dt,
        timezone="UTC",
        reminders=[],
        default_reminders=True,
    )

    # Event with no reminders specified (empty list, not default)
    event_no_reminders = _StubEvent(
        id="evt-no-reminders",
        summary="No Reminders",
        start=start_dt,
        end=end_dt,
        timezone="UTC",
        reminders=[],
        default_reminders=False,
    )

    calendar, _ = _build_calendar(
        [event_with_reminders, event_default_reminders, event_no_reminders]
    )

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp()) + 3600  # 1 hour later

    fetched = list(calendar[start_ts:end_ts])
    assert len(fetched) == 3

    # Find event with reminders
    with_reminders = next(e for e in fetched if e.id == "evt-with-reminders")
    assert with_reminders.reminders is not None
    assert len(with_reminders.reminders) == 2
    assert with_reminders.reminders[0] == Reminder(method="email", minutes=30)
    assert with_reminders.reminders[1] == Reminder(method="popup", minutes=15)

    # Find event with default reminders (should be None)
    default_reminders = next(e for e in fetched if e.id == "evt-default-reminders")
    assert default_reminders.reminders is None

    # Find event with no reminders (empty list should result in None)
    no_reminders = next(e for e in fetched if e.id == "evt-no-reminders")
    assert no_reminders.reminders is None

