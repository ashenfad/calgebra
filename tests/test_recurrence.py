"""Tests for recurring interval generators."""

from datetime import datetime, timezone

import pytest

from calgebra import HOUR, MINUTE, recurring


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
            start=9 * HOUR + 30 * MINUTE,
            duration=30 * MINUTE,
            tz="UTC",
        )[monday:sunday]
    )

    assert len(standup) == 1

    # Check duration is 30 minutes
    assert standup[0].start is not None and standup[0].end is not None
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
        recurring(freq="daily", start=9 * HOUR, duration=HOUR, tz="UTC")[start:end]
    )

    # Should get 7 days
    assert len(daily) == 7


def test_recurring_requires_finite_start():
    """Test that recurring requires finite start bound."""
    with pytest.raises(ValueError, match="requires finite start"):
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
            start=9 * HOUR + 30 * MINUTE,
            duration=30 * MINUTE,
            tz="UTC",
        )[monday:sunday]
    )

    # Approach 2: day_of_week + time_of_day (composition)
    option_b = list(
        flatten(
            day_of_week("monday", tz="UTC")
            & time_of_day(start=9 * HOUR + 30 * MINUTE, duration=30 * MINUTE, tz="UTC")
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
        start=10 * HOUR,
        duration=30 * MINUTE,
        tz="UTC",
    )
    assert 20 <= len(list(biweekly_standup[start:end])) <= 30

    # Quarterly reviews (every 3 months on 1st at 2pm)
    quarterly = recurring(
        freq="monthly",
        interval=3,
        day_of_month=1,
        start=14 * HOUR,
        duration=2 * HOUR,
        tz="UTC",
    )
    assert len(list(quarterly[start:end])) == 4


def test_recurring_yearly_single_month():
    """Test yearly pattern on a specific month."""
    # 3 years
    start = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2027, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # Every January 1st
    new_years = list(
        recurring(freq="yearly", month=1, day_of_month=1, tz="UTC")[start:end]
    )

    # Should get 3 (2025, 2026, 2027)
    assert len(new_years) == 3


def test_recurring_yearly_multiple_months():
    """Test yearly pattern on multiple months (e.g., quarterly dates)."""
    # 2 years
    start = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # Jan 1, Apr 1, Jul 1, Oct 1 each year
    quarterly_dates = list(
        recurring(freq="yearly", month=[1, 4, 7, 10], day_of_month=1, tz="UTC")[
            start:end
        ]
    )

    # Should get 8 (4 per year × 2 years)
    assert len(quarterly_dates) == 8


def test_recurring_yearly_with_time_window():
    """Test yearly pattern with specific time window."""
    # 2 years
    start = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # Company anniversary party: June 15th at 5pm for 3 hours
    anniversary = list(
        recurring(
            freq="yearly",
            month=6,
            day_of_month=15,
            start=17 * HOUR,
            duration=3 * HOUR,
            tz="UTC",
        )[start:end]
    )

    # Should get 2 (one per year)
    assert len(anniversary) == 2

    # Check duration is 3 hours
    assert anniversary[0].start is not None and anniversary[0].end is not None
    duration = anniversary[0].end - anniversary[0].start + 1
    assert duration == 10800  # 3 hours in seconds


def test_recurring_yearly_month_only():
    """Test yearly pattern on entire month."""
    # 2 years
    start = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # Every December (full days)
    december = list(recurring(freq="yearly", month=12, tz="UTC")[start:end])

    # Should get 2 Decembers (2025, 2026) - one event per year starting Dec 1
    assert len(december) == 2


def test_recurring_unbounded_end():
    """Test that recurring supports unbounded end queries via itertools."""
    from itertools import islice

    start = int(datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())

    # Get next 5 Mondays
    mondays = recurring(freq="weekly", day="monday", tz="UTC")
    next_five = list(islice(mondays[start:], 5))

    assert len(next_five) == 5

    # Verify they're all Mondays
    for interval in next_five:
        assert interval.start is not None
        dt = datetime.fromtimestamp(interval.start, tz=timezone.utc)
        assert dt.weekday() == 0  # Monday


def test_recurring_lookback_bug_fix():
    """Test that long-duration events starting before query are included."""
    # Query starts at Jan 10, 2pm
    query_start = int(datetime(2025, 1, 10, 14, 0, 0, tzinfo=timezone.utc).timestamp())
    query_end = int(datetime(2025, 1, 20, 0, 0, 0, tzinfo=timezone.utc).timestamp())

    # Weekly event on Fridays at noon, 40-hour duration (extends into Sunday)
    # Jan 10 is a Friday, so the event runs from Jan 10 noon to Jan 12 4am
    long_events = recurring(
        freq="weekly", day="friday", start=12 * HOUR, duration=40 * HOUR, tz="UTC"
    )

    results = list(long_events[query_start:query_end])

    # Should include:
    # 1. Jan 10 Friday event (starts at noon, query starts at 2pm - should be clamped)
    # 2. Jan 17 Friday event
    assert len(results) >= 2

    # First event should start at query_start (clamped from Jan 10 noon)
    assert results[0].start == query_start


def test_recurring_paging_merges_fragments():
    """Test that unbounded queries work and flatten merges properly."""
    from itertools import islice

    start = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())

    # Weekly pattern spanning multiple months (will use multiple pages internally for long queries)
    weekly = recurring(freq="weekly", day="monday", tz="UTC")

    # Get 10 results
    results = list(islice(weekly[start:], 10))

    assert len(results) == 10

    # Verify they're consecutive weeks (should be 7 days apart)
    for i in range(len(results) - 1):
        current_start = results[i].start
        next_start = results[i + 1].start
        assert current_start is not None and next_start is not None
        # Should be exactly 7 days (604800 seconds) apart
        assert next_start - current_start == 604800


def test_recurring_duration_exceeds_interval():
    """Test recurring patterns where duration > interval_between_occurrences.

    This is the edge case where multiple previous occurrences overlap with
    the query start. The lookback should find all of them, and after flattening
    they should create continuous coverage.
    """
    from calgebra import DAY

    # Daily events with 3-day duration: each event overlaps with next 2
    # Query starts on Jan 5
    query_start = int(datetime(2025, 1, 5, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    query_end = int(datetime(2025, 1, 10, 0, 0, 0, tzinfo=timezone.utc).timestamp())

    long_events = recurring(freq="daily", duration=3 * DAY, tz="UTC")

    results = list(long_events[query_start:query_end])

    # recurring() returns flattened intervals, so overlapping events merge
    # Daily events with 3-day duration create continuous coverage
    # Should get one continuous interval covering the entire query range
    assert len(results) == 1

    # Should span the entire query range
    assert results[0].start == query_start
    assert results[0].end == query_end


def test_recurring_weekly_with_multi_day_duration():
    """Test weekly events that span multiple days."""
    # Weekly events on Fridays with 3-day duration (Fri-Sun)
    query_start = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    query_end = int(datetime(2025, 1, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    weekend_events = recurring(
        freq="weekly", day="friday", duration=3 * 86400, tz="UTC"
    )

    results = list(weekend_events[query_start:query_end])

    # January 2025: Fridays are Jan 3, 10, 17, 24, 31
    assert len(results) == 5

    # First 4 events should be 3 days long
    for interval in results[:4]:
        assert interval.start is not None and interval.end is not None
        duration = interval.end - interval.start + 1
        assert duration == 3 * 86400, f"Expected 3 days, got {duration/86400:.2f} days"

    # Last event (Jan 31) extends beyond query range and gets clamped
    # Just verify it starts on Jan 31
    jan_31 = int(datetime(2025, 1, 31, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    assert results[4].start == jan_31


def test_recurring_flatten_merges_overlapping_durations():
    """Test that overlapping recurring events are already flattened by recurring()."""
    from calgebra import DAY, recurring
    from calgebra.recurrence import _RawRecurringTimeline

    query_start = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    query_end = int(datetime(2025, 1, 10, 0, 0, 0, tzinfo=timezone.utc).timestamp())

    # Daily events with 2-day duration: creates continuous coverage
    # recurring() already applies flatten(), so check raw timeline first
    raw = _RawRecurringTimeline(freq="daily", duration=2 * DAY, tz="UTC")
    raw_results = list(raw.fetch(query_start, query_end))

    # Raw should have many overlapping intervals (one per day)
    assert len(raw_results) >= 10

    # recurring() returns flattened results
    flattened = recurring(freq="daily", duration=2 * DAY, tz="UTC")
    flattened_results = list(flattened[query_start:query_end])

    # After flatten: should be one continuous interval
    assert len(flattened_results) == 1

    # Should cover the entire query range
    assert flattened_results[0].start == query_start
    assert flattened_results[0].end == query_end


def test_recurring_lookback_multiple_previous():
    """Test that lookback correctly finds multiple previous occurrences.

    Without proper lookback, events starting before the query but extending
    into it would be missed, causing gaps in coverage.
    """
    from calgebra import DAY

    # Start query on Jan 10
    query_start = int(datetime(2025, 1, 10, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    query_end = int(datetime(2025, 1, 15, 0, 0, 0, tzinfo=timezone.utc).timestamp())

    # Daily events with 5-day duration
    # Jan 6 extends to Jan 11 (overlaps with query start)
    # Jan 7 extends to Jan 12 (overlaps with query start)
    # Jan 8 extends to Jan 13 (overlaps with query start)
    # Jan 9 extends to Jan 14 (overlaps with query start)
    # Jan 10+ extends to Jan 15+ (starts at/after query start)
    long_events = recurring(freq="daily", duration=5 * DAY, tz="UTC")

    results = list(long_events[query_start:query_end])

    # After flattening, should have continuous coverage
    # (if lookback missed previous events, there would be gaps)
    assert len(results) == 1, "Should be one continuous interval after flattening"

    # Should cover the entire query range
    assert results[0].start == query_start
    assert results[0].end == query_end


def test_recurring_raw_lookback_captures_all_overlaps():
    """Test that raw recurring timeline (before flatten) captures all overlapping events.

    This directly tests the _generate_page lookback logic.
    """
    from calgebra import DAY
    from calgebra.recurrence import _RawRecurringTimeline

    # Create raw timeline (bypasses the flatten in recurring())
    raw = _RawRecurringTimeline(
        freq="daily", duration=4 * DAY, tz="UTC"  # 4-day duration on daily events
    )

    # Query starts on Jan 10
    query_start = int(datetime(2025, 1, 10, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    query_end = int(datetime(2025, 1, 15, 0, 0, 0, tzinfo=timezone.utc).timestamp())

    results = list(raw.fetch(query_start, query_end))

    # Should capture events from Jan 7, 8, 9, 10, 11, 12, 13, 14, 15
    # (Jan 7 extends to Jan 11, overlapping with query start)
    jan_7 = int(datetime(2025, 1, 7, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    jan_8 = int(datetime(2025, 1, 8, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    jan_9 = int(datetime(2025, 1, 9, 0, 0, 0, tzinfo=timezone.utc).timestamp())

    event_starts = {r.start for r in results}

    # Verify we captured the previous overlapping events
    assert (
        jan_7 in event_starts
    ), "Should include Jan 7 (extends to Jan 11, overlaps query)"
    assert (
        jan_8 in event_starts
    ), "Should include Jan 8 (extends to Jan 12, overlaps query)"
    assert (
        jan_9 in event_starts
    ), "Should include Jan 9 (extends to Jan 13, overlaps query)"

    # Should have at least 9 events (Jan 7-15)
    assert len(results) >= 9
