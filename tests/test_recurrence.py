"""Tests for recurring interval generators."""

from datetime import datetime, timezone

import pytest

from calgebra import Interval, recurring


def test_recurring_weekly_single_day():
    """Test recurring weekly pattern for a single day."""
    # Week of Jan 6-12, 2025 (Mon-Sun in UTC)
    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    sunday = int(datetime(2025, 1, 12, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    mondays = list(recurring(freq="weekly", day="monday", tz="UTC")[monday:sunday])

    # Should get 1 Monday
    assert len(mondays) == 1


def test_recurring_weekly_multiple_days():
    """Test recurring weekly pattern for multiple days."""
    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    sunday = int(datetime(2025, 1, 12, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # Mon/Wed/Fri
    mwf = list(
        recurring(freq="weekly", day=["monday", "wednesday", "friday"], tz="UTC")[
            monday:sunday
        ]
    )

    # Should get 3 days
    assert len(mwf) == 3


def test_recurring_weekly_with_time_window():
    """Test recurring weekly with specific time window."""
    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    sunday = int(datetime(2025, 1, 12, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # Every Monday at 9:30am for 30 minutes
    standup = list(
        recurring(
            freq="weekly",
            day="monday",
            start_hour=9.5,
            duration_hours=0.5,
            tz="UTC",
        )[monday:sunday]
    )

    assert len(standup) == 1

    # Check duration is 30 minutes
    duration = standup[0].end - standup[0].start + 1
    assert duration == 1800  # 30 minutes in seconds


def test_recurring_biweekly():
    """Test bi-weekly (every other week) pattern."""
    # 4 weeks
    start = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2025, 2, 3, 0, 0, 0, tzinfo=timezone.utc).timestamp())

    # Every other Monday
    biweekly = list(
        recurring(freq="weekly", interval=2, day="monday", tz="UTC")[start:end]
    )

    # Should get 3 Mondays (Jan 6, Jan 20, Feb 3) - rrule includes start date
    assert len(biweekly) == 3


def test_recurring_monthly_first_weekday():
    """Test first weekday of each month."""
    # 3 months
    start = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2025, 3, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # First Monday of each month
    first_monday = list(
        recurring(freq="monthly", week=1, day="monday", tz="UTC")[start:end]
    )

    # Should get 3 (one per month: Jan, Feb, Mar)
    assert len(first_monday) == 3


def test_recurring_monthly_last_weekday():
    """Test last weekday of each month."""
    # 3 months
    start = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2025, 3, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # Last Friday of each month
    last_friday = list(
        recurring(freq="monthly", week=-1, day="friday", tz="UTC")[start:end]
    )

    # Should get 3 (one per month)
    assert len(last_friday) == 3


def test_recurring_monthly_day_of_month():
    """Test specific day of month."""
    # 3 months
    start = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2025, 3, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # 15th of every month
    fifteenth = list(recurring(freq="monthly", day_of_month=15, tz="UTC")[start:end])

    # Should get 3 (Jan 15, Feb 15, Mar 15)
    assert len(fifteenth) == 3


def test_recurring_monthly_multiple_days():
    """Test multiple days of month (e.g., paydays)."""
    # 2 months
    start = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2025, 2, 28, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # 1st and 15th of every month
    paydays = list(recurring(freq="monthly", day_of_month=[1, 15], tz="UTC")[start:end])

    # Should get 4 (Jan 1, Jan 15, Feb 1, Feb 15)
    assert len(paydays) == 4


def test_recurring_quarterly():
    """Test quarterly pattern (every 3 months)."""
    # 1 year
    start = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # Quarterly on the 1st
    quarterly = list(
        recurring(freq="monthly", interval=3, day_of_month=1, tz="UTC")[start:end]
    )

    # Should get 4 (Jan, Apr, Jul, Oct)
    assert len(quarterly) == 4


def test_recurring_daily():
    """Test daily pattern."""
    # 1 week
    start = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2025, 1, 12, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # Every day at 9am for 1 hour
    daily = list(
        recurring(freq="daily", start_hour=9, duration_hours=1, tz="UTC")[start:end]
    )

    # Should get 7 days
    assert len(daily) == 7


def test_recurring_requires_finite_bounds():
    """Test that recurring requires finite bounds."""
    with pytest.raises(ValueError, match="finite start and end bounds"):
        list(recurring(freq="weekly", day="monday")[:100])


def test_recurring_invalid_day():
    """Test that invalid day names raise ValueError."""
    with pytest.raises(ValueError, match="Invalid day"):
        recurring(freq="weekly", day="notaday")


def test_comparison_with_windows_primitives():
    """Compare recurring() with day_of_week + time_of_day approach."""
    from calgebra import day_of_week, flatten, time_of_day

    monday = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    sunday = int(datetime(2025, 1, 12, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # Approach 1: recurring (one call)
    option_a = list(
        recurring(
            freq="weekly",
            day="monday",
            start_hour=9.5,
            duration_hours=0.5,
            tz="UTC",
        )[monday:sunday]
    )

    # Approach 2: day_of_week + time_of_day (composition)
    option_b = list(
        flatten(
            day_of_week("monday", tz="UTC")
            & time_of_day(start_hour=9.5, duration_hours=0.5, tz="UTC")
        )[monday:sunday]
    )

    # Should produce same results
    assert len(option_a) == len(option_b) == 1
    assert option_a[0] == option_b[0]


def test_recurring_simplifies_common_patterns():
    """Show how recurring() simplifies common patterns."""
    start = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # These patterns are much simpler with recurring():

    # First Monday of each month
    first_mondays = recurring(freq="monthly", week=1, day="monday", tz="UTC")
    assert 10 <= len(list(first_mondays[start:end])) <= 12

    # Bi-weekly Tuesday standup
    biweekly_standup = recurring(
        freq="weekly",
        interval=2,
        day="tuesday",
        start_hour=10,
        duration_hours=0.5,
        tz="UTC",
    )
    assert 20 <= len(list(biweekly_standup[start:end])) <= 30

    # Quarterly reviews (every 3 months on 1st at 2pm)
    quarterly = recurring(
        freq="monthly",
        interval=3,
        day_of_month=1,
        start_hour=14,
        duration_hours=2,
        tz="UTC",
    )
    assert len(list(quarterly[start:end])) == 4
