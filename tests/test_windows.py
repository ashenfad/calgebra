"""Tests for built-in time window generators."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from calgebra import Interval, business_hours, weekdays, weekends


def test_weekdays_generates_monday_through_friday():
    """Test that weekdays only generates Mon-Fri."""
    # Week of Jan 6-12, 2025 (Mon-Sun in UTC)
    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    sunday = int(datetime(2025, 1, 12, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    days = list(weekdays(tz="UTC")[monday:sunday])

    # Should get 5 days (Mon-Fri)
    assert len(days) == 5

    # Check first day is Monday, full day
    monday_start = monday
    monday_end = int(datetime(2025, 1, 6, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    assert days[0] == Interval(start=monday_start, end=monday_end)

    # Check last day is Friday
    friday_start = int(datetime(2025, 1, 10, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    friday_end = int(datetime(2025, 1, 10, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    assert days[4] == Interval(start=friday_start, end=friday_end)


def test_weekdays_respects_timezone():
    """Test that weekdays correctly handles timezone conversions."""
    # Jan 6, 2025 00:00 UTC is Jan 5, 2025 16:00 Pacific (Sunday)
    # So Pacific weekdays should start later
    utc_monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    one_day_later = utc_monday + 86400

    utc_days = list(weekdays(tz="UTC")[utc_monday:one_day_later])
    pacific_days = list(weekdays(tz="US/Pacific")[utc_monday:one_day_later])

    # UTC should include Monday 00:00
    assert len(utc_days) == 2  # Monday and Tuesday
    assert utc_days[0].start == utc_monday

    # Pacific Monday starts at UTC 08:00 (midnight Pacific)
    pacific_monday_start = int(
        datetime(2025, 1, 6, 8, 0, 0, tzinfo=timezone.utc).timestamp()
    )
    assert pacific_days[0].start == pacific_monday_start


def test_weekdays_clamps_to_query_bounds():
    """Test that weekdays clamps intervals to query range."""
    # Mid-day Monday to mid-day Wednesday
    monday_noon = int(datetime(2025, 1, 6, 12, 0, 0, tzinfo=timezone.utc).timestamp())
    wednesday_noon = int(
        datetime(2025, 1, 8, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    )

    days = list(weekdays(tz="UTC")[monday_noon:wednesday_noon])

    # Should get 3 partial/full days
    assert len(days) == 3

    # First interval should start at query start (Monday noon)
    assert days[0].start == monday_noon

    # Last interval should end at query end (Wednesday noon)
    assert days[2].end == wednesday_noon


def test_weekdays_requires_finite_bounds():
    """Test that weekdays raises error for unbounded queries."""
    with pytest.raises(ValueError, match="finite start and end bounds"):
        list(weekdays()[:100])

    with pytest.raises(ValueError, match="finite start and end bounds"):
        list(weekdays()[0:])


def test_weekends_generates_saturday_and_sunday():
    """Test that weekends only generates Sat-Sun."""
    # Week of Jan 6-12, 2025 (Mon-Sun in UTC)
    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    sunday = int(datetime(2025, 1, 12, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    days = list(weekends(tz="UTC")[monday:sunday])

    # Should get 2 days (Sat-Sun)
    assert len(days) == 2

    # Check first day is Saturday
    saturday_start = int(
        datetime(2025, 1, 11, 0, 0, 0, tzinfo=timezone.utc).timestamp()
    )
    saturday_end = int(
        datetime(2025, 1, 11, 23, 59, 59, tzinfo=timezone.utc).timestamp()
    )
    assert days[0] == Interval(start=saturday_start, end=saturday_end)

    # Check second day is Sunday
    sunday_start = int(datetime(2025, 1, 12, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    assert days[1].start == sunday_start


def test_weekends_requires_finite_bounds():
    """Test that weekends raises error for unbounded queries."""
    with pytest.raises(ValueError, match="finite start and end bounds"):
        list(weekends()[:100])


def test_business_hours_default_9_to_5():
    """Test that business_hours defaults to 9am-5pm weekdays."""
    # Monday Jan 6, 2025
    monday_start = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    monday_end = int(datetime(2025, 1, 6, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    hours = list(business_hours(tz="UTC")[monday_start:monday_end])

    # Should get one interval (9am-5pm Monday)
    assert len(hours) == 1

    expected_start = int(datetime(2025, 1, 6, 9, 0, 0, tzinfo=timezone.utc).timestamp())
    expected_end = int(
        datetime(2025, 1, 6, 16, 59, 59, tzinfo=timezone.utc).timestamp()
    )

    assert hours[0] == Interval(start=expected_start, end=expected_end)


def test_business_hours_custom_hours():
    """Test business_hours with custom start and end hours."""
    # Monday Jan 6, 2025
    monday_start = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    monday_end = int(datetime(2025, 1, 6, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # 8am-6pm
    hours = list(
        business_hours(tz="UTC", start_hour=8, end_hour=18)[monday_start:monday_end]
    )

    expected_start = int(datetime(2025, 1, 6, 8, 0, 0, tzinfo=timezone.utc).timestamp())
    expected_end = int(
        datetime(2025, 1, 6, 17, 59, 59, tzinfo=timezone.utc).timestamp()
    )

    assert hours[0] == Interval(start=expected_start, end=expected_end)


def test_business_hours_only_weekdays():
    """Test that business_hours excludes weekends."""
    # Friday through Monday (Jan 10-13, 2025)
    friday = int(datetime(2025, 1, 10, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    monday = int(datetime(2025, 1, 13, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    hours = list(business_hours(tz="UTC")[friday:monday])

    # Should get 2 intervals (Friday and Monday, no Sat/Sun)
    assert len(hours) == 2


def test_business_hours_respects_timezone():
    """Test that business_hours handles timezone conversions."""
    # Query in UTC, but business hours in Pacific
    utc_start = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    utc_end = int(datetime(2025, 1, 6, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    pacific_hours = list(business_hours(tz="US/Pacific")[utc_start:utc_end])

    # Pacific 9am-5pm on Jan 6 is UTC 17:00-01:00 (next day)
    # So query should catch the 17:00-23:59 portion on Jan 6
    assert len(pacific_hours) == 1

    # Should start at Pacific 9am = UTC 17:00 on Jan 6
    expected_start = int(
        datetime(2025, 1, 6, 17, 0, 0, tzinfo=timezone.utc).timestamp()
    )
    assert pacific_hours[0].start == expected_start


def test_business_hours_clamps_to_query_bounds():
    """Test that business_hours clamps intervals to query range."""
    # Query from 10am-3pm on Monday
    start = int(datetime(2025, 1, 6, 10, 0, 0, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2025, 1, 6, 15, 0, 0, tzinfo=timezone.utc).timestamp())

    hours = list(business_hours(tz="UTC")[start:end])

    # Should get one clamped interval
    assert len(hours) == 1
    assert hours[0].start == start
    assert hours[0].end == end


def test_business_hours_validates_hour_range():
    """Test that business_hours validates hour parameters."""
    with pytest.raises(ValueError, match="start_hour must be 0-23"):
        business_hours(start_hour=-1)

    with pytest.raises(ValueError, match="start_hour must be 0-23"):
        business_hours(start_hour=24)

    with pytest.raises(ValueError, match="end_hour must be 0-24"):
        business_hours(end_hour=-1)

    with pytest.raises(ValueError, match="end_hour must be 0-24"):
        business_hours(end_hour=25)

    with pytest.raises(ValueError, match="start_hour must be less than end_hour"):
        business_hours(start_hour=17, end_hour=9)

    with pytest.raises(ValueError, match="start_hour must be less than end_hour"):
        business_hours(start_hour=9, end_hour=9)


def test_business_hours_requires_finite_bounds():
    """Test that business_hours raises error for unbounded queries."""
    with pytest.raises(ValueError, match="finite start and end bounds"):
        list(business_hours()[:100])


def test_windows_compose_with_algebra():
    """Test that time windows compose with other timeline operations."""
    # Create a simple busy timeline
    monday_meeting = Interval(
        start=int(datetime(2025, 1, 6, 10, 0, 0, tzinfo=timezone.utc).timestamp()),
        end=int(datetime(2025, 1, 6, 11, 0, 0, tzinfo=timezone.utc).timestamp()),
    )

    from collections.abc import Iterable
    from typing import override

    from calgebra.core import Timeline

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

    busy = SimpleTimeline(monday_meeting)

    # Find free time during business hours on Monday
    monday_start = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    monday_end = int(datetime(2025, 1, 6, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    free = business_hours(tz="UTC") - busy
    free_times = list(free[monday_start:monday_end])

    # Should have free time before (9-10) and after (11-17) the meeting
    assert len(free_times) == 2

    # First slot: 9am-10am
    assert free_times[0].start == int(
        datetime(2025, 1, 6, 9, 0, 0, tzinfo=timezone.utc).timestamp()
    )
    assert free_times[0].end == int(
        datetime(2025, 1, 6, 9, 59, 59, tzinfo=timezone.utc).timestamp()
    )

    # Second slot: 11am-5pm
    assert free_times[1].start == int(
        datetime(2025, 1, 6, 11, 0, 1, tzinfo=timezone.utc).timestamp()
    )
    assert free_times[1].end == int(
        datetime(2025, 1, 6, 16, 59, 59, tzinfo=timezone.utc).timestamp()
    )


def test_weekdays_and_weekends_are_complementary():
    """Test that weekdays and weekends cover all time without overlap."""
    from calgebra import flatten

    # One week
    week_start = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    week_end = int(datetime(2025, 1, 12, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # Union should cover the whole week
    all_time = flatten(weekdays(tz="UTC") | weekends(tz="UTC"))
    coverage = list(all_time[week_start:week_end])

    # Should be a single continuous interval covering the whole week
    assert len(coverage) == 1
    assert coverage[0].start == week_start
    assert coverage[0].end == week_end
