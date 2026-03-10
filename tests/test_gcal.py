"""Tests for calgebra.gcal — direct Google Calendar REST API backend."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from calgebra.gcal import (
    Attendee,
    Calendar,
    Event,
    Reminder,
    _event_to_body,
    _infer_is_all_day,
    _json_to_event,
    _parse_attendees,
    _parse_event_datetime,
    _parse_reminders,
    calendars,
)

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

UTC = timezone.utc
PACIFIC = ZoneInfo("US/Pacific")


def _ts(year, month, day, hour=0, minute=0, tz=UTC):
    """Create a unix timestamp from components."""
    dt = datetime(year, month, day, hour, minute, tzinfo=tz)
    return int(dt.timestamp())


def _make_api_event(
    *,
    id="evt1",
    summary="Test Event",
    start_dt="2025-01-15T14:00:00Z",
    end_dt="2025-01-15T15:00:00Z",
    start_date=None,
    end_date=None,
    description=None,
    location=None,
    recurring_event_id=None,
    status="confirmed",
    visibility=None,
    transparency=None,
    color_id=None,
    html_link=None,
    hangout_link=None,
    attendees=None,
    reminders=None,
    creator=None,
    organizer=None,
):
    """Build a mock Google Calendar API event JSON dict."""
    event = {"id": id, "summary": summary, "status": status}
    if start_date:
        event["start"] = {"date": start_date}
        event["end"] = {"date": end_date}
    else:
        event["start"] = {"dateTime": start_dt}
        event["end"] = {"dateTime": end_dt}
    if description:
        event["description"] = description
    if location:
        event["location"] = location
    if recurring_event_id:
        event["recurringEventId"] = recurring_event_id
    if visibility:
        event["visibility"] = visibility
    if transparency:
        event["transparency"] = transparency
    if color_id:
        event["colorId"] = color_id
    if html_link:
        event["htmlLink"] = html_link
    if hangout_link:
        event["hangoutLink"] = hangout_link
    if attendees:
        event["attendees"] = attendees
    if reminders:
        event["reminders"] = reminders
    if creator:
        event["creator"] = creator
    if organizer:
        event["organizer"] = organizer
    return event


def _mock_xhr(responses):
    """Create a mock for _xhr_request that returns responses in order.

    Args:
        responses: List of dicts (or None) to return for successive calls.
    """
    call_idx = {"i": 0}
    calls = []

    def mock_fn(method, url, access_token, body=None):
        calls.append({"method": method, "url": url, "body": body})
        idx = call_idx["i"]
        call_idx["i"] += 1
        if idx < len(responses):
            return responses[idx]
        return None

    mock_fn.calls = calls
    return mock_fn


# ---------------------------------------------------------------------------
# Test _parse_event_datetime
# ---------------------------------------------------------------------------


class TestParseEventDatetime:
    def test_timed_event_utc(self):
        dt_obj = {"dateTime": "2025-01-15T14:00:00Z"}
        ts, is_all_day = _parse_event_datetime(dt_obj, None)
        assert is_all_day is False
        assert ts == _ts(2025, 1, 15, 14, 0)

    def test_timed_event_with_offset(self):
        dt_obj = {"dateTime": "2025-01-15T06:00:00-08:00"}
        ts, is_all_day = _parse_event_datetime(dt_obj, None)
        assert is_all_day is False
        assert ts == _ts(2025, 1, 15, 14, 0)  # 6am PST = 2pm UTC

    def test_all_day_event(self):
        dt_obj = {"date": "2025-01-15"}
        ts, is_all_day = _parse_event_datetime(dt_obj, None)
        assert is_all_day is True
        assert ts == _ts(2025, 1, 15)

    def test_all_day_event_with_calendar_tz(self):
        dt_obj = {"date": "2025-01-15"}
        ts, is_all_day = _parse_event_datetime(dt_obj, PACIFIC)
        assert is_all_day is True
        # Midnight Pacific = 8am UTC
        assert ts == _ts(2025, 1, 15, 8, 0)


# ---------------------------------------------------------------------------
# Test _json_to_event
# ---------------------------------------------------------------------------


class TestJsonToEvent:
    def test_basic_timed_event(self):
        raw = _make_api_event()
        event = _json_to_event(raw, "cal1", "My Cal", None)
        assert event is not None
        assert event.id == "evt1"
        assert event.summary == "Test Event"
        assert event.calendar_id == "cal1"
        assert event.calendar_summary == "My Cal"
        assert event.is_all_day is False

    def test_all_day_event(self):
        raw = _make_api_event(start_date="2025-01-15", end_date="2025-01-16")
        event = _json_to_event(raw, "cal1", "My Cal", None)
        assert event is not None
        assert event.is_all_day is True

    def test_with_all_fields(self):
        raw = _make_api_event(
            description="A description",
            location="Room 42",
            recurring_event_id="master1",
            visibility="private",
            transparency="transparent",
            color_id="5",
            html_link="https://calendar.google.com/event?eid=xxx",
            hangout_link="https://meet.google.com/xxx",
            attendees=[
                {"email": "alice@example.com", "responseStatus": "accepted"},
                {"email": "bob@example.com", "displayName": "Bob", "optional": True},
            ],
            reminders={
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": 10}],
            },
            creator={"email": "creator@example.com"},
            organizer={"email": "org@example.com", "displayName": "Org"},
        )
        event = _json_to_event(raw, "cal1", "My Cal", None)
        assert event is not None
        assert event.description == "A description"
        assert event.location == "Room 42"
        assert event.recurring_event_id == "master1"
        assert event.visibility == "private"
        assert event.transparency == "transparent"
        assert event.color_id == "5"
        assert event.html_link is not None
        assert event.hangout_link is not None
        assert event.attendees is not None
        assert len(event.attendees) == 2
        assert event.attendees[0].email == "alice@example.com"
        assert event.attendees[1].optional is True
        assert event.reminders is not None
        assert len(event.reminders) == 1
        assert event.reminders[0].method == "popup"
        assert event.reminders[0].minutes == 10
        assert event.creator == {"email": "creator@example.com"}

    def test_missing_id_returns_none(self):
        raw = {
            "summary": "No ID",
            "start": {"dateTime": "2025-01-15T14:00:00Z"},
            "end": {"dateTime": "2025-01-15T15:00:00Z"},
        }
        assert _json_to_event(raw, "cal1", "My Cal", None) is None

    def test_default_reminders(self):
        raw = _make_api_event(reminders={"useDefault": True})
        event = _json_to_event(raw, "cal1", "My Cal", None)
        assert event is not None
        assert event.reminders is None


# ---------------------------------------------------------------------------
# Test _event_to_body
# ---------------------------------------------------------------------------


class TestEventToBody:
    def test_timed_event(self):
        event = Event(
            start=_ts(2025, 1, 15, 14),
            end=_ts(2025, 1, 15, 15),
            summary="Meeting",
        )
        body = _event_to_body(event, is_all_day=False)
        assert body["summary"] == "Meeting"
        assert "dateTime" in body["start"]
        assert "dateTime" in body["end"]

    def test_all_day_event(self):
        event = Event(
            start=_ts(2025, 1, 15),
            end=_ts(2025, 1, 16),
            summary="All Day",
        )
        body = _event_to_body(event, is_all_day=True)
        assert "date" in body["start"]
        assert "date" in body["end"]
        assert body["start"]["date"] == "2025-01-15"

    def test_with_attendees(self):
        event = Event(
            start=_ts(2025, 1, 15, 14),
            end=_ts(2025, 1, 15, 15),
            summary="Meeting",
            attendees=[
                Attendee(email="alice@example.com"),
                Attendee(email="bob@example.com", optional=True),
            ],
        )
        body = _event_to_body(event, is_all_day=False)
        assert len(body["attendees"]) == 2
        assert body["attendees"][0]["email"] == "alice@example.com"
        assert body["attendees"][1].get("optional") is True

    def test_with_reminders(self):
        event = Event(
            start=_ts(2025, 1, 15, 14),
            end=_ts(2025, 1, 15, 15),
            summary="Meeting",
            reminders=[Reminder(method="popup", minutes=10)],
        )
        body = _event_to_body(event, is_all_day=False)
        assert body["reminders"]["useDefault"] is False
        assert body["reminders"]["overrides"][0]["minutes"] == 10


# ---------------------------------------------------------------------------
# Test _parse_attendees / _parse_reminders
# ---------------------------------------------------------------------------


class TestParsers:
    def test_parse_attendees_none(self):
        assert _parse_attendees(None) is None
        assert _parse_attendees([]) is None

    def test_parse_attendees(self):
        raw = [
            {"email": "a@b.com", "responseStatus": "accepted", "self": True},
            {"email": "c@d.com", "displayName": "C D", "optional": True},
        ]
        result = _parse_attendees(raw)
        assert result is not None
        assert len(result) == 2
        assert result[0].self_ is True
        assert result[1].display_name == "C D"
        assert result[1].optional is True

    def test_parse_reminders_default(self):
        assert _parse_reminders(None) is None
        assert _parse_reminders({"useDefault": True}) is None

    def test_parse_reminders_custom(self):
        raw = {"useDefault": False, "overrides": [{"method": "email", "minutes": 30}]}
        result = _parse_reminders(raw)
        assert result is not None
        assert len(result) == 1
        assert result[0].method == "email"
        assert result[0].minutes == 30


# ---------------------------------------------------------------------------
# Test _infer_is_all_day
# ---------------------------------------------------------------------------


class TestInferIsAllDay:
    def test_all_day_utc(self):
        start = _ts(2025, 1, 15)
        end = _ts(2025, 1, 16)
        assert _infer_is_all_day(start, end, None) is True

    def test_not_all_day(self):
        start = _ts(2025, 1, 15, 14)
        end = _ts(2025, 1, 15, 15)
        assert _infer_is_all_day(start, end, None) is False

    def test_multi_day(self):
        start = _ts(2025, 1, 15)
        end = _ts(2025, 1, 17)
        assert _infer_is_all_day(start, end, None) is True


# ---------------------------------------------------------------------------
# Test Calendar.fetch with mocked HTTP
# ---------------------------------------------------------------------------


class TestCalendarFetch:
    def test_fetch_single_page(self):
        api_events = [
            _make_api_event(id="e1", summary="Ev1"),
            _make_api_event(id="e2", summary="Ev2"),
        ]
        response = {"items": api_events}

        mock = _mock_xhr(
            [
                # First call: timezone fetch
                {"timeZone": "UTC"},
                # Second call: events list
                response,
            ]
        )

        with patch("calgebra.gcal._xhr_request", mock):
            cal = Calendar("cal1", "My Cal", "fake-token")
            events = list(cal.fetch(_ts(2025, 1, 1), _ts(2025, 2, 1)))

        assert len(events) == 2
        assert events[0].summary == "Ev1"
        assert events[1].summary == "Ev2"

    def test_fetch_pagination(self):
        page1 = {"items": [_make_api_event(id="e1")], "nextPageToken": "tok2"}
        page2 = {"items": [_make_api_event(id="e2")]}

        mock = _mock_xhr(
            [
                {"timeZone": "UTC"},  # timezone
                page1,
                page2,
            ]
        )

        with patch("calgebra.gcal._xhr_request", mock):
            cal = Calendar("cal1", "My Cal", "fake-token")
            events = list(cal.fetch(_ts(2025, 1, 1), _ts(2025, 2, 1)))

        assert len(events) == 2

    def test_fetch_empty(self):
        mock = _mock_xhr(
            [
                {"timeZone": "UTC"},
                {"items": []},
            ]
        )

        with patch("calgebra.gcal._xhr_request", mock):
            cal = Calendar("cal1", "My Cal", "fake-token")
            events = list(cal.fetch(_ts(2025, 1, 1), _ts(2025, 2, 1)))

        assert events == []

    def test_fetch_reverse_requires_end(self):
        cal = Calendar("cal1", "My Cal", "fake-token")
        with pytest.raises(ValueError, match="Reverse iteration"):
            list(cal.fetch(_ts(2025, 1, 1), None, reverse=True))


# ---------------------------------------------------------------------------
# Test Calendar write operations with mocked HTTP
# ---------------------------------------------------------------------------


class TestCalendarWrite:
    def test_add_event(self):
        event = Event(
            start=_ts(2025, 1, 15, 14),
            end=_ts(2025, 1, 15, 15),
            summary="New Meeting",
        )

        mock = _mock_xhr(
            [
                {"timeZone": "UTC"},  # timezone fetch
                {"id": "created1"},  # POST response
            ]
        )

        with patch("calgebra.gcal._xhr_request", mock):
            cal = Calendar("cal1", "My Cal", "fake-token")
            results = cal.add(event)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].event is not None
        assert results[0].event.id == "created1"

        # Verify POST was made
        post_call = mock.calls[1]
        assert post_call["method"] == "POST"
        assert "events" in post_call["url"]

    def test_remove_standalone_event(self):
        event = Event(
            id="evt1",
            start=_ts(2025, 1, 15, 14),
            end=_ts(2025, 1, 15, 15),
            summary="To Delete",
        )

        mock = _mock_xhr([None])  # DELETE returns None (204)

        with patch("calgebra.gcal._xhr_request", mock):
            cal = Calendar("cal1", "My Cal", "fake-token")
            results = cal.remove(event)

        assert len(results) == 1
        assert results[0].success is True
        assert mock.calls[0]["method"] == "DELETE"

    def test_remove_recurring_instance(self):
        instance = Event(
            id="evt1_20250115",
            start=_ts(2025, 1, 15, 14),
            end=_ts(2025, 1, 15, 15),
            summary="Weekly",
            recurring_event_id="master1",
        )

        master_data = {
            "id": "master1",
            "summary": "Weekly",
            "recurrence": ["RRULE:FREQ=WEEKLY"],
            "start": {"dateTime": "2025-01-08T14:00:00Z"},
            "end": {"dateTime": "2025-01-08T15:00:00Z"},
        }

        mock = _mock_xhr(
            [
                master_data,  # GET master
                master_data,  # PUT updated master
            ]
        )

        with patch("calgebra.gcal._xhr_request", mock):
            cal = Calendar("cal1", "My Cal", "fake-token")
            results = cal.remove(instance)

        assert len(results) == 1
        assert results[0].success is True
        # Verify PUT was called with updated recurrence
        put_call = mock.calls[1]
        assert put_call["method"] == "PUT"
        assert "EXDATE" in put_call["body"]["recurrence"][0]

    def test_remove_series(self):
        event = Event(
            id="inst1",
            start=_ts(2025, 1, 15, 14),
            end=_ts(2025, 1, 15, 15),
            summary="Series",
            recurring_event_id="master1",
        )

        mock = _mock_xhr([None])  # DELETE

        with patch("calgebra.gcal._xhr_request", mock):
            cal = Calendar("cal1", "My Cal", "fake-token")
            results = cal.remove_series(event)

        assert len(results) == 1
        assert results[0].success is True
        # Should delete master, not instance
        assert "master1" in mock.calls[0]["url"]

    def test_add_non_event_fails(self):
        from calgebra.interval import Interval

        interval = Interval(start=100, end=200)
        cal = Calendar("cal1", "My Cal", "fake-token")
        results = cal.add(interval)
        assert len(results) == 1
        assert results[0].success is False
        assert "Expected Event" in str(results[0].error)


# ---------------------------------------------------------------------------
# Test calendars() function
# ---------------------------------------------------------------------------


class TestCalendarsFunction:
    def test_lists_calendars(self):
        response = {
            "items": [
                {"id": "primary", "summary": "Primary"},
                {"id": "work@group.calendar.google.com", "summary": "Work"},
            ]
        }

        mock = _mock_xhr([response])

        with patch("calgebra.gcal._xhr_request", mock):
            cals = calendars("fake-token")

        assert len(cals) == 2
        # Should be sorted by id
        assert cals[0].id == "primary"
        assert cals[1].id == "work@group.calendar.google.com"


# ---------------------------------------------------------------------------
# Test Event dataclass
# ---------------------------------------------------------------------------


class TestEvent:
    def test_from_datetimes(self):
        start = datetime(2025, 1, 15, 14, 0, tzinfo=UTC)
        end = datetime(2025, 1, 15, 15, 0, tzinfo=UTC)
        event = Event.from_datetimes(start=start, end=end, summary="Test")
        assert event.summary == "Test"
        assert event.start == _ts(2025, 1, 15, 14)
        assert event.end == _ts(2025, 1, 15, 15)

    def test_str(self):
        event = Event(start=100, end=200, summary="Test")
        assert "Test" in str(event)
        assert "100" in str(event)

    def test_default_fields(self):
        event = Event(start=100, end=200, summary="Test")
        assert event.id == ""
        assert event.description is None
        assert event.location is None
        assert event.attendees is None
        assert event.reminders is None
        assert event.status == "confirmed"
        assert event.visibility is None
        assert event.transparency is None
