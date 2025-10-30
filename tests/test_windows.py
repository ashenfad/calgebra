"""Tests for built-in time window generators."""

from datetime import datetime, timezone

import pytest
from typing_extensions import override

from calgebra import HOUR, MINUTE, Interval, Timeline, day_of_week, time_of_day


def test_day_of_week_single_day():
    """Test generating intervals for a single day of the week."""
    # Week of Jan 6-12, 2025 (Mon-Sun in UTC)
    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    sunday = int(datetime(2025, 1, 12, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    mondays = list(day_of_week("monday", tz="UTC")[monday:sunday])

    # Should get 1 day (just Monday)
    assert len(mondays) == 1

    monday_start = monday
    monday_end = int(datetime(2025, 1, 6, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    assert mondays[0] == Interval(start=monday_start, end=monday_end)


def test_day_of_week_multiple_days():
    """Test generating intervals for multiple days of the week.
    
    Adjacent days are merged by flatten, so Mon-Fri becomes one interval.
    """
    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    sunday = int(datetime(2025, 1, 12, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # Weekdays (Mon-Fri)
    weekdays = day_of_week(
        ["monday", "tuesday", "wednesday", "thursday", "friday"], tz="UTC"
    )
    days = list(weekdays[monday:sunday])

    # Adjacent days are merged into one continuous interval
    assert len(days) == 1
    
    # Verify it covers Monday through Friday
    monday_start = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    friday_end = int(datetime(2025, 1, 10, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    assert days[0].start == monday_start
    assert days[0].end == friday_end


def test_day_of_week_case_insensitive():
    """Test that day names are case-insensitive."""
    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    tuesday = int(datetime(2025, 1, 7, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    mondays_lower = list(day_of_week("monday")[monday:tuesday])
    mondays_upper = list(day_of_week("MONDAY")[monday:tuesday])
    mondays_mixed = list(day_of_week("Monday")[monday:tuesday])

    assert mondays_lower == mondays_upper == mondays_mixed


def test_day_of_week_invalid_day():
    """Test that invalid day names raise ValueError."""
    with pytest.raises(ValueError, match="Invalid day"):
        day_of_week("notaday")


def test_day_of_week_respects_timezone():
    """Test that day_of_week correctly handles timezone conversions."""
    # Jan 6, 2025 00:00 UTC is Jan 5, 2025 16:00 Pacific (Sunday)
    utc_monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    one_day_later = utc_monday + 86400

    utc_mondays = list(day_of_week("monday", tz="UTC")[utc_monday:one_day_later])
    pacific_mondays = list(
        day_of_week("monday", tz="US/Pacific")[utc_monday:one_day_later]
    )

    # UTC should include Monday only (one full day)
    assert len(utc_mondays) == 1

    # Pacific Monday starts at UTC 08:00 (midnight Pacific)
    pacific_monday_start = int(
        datetime(2025, 1, 6, 8, 0, 0, tzinfo=timezone.utc).timestamp()
    )
    assert pacific_mondays[0].start == pacific_monday_start


def test_day_of_week_requires_finite_start():
    """Test that day_of_week requires finite start (but supports unbounded end)."""
    with pytest.raises(ValueError, match="requires finite start"):
        list(day_of_week("monday")[:100])


def test_time_of_day_full_day():
    """Test time_of_day with default full day.
    
    Adjacent full days are merged by flatten into one continuous interval.
    """
    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    tuesday = int(datetime(2025, 1, 7, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # Default is all 24 hours
    all_day = list(time_of_day(tz="UTC")[monday:tuesday])

    # Adjacent full days are merged into one interval
    assert len(all_day) == 1
    assert all_day[0].start == monday
    assert all_day[0].end == tuesday


def test_time_of_day_specific_hours():
    """Test time_of_day with specific hour range."""
    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    monday_end = int(datetime(2025, 1, 6, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # 9am-5pm (8 hours)
    work_hours = list(
        time_of_day(start=9 * HOUR, duration=8 * HOUR, tz="UTC")[monday:monday_end]
    )

    assert len(work_hours) == 1

    expected_start = int(datetime(2025, 1, 6, 9, 0, 0, tzinfo=timezone.utc).timestamp())
    expected_end = int(
        datetime(2025, 1, 6, 16, 59, 59, tzinfo=timezone.utc).timestamp()
    )

    assert work_hours[0] == Interval(start=expected_start, end=expected_end)


def test_time_of_day_fractional_hours():
    """Test time_of_day with minute precision."""
    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    monday_end = int(datetime(2025, 1, 6, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # 9:30am-10am (30 minutes)
    standup = list(
        time_of_day(start=9 * HOUR + 30 * MINUTE, duration=30 * MINUTE, tz="UTC")[
            monday:monday_end
        ]
    )

    assert len(standup) == 1

    expected_start = int(
        datetime(2025, 1, 6, 9, 30, 0, tzinfo=timezone.utc).timestamp()
    )
    expected_end = int(datetime(2025, 1, 6, 9, 59, 59, tzinfo=timezone.utc).timestamp())

    assert standup[0] == Interval(start=expected_start, end=expected_end)


def test_time_of_day_validates_parameters():
    """Test that time_of_day validates parameters."""

    with pytest.raises(ValueError, match="start must be in range"):
        time_of_day(start=-1)

    with pytest.raises(ValueError, match="start must be in range"):
        time_of_day(start=25 * HOUR)

    with pytest.raises(ValueError, match="duration must be positive"):
        time_of_day(duration=0)

    with pytest.raises(ValueError, match="duration must be positive"):
        time_of_day(duration=-1)

    with pytest.raises(ValueError, match="cannot exceed 24 hours"):
        time_of_day(start=20 * HOUR, duration=5 * HOUR)


def test_time_of_day_requires_finite_start():
    """Test that time_of_day requires finite start (but supports unbounded end)."""
    with pytest.raises(ValueError, match="requires finite start"):
        list(time_of_day()[:100])


def test_composition_business_hours():
    """Test composing day_of_week and time_of_day for business hours."""

    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    sunday = int(datetime(2025, 1, 12, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # Business hours = weekdays & 9-5
    weekdays = day_of_week(
        ["monday", "tuesday", "wednesday", "thursday", "friday"], tz="UTC"
    )
    work_hours = time_of_day(start=9 * HOUR, duration=8 * HOUR, tz="UTC")

    # Intersection of mask timelines auto-flattens
    business_hours = weekdays & work_hours

    hours = list(business_hours[monday:sunday])

    # Should get 5 days (Mon-Fri), each with 9-5 window
    assert len(hours) == 5

    # Check first day is Monday 9-5
    expected_start = int(datetime(2025, 1, 6, 9, 0, 0, tzinfo=timezone.utc).timestamp())
    expected_end = int(
        datetime(2025, 1, 6, 16, 59, 59, tzinfo=timezone.utc).timestamp()
    )
    assert hours[0] == Interval(start=expected_start, end=expected_end)


def test_composition_recurring_meeting():
    """Test composing for a specific recurring meeting time."""

    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    next_month = int(datetime(2025, 2, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())

    # Monday standup: every Monday at 9:30am for 30 min
    mondays = day_of_week("monday", tz="UTC")
    standup_time = time_of_day(
        start=9 * HOUR + 30 * MINUTE, duration=30 * MINUTE, tz="UTC"
    )

    # Intersection of mask timelines auto-flattens
    monday_standup = mondays & standup_time

    standups = list(monday_standup[monday:next_month])

    # Should get ~5 Mondays in a month
    assert 4 <= len(standups) <= 5

    # Each should be 9:30-10am
    for standup in standups:
        duration = standup.end - standup.start + 1
        assert duration == 1800  # 30 minutes


def test_composition_with_calendar():
    """Test composing time windows with calendar operations."""

    class SimpleTimeline(Timeline[Interval]):
        def __init__(self, *events):
            self.events = list(events)

        @override
        def fetch(self, start, end):
            for event in self.events:
                if start is not None and event.end < start:
                    continue
                if end is not None and event.start > end:
                    break
                yield event

    # Monday with a 10am-11am meeting
    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    monday_end = int(datetime(2025, 1, 6, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    meeting = Interval(
        start=int(datetime(2025, 1, 6, 10, 0, 0, tzinfo=timezone.utc).timestamp()),
        end=int(datetime(2025, 1, 6, 11, 0, 0, tzinfo=timezone.utc).timestamp()),
    )
    busy = SimpleTimeline(meeting)

    # Find free time during business hours
    weekdays = day_of_week(["monday"], tz="UTC")
    work_hours = time_of_day(start=9 * HOUR, duration=8 * HOUR, tz="UTC")

    # Intersection of mask timelines auto-flattens
    business_hours = weekdays & work_hours

    free = business_hours - busy
    free_times = list(free[monday:monday_end])

    # Should have free time before (9-10) and after (11-17) the meeting
    assert len(free_times) == 2


def test_weekend_pattern():
    """Test creating weekend pattern with day_of_week.
    
    Adjacent days (Saturday and Sunday) are merged into one continuous interval.
    """
    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    sunday = int(datetime(2025, 1, 12, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    weekends = day_of_week(["saturday", "sunday"], tz="UTC")
    days = list(weekends[monday:sunday])

    # Adjacent days are merged into one interval
    assert len(days) == 1

    saturday_start = int(
        datetime(2025, 1, 11, 0, 0, 0, tzinfo=timezone.utc).timestamp()
    )
    sunday_end = int(
        datetime(2025, 1, 12, 23, 59, 59, tzinfo=timezone.utc).timestamp()
    )
    assert days[0].start == saturday_start
    assert days[0].end == sunday_end
