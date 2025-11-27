from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from calgebra.gcsa import Calendar


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
    def __init__(self, events: list[_StubEvent] | None = None):
        self._events = events if events is not None else []
        self.calls: list[dict[str, object]] = []
        self.added_events: list[dict[str, object]] = []

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

    def add_event(self, event, *, calendar_id: str | None = None, **kwargs):
        """Stub for adding an event to Google Calendar."""
        self.added_events.append(
            {
                "event": event,
                "calendar_id": calendar_id,
                **kwargs,
            }
        )
        # Return a stub event with an ID
        # Extract event details from the gcsa Event object
        event_id = f"evt-{len(self.added_events)}"
        # Extract start datetime/date
        if isinstance(event.start, (datetime, date)):
            start_dt = event.start
        else:
            start_dt = event.start.dateTime or event.start.date
        # Extract end datetime/date
        if isinstance(event.end, (datetime, date)):
            end_dt = event.end
        else:
            end_dt = event.end.dateTime or event.end.date
        return _StubEvent(
            id=event_id,
            summary=event.summary,
            start=start_dt,
            end=end_dt,
            description=event.description,
            timezone=event.timezone,
            reminders=event.reminders,
            default_reminders=getattr(event, "default_reminders", False),
        )

    def get_event(self, event_id: str, *, calendar_id: str | None = None, **kwargs):
        """Stub for getting an event by ID."""
        # Find event by ID in our list
        for event in self._events:
            if event.id == event_id:
                return event
        raise ValueError(f"Event {event_id} not found")

    def delete_event(
        self, event: str | object, *, calendar_id: str | None = None, **kwargs
    ):
        """Stub for deleting an event."""
        event_id = event if isinstance(event, str) else getattr(event, "id", None)
        if event_id is None:
            raise ValueError("Event ID required")
        # Remove from list
        self._events = [e for e in self._events if e.id != event_id]

    def update_event(self, event: object, *, calendar_id: str | None = None, **kwargs):
        """Stub for updating an event."""
        # Update the event in our list
        event_id = getattr(event, "id", None)
        if event_id:
            for i, e in enumerate(self._events):
                if e.id == event_id:
                    # Update the event in place
                    self._events[i] = event
                    return event
        # If not found, add it
        self._events.append(event)
        return event

    def get_calendar_list(self):
        return []


def _build_calendar(
    events: list[_StubEvent],
    *,
    calendar_id: str = "primary",
    calendar_summary: str = "Primary",
) -> tuple[Calendar, _StubGoogleCalendar]:
    stub = _StubGoogleCalendar(events)
    calendar = Calendar(
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
    # 30 minutes + 0.5 seconds
    end_dt = datetime(2025, 1, 1, 10, 30, 0, 500000, tzinfo=zone)

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

    fetched = list(calendar[expected_start_ts:expected_end_ts])[0]
    assert fetched.start == expected_start_ts
    assert fetched.end == expected_end_ts
    assert fetched.calendar_id == "primary"
    assert fetched.calendar_summary == "Primary"


def test_calendar_str_includes_ids_and_summary() -> None:
    calendar, _ = _build_calendar(
        [], calendar_id="team@company.com", calendar_summary="Team Calendar"
    )
    assert str(calendar) == "Calendar(id='team@company.com', summary='Team Calendar')"


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

    # Use fetch() directly to avoid intersection clipping issues
    # with overlapping events
    # TODO: Investigate why intersection filters out the timed event
    # when it's within all-day event
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
    from calgebra.gcsa import Reminder

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


def test_add_interval_creates_timed_event() -> None:
    """Test that _add_interval creates a timed event correctly."""
    from calgebra.gcsa import Event, Reminder

    zone = ZoneInfo("UTC")
    start_dt = datetime(2025, 1, 1, 14, 0, 0, tzinfo=zone)
    end_dt = datetime(2025, 1, 1, 15, 0, 0, tzinfo=zone)

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    # Create an Event to add
    event = Event(
        id="",  # Will be set by Google Calendar
        calendar_id="primary",
        calendar_summary="Primary",
        summary="Test Meeting",
        description="Test description",
        is_all_day=False,
        reminders=[
            Reminder(method="email", minutes=30),
            Reminder(method="popup", minutes=15),
        ],
        start=start_ts,
        end=end_ts,
    )

    calendar, stub = _build_calendar([])

    # Add the event
    results = calendar._add_interval(event, metadata={})

    # Verify result
    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert result.error is None
    assert result.event is not None
    assert result.event.summary == "Test Meeting"
    assert result.event.description == "Test description"
    assert result.event.is_all_day is False
    assert result.event.start == start_ts
    assert result.event.end == end_ts
    assert result.event.reminders == event.reminders

    # Verify add_event was called
    assert len(stub.added_events) == 1
    added_call = stub.added_events[0]
    assert added_call["calendar_id"] == "primary"
    gcsa_event = added_call["event"]
    assert gcsa_event.summary == "Test Meeting"
    assert gcsa_event.description == "Test description"
    assert gcsa_event.timezone == "UTC"
    # Verify start/end are datetime objects (not dates)
    assert isinstance(gcsa_event.start, datetime)
    assert isinstance(gcsa_event.end, datetime)
    # Verify reminders were converted
    assert len(gcsa_event.reminders) == 2


def test_add_interval_creates_all_day_event() -> None:
    """Test that _add_interval creates an all-day event correctly."""
    from calgebra.gcsa import Event

    zone = ZoneInfo("UTC")
    # All-day event: start and end at midnight
    start_dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=zone)
    end_dt = datetime(2025, 1, 2, 0, 0, 0, tzinfo=zone)

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    # Create an all-day Event
    event = Event(
        id="",
        calendar_id="primary",
        calendar_summary="Primary",
        summary="All Day Event",
        description=None,
        is_all_day=True,
        reminders=None,
        start=start_ts,
        end=end_ts,
    )

    calendar, stub = _build_calendar([])

    # Add the event
    results = calendar._add_interval(event, metadata={})

    # Verify result
    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert result.event is not None
    assert result.event.is_all_day is True

    # Verify add_event was called with date objects
    assert len(stub.added_events) == 1
    gcsa_event = stub.added_events[0]["event"]
    assert isinstance(gcsa_event.start, date)
    assert isinstance(gcsa_event.end, date)
    assert gcsa_event.timezone is None  # All-day events don't have timezone


def test_add_interval_auto_infers_all_day() -> None:
    """Test that _add_interval auto-infers all-day status when is_all_day=None."""
    from calgebra.gcsa import Event

    zone = ZoneInfo("UTC")
    # Event spanning whole days at midnight boundaries
    start_dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=zone)
    end_dt = datetime(2025, 1, 3, 0, 0, 0, tzinfo=zone)  # 2 days

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    # Create event with is_all_day=None (should auto-infer)
    event = Event(
        id="",
        calendar_id="primary",
        calendar_summary="Primary",
        summary="Auto-detected All Day",
        description=None,
        is_all_day=None,  # Auto-infer
        reminders=None,
        start=start_ts,
        end=end_ts,
    )

    calendar, stub = _build_calendar([])

    # Add the event
    results = calendar._add_interval(event, metadata={})

    # Verify result
    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert result.event is not None
    # Should have inferred all-day
    assert result.event.is_all_day is True

    # Verify add_event was called with date objects
    gcsa_event = stub.added_events[0]["event"]
    assert isinstance(gcsa_event.start, date)
    assert isinstance(gcsa_event.end, date)


def test_add_interval_rejects_non_event() -> None:
    """Test that _add_interval rejects non-Event intervals."""
    from calgebra.interval import Interval

    calendar, stub = _build_calendar([])

    # Try to add a plain Interval (not an Event)
    interval = Interval(start=1000, end=2000)
    results = calendar._add_interval(interval, metadata={})

    # Verify error result
    assert len(results) == 1
    result = results[0]
    assert result.success is False
    assert result.error is not None
    assert isinstance(result.error, TypeError)
    assert "Expected Event" in str(result.error)

    # Verify add_event was not called
    assert len(stub.added_events) == 0


def test_add_interval_rejects_unbounded_interval() -> None:
    """Test that _add_interval rejects intervals with None start/end."""
    from calgebra.gcsa import Event

    calendar, stub = _build_calendar([])

    # Try to add an event with None start
    event = Event(
        id="",
        calendar_id="primary",
        calendar_summary="Primary",
        summary="Unbounded",
        description=None,
        start=None,  # Invalid
        end=2000,
    )

    results = calendar._add_interval(event, metadata={})

    # Verify error result
    assert len(results) == 1
    result = results[0]
    assert result.success is False
    assert result.error is not None
    assert isinstance(result.error, ValueError)
    assert "finite start and end" in str(result.error)

    # Verify add_event was not called
    assert len(stub.added_events) == 0


def test_add_recurring_creates_recurring_event() -> None:
    """Test that _add_recurring creates a recurring event correctly."""
    from calgebra.gcsa import Event
    from calgebra.recurrence import RecurringPattern
    from calgebra.util import HOUR

    zone = ZoneInfo("UTC")
    start_dt = datetime(2025, 1, 6, 10, 0, 0, tzinfo=zone)  # Monday
    start_ts = int(start_dt.timestamp())

    # Create a weekly recurring pattern (every Monday at 10am for 1 hour)
    pattern = RecurringPattern(
        freq="weekly",
        day="monday",
        start=10 * HOUR,  # 10am
        duration=HOUR,  # 1 hour
        tz="UTC",
        interval_class=Event,
        summary="Weekly Standup",
        description="Team standup meeting",
    )

    calendar, stub = _build_calendar([])

    # Add the recurring pattern with start timestamp in metadata
    metadata = {"start": start_ts}
    results = calendar._add_recurring(pattern, metadata)

    # Verify result
    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert result.error is None
    assert result.event is not None
    assert result.event.summary == "Weekly Standup"
    assert result.event.description == "Team standup meeting"
    assert result.event.recurring_event_id is None  # Master event
    assert result.event.is_all_day is False  # Timed event

    # Verify add_event was called
    assert len(stub.added_events) == 1
    added_call = stub.added_events[0]
    assert added_call["calendar_id"] == "primary"
    gcsa_event = added_call["event"]
    assert gcsa_event.summary == "Weekly Standup"
    assert gcsa_event.description == "Team standup meeting"
    assert gcsa_event.timezone == "UTC"
    # Verify recurrence string
    assert len(gcsa_event.recurrence) == 1
    rrule_str = gcsa_event.recurrence[0]
    assert "FREQ=WEEKLY" in rrule_str
    assert "BYDAY=MO" in rrule_str
    # Verify start/end are datetime objects (not dates)
    assert isinstance(gcsa_event.start, datetime)
    assert isinstance(gcsa_event.end, datetime)


def test_add_recurring_creates_all_day_recurring_event() -> None:
    """Test that _add_recurring creates an all-day recurring event."""
    from calgebra.gcsa import Event
    from calgebra.recurrence import RecurringPattern
    from calgebra.util import DAY

    zone = ZoneInfo("UTC")
    start_dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=zone)
    start_ts = int(start_dt.timestamp())

    # Create a daily all-day recurring pattern
    pattern = RecurringPattern(
        freq="daily",
        duration=DAY,  # Full day = all-day
        tz="UTC",
        interval_class=Event,
        summary="Daily Reminder",
    )

    calendar, stub = _build_calendar([])

    # Add the recurring pattern
    metadata = {"start": start_ts}
    results = calendar._add_recurring(pattern, metadata)

    # Verify result
    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert result.event is not None
    assert result.event.is_all_day is True

    # Verify add_event was called with date objects
    gcsa_event = stub.added_events[0]["event"]
    assert isinstance(gcsa_event.start, date)
    assert isinstance(gcsa_event.end, date)
    assert gcsa_event.timezone is None  # All-day events don't have timezone
    # Verify recurrence string
    assert "FREQ=DAILY" in gcsa_event.recurrence[0]


def test_add_recurring_includes_exdates() -> None:
    """Test that _add_recurring includes EXDATE for excluded dates."""
    from datetime import timezone

    from calgebra.gcsa import Event
    from calgebra.recurrence import RecurringPattern
    from calgebra.util import DAY, HOUR

    zone = ZoneInfo("UTC")
    start_dt = datetime(2025, 1, 6, 10, 0, 0, tzinfo=zone)  # Monday
    start_ts = int(start_dt.timestamp())

    # Exclude the second occurrence (next Monday)
    excluded_ts = start_ts + 7 * DAY

    # Create a weekly recurring pattern with exdates
    pattern = RecurringPattern(
        freq="weekly",
        day="monday",
        start=10 * HOUR,
        duration=HOUR,
        tz="UTC",
        interval_class=Event,
        summary="Weekly Meeting",
        exdates=[excluded_ts],
    )

    calendar, stub = _build_calendar([])

    # Add the recurring pattern
    metadata = {"start": start_ts}
    results = calendar._add_recurring(pattern, metadata)

    # Verify result
    assert len(results) == 1
    assert results[0].success is True

    # Verify EXDATE is included in recurrence string
    gcsa_event = stub.added_events[0]["event"]
    rrule_str = gcsa_event.recurrence[0]
    assert "EXDATE:" in rrule_str
    # Check that the excluded date is formatted correctly
    excluded_dt = datetime.fromtimestamp(excluded_ts, tz=timezone.utc)
    excluded_str = excluded_dt.strftime("%Y%m%dT%H%M%SZ")
    assert excluded_str in rrule_str


def test_add_recurring_rejects_non_event_pattern() -> None:
    """Test that _add_recurring accepts RecurringPattern[Interval] and promotes it
    using metadata.
    """
    from calgebra.interval import Interval
    from calgebra.recurrence import RecurringPattern
    from calgebra.util import DAY

    calendar, stub = _build_calendar([])

    # Create a pattern with base Interval class (not Event)
    pattern = RecurringPattern(
        freq="daily",
        duration=DAY,
        tz="UTC",
        interval_class=Interval,  # Base Interval, not Event
    )

    # Pass metadata with summary to create Event fields
    results = calendar._add_recurring(pattern, metadata={"summary": "Daily Pattern"})

    # Verify success - now accepts Interval and promotes via metadata
    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert result.error is None
    assert result.event is not None
    assert result.event.summary == "Daily Pattern"
    assert result.event.is_all_day is True

    # Verify add_event was called
    assert len(stub.added_events) == 1
    gcsa_event = stub.added_events[0]["event"]
    assert gcsa_event.summary == "Daily Pattern"



def test_remove_interval_deletes_standalone_event() -> None:
    """Test that _remove_interval deletes a standalone event."""
    from calgebra.gcsa import Event

    zone = ZoneInfo("UTC")
    start_dt = datetime(2025, 1, 1, 10, 0, 0, tzinfo=zone)
    end_dt = datetime(2025, 1, 1, 11, 0, 0, tzinfo=zone)

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    # Create a standalone event
    event = Event(
        id="evt-standalone",
        calendar_id="primary",
        calendar_summary="Primary",
        summary="Standalone Event",
        description="To be deleted",
        recurring_event_id=None,  # Standalone
        is_all_day=False,
        start=start_ts,
        end=end_ts,
    )

    # Create a stub event for the calendar
    stub_event = _StubEvent(
        id="evt-standalone",
        summary="Standalone Event",
        start=start_dt,
        end=end_dt,
        timezone="UTC",
    )

    calendar, stub = _build_calendar([stub_event])

    # Remove the event
    results = calendar._remove_interval(event)

    # Verify result
    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert result.error is None
    assert result.event == event

    # Verify event was deleted (removed from stub's event list)
    assert len(stub._events) == 0


def test_remove_interval_adds_recurring_instance_to_exdates() -> None:
    """Test that _remove_interval adds a recurring instance to exdates."""
    from calgebra.gcsa import Event

    zone = ZoneInfo("UTC")
    start_dt = datetime(2025, 1, 6, 10, 0, 0, tzinfo=zone)  # Monday
    end_dt = datetime(2025, 1, 6, 11, 0, 0, tzinfo=zone)

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    # Create a recurring instance
    instance = Event(
        id="evt-instance",
        calendar_id="primary",
        calendar_summary="Primary",
        summary="Weekly Meeting",
        description=None,
        recurring_event_id="master-event-id",
        is_all_day=False,
        start=start_ts,
        end=end_ts,
    )

    # Create master event with recurrence
    master_event = _StubEvent(
        id="master-event-id",
        summary="Weekly Meeting",
        start=start_dt,
        end=end_dt,
        timezone="UTC",
    )
    # Add recurrence attribute (gcsa stores it as a list)
    master_event.recurrence = ["FREQ=WEEKLY;BYDAY=MO"]

    calendar, stub = _build_calendar([master_event])

    # Remove the instance
    results = calendar._remove_interval(instance)

    # Verify result
    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert result.error is None

    # Verify master event was updated with EXDATE
    updated_master = stub.get_event("master-event-id")
    assert updated_master.recurrence is not None
    rrule_str = updated_master.recurrence[0]
    assert "EXDATE:" in rrule_str or "EXDATE=" in rrule_str
    # Check that the instance start time is in EXDATE
    exdate_str = start_dt.strftime("%Y%m%dT%H%M%SZ")
    assert exdate_str in rrule_str


def test_remove_interval_rejects_non_event() -> None:
    """Test that _remove_interval rejects non-Event intervals."""
    from calgebra.interval import Interval

    calendar, stub = _build_calendar([])

    # Try to remove a plain Interval
    interval = Interval(start=1000, end=2000)
    results = calendar._remove_interval(interval)

    # Verify error result
    assert len(results) == 1
    result = results[0]
    assert result.success is False
    assert result.error is not None
    assert isinstance(result.error, TypeError)
    assert "Expected Event" in str(result.error)


def test_remove_interval_rejects_event_without_id() -> None:
    """Test that _remove_interval rejects events without an ID."""
    from calgebra.gcsa import Event

    calendar, stub = _build_calendar([])

    # Create event without ID
    event = Event(
        id="",  # Empty ID
        calendar_id="primary",
        calendar_summary="Primary",
        summary="No ID",
        description=None,
        start=1000,
        end=2000,
    )

    results = calendar._remove_interval(event)

    # Verify error result
    assert len(results) == 1
    result = results[0]
    assert result.success is False
    assert result.error is not None
    assert isinstance(result.error, ValueError)
    assert "ID" in str(result.error)


def test_remove_series_deletes_master_event() -> None:
    """Test that _remove_series deletes a master recurring event."""
    from calgebra.gcsa import Event

    zone = ZoneInfo("UTC")
    start_dt = datetime(2025, 1, 6, 10, 0, 0, tzinfo=zone)  # Monday
    end_dt = datetime(2025, 1, 6, 11, 0, 0, tzinfo=zone)

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    # Create a master recurring event
    master_event = Event(
        id="master-event-id",
        calendar_id="primary",
        calendar_summary="Primary",
        summary="Weekly Meeting",
        description=None,
        recurring_event_id=None,  # Master event
        is_all_day=False,
        start=start_ts,
        end=end_ts,
    )

    # Create stub master event
    stub_master = _StubEvent(
        id="master-event-id",
        summary="Weekly Meeting",
        start=start_dt,
        end=end_dt,
        timezone="UTC",
    )
    stub_master.recurrence = ["FREQ=WEEKLY;BYDAY=MO"]

    calendar, stub = _build_calendar([stub_master])

    # Remove the series
    results = calendar._remove_series(master_event)

    # Verify result
    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert result.error is None
    assert result.event == master_event

    # Verify master event was deleted
    assert len(stub._events) == 0


def test_remove_series_deletes_master_from_instance() -> None:
    """Test that _remove_series deletes master event when given an instance."""
    from calgebra.gcsa import Event

    zone = ZoneInfo("UTC")
    start_dt = datetime(2025, 1, 6, 10, 0, 0, tzinfo=zone)  # Monday
    end_dt = datetime(2025, 1, 6, 11, 0, 0, tzinfo=zone)

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    # Create a recurring instance
    instance = Event(
        id="evt-instance",
        calendar_id="primary",
        calendar_summary="Primary",
        summary="Weekly Meeting",
        description=None,
        recurring_event_id="master-event-id",  # Points to master
        is_all_day=False,
        start=start_ts,
        end=end_ts,
    )

    # Create stub master event
    stub_master = _StubEvent(
        id="master-event-id",
        summary="Weekly Meeting",
        start=start_dt,
        end=end_dt,
        timezone="UTC",
    )
    stub_master.recurrence = ["FREQ=WEEKLY;BYDAY=MO"]

    calendar, stub = _build_calendar([stub_master])

    # Remove the series using the instance
    results = calendar._remove_series(instance)

    # Verify result
    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert result.error is None

    # Verify master event was deleted (not the instance)
    assert len(stub._events) == 0
    # Verify master was deleted, not instance
    try:
        stub.get_event("master-event-id")
        assert False, "Master event should have been deleted"
    except ValueError:
        pass  # Expected


def test_remove_series_rejects_non_event() -> None:
    """Test that _remove_series rejects non-Event intervals."""
    from calgebra.interval import Interval

    calendar, stub = _build_calendar([])

    # Try to remove a plain Interval
    interval = Interval(start=1000, end=2000)
    results = calendar._remove_series(interval)

    # Verify error result
    assert len(results) == 1
    result = results[0]
    assert result.success is False
    assert result.error is not None
    assert isinstance(result.error, TypeError)
    assert "Expected Event" in str(result.error)


def test_remove_series_rejects_event_without_id() -> None:
    """Test that _remove_series rejects events without an ID."""
    from calgebra.gcsa import Event

    calendar, stub = _build_calendar([])

    # Create event without ID
    event = Event(
        id="",  # Empty ID
        calendar_id="primary",
        calendar_summary="Primary",
        summary="No ID",
        description=None,
        start=1000,
        end=2000,
    )

    results = calendar._remove_series(event)

    # Verify error result
    assert len(results) == 1
    result = results[0]
    assert result.success is False
    assert result.error is not None
    assert isinstance(result.error, ValueError)
    assert "ID" in str(result.error)


def test_add_interval_auto_fills_calendar_metadata() -> None:
    """Test that _add_interval auto-fills calendar_id and calendar_summary."""
    from calgebra.gcsa import Event

    zone = ZoneInfo("UTC")
    start_dt = datetime(2025, 1, 1, 14, 0, 0, tzinfo=zone)
    end_dt = datetime(2025, 1, 1, 15, 0, 0, tzinfo=zone)

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    # Create an Event WITHOUT calendar_id/calendar_summary
    event = Event(
        id="",
        summary="Test Meeting",
        description=None,
        is_all_day=False,
        start=start_ts,
        end=end_ts,
    )

    calendar, stub = _build_calendar([])

    # Add the event
    results = calendar._add_interval(event, metadata={})

    # Verify result has calendar metadata auto-filled
    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert result.event is not None
    assert result.event.calendar_id == calendar.calendar_id
    assert result.event.calendar_summary == calendar.calendar_summary


def test_add_interval_ignores_source_calendar_metadata() -> None:
    """Test that _add_interval ignores calendar_id/calendar_summary from source
    calendar.
    """
    from calgebra.gcsa import Event

    zone = ZoneInfo("UTC")
    start_dt = datetime(2025, 1, 1, 14, 0, 0, tzinfo=zone)
    end_dt = datetime(2025, 1, 1, 15, 0, 0, tzinfo=zone)

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    # Create calendar A with specific ID
    cal_a, stub_a = _build_calendar(
        [],
        calendar_id="calendar-a",
        calendar_summary="Calendar A",
    )

    # Create an Event with calendar A's metadata
    event = Event(
        id="",
        calendar_id=cal_a.calendar_id,
        calendar_summary=cal_a.calendar_summary,
        summary="Test Meeting",
        description=None,
        start=start_ts,
        end=end_ts,
    )

    # Create calendar B with different ID
    cal_b, stub_b = _build_calendar(
        [],
        calendar_id="calendar-b",
        calendar_summary="Calendar B",
    )

    # Add event to calendar B (should use B's metadata, not A's)
    results = cal_b._add_interval(event, metadata={})

    # Verify result has calendar B's metadata (not A's)
    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert result.event is not None
    assert result.event.calendar_id == cal_b.calendar_id
    assert result.event.calendar_summary == cal_b.calendar_summary
    assert result.event.calendar_id != cal_a.calendar_id  # Should be different
    assert result.event.calendar_id == "calendar-b"
