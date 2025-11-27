"""Test that RecurringPattern parameters are preserved when adding to MemoryTimeline.

This test suite specifically covers the bug where recurrence parameters (day, week,
day_of_month, month, start, exdates) were not being preserved when creating enriched
patterns in _add_recurring.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from calgebra.interval import Interval
from calgebra.mutable.memory import MemoryTimeline
from calgebra.recurrence import RecurringPattern
from calgebra.util import DAY, HOUR, MINUTE


def test_preserve_weekly_day_pattern():
    """Test that weekly patterns with specific days are preserved."""
    mem = MemoryTimeline()

    # Create pattern: Every Tuesday and Thursday
    pattern = RecurringPattern(
        freq="weekly",
        day=["tuesday", "thursday"],
        tz="UTC"
    )

    # Add to timeline
    results = mem.add(pattern)
    assert results[0].success

    # Fetch January 2025
    jan_start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    jan_end = int(datetime(2025, 2, 1, tzinfo=timezone.utc).timestamp())

    intervals = list(mem[jan_start:jan_end])

    # Should have Tuesdays and Thursdays only
    assert len(intervals) > 0

    # Verify they're actually Tuesdays and Thursdays
    for ivl in intervals:
        dt = datetime.fromtimestamp(ivl.start, tz=timezone.utc)
        weekday = dt.weekday()  # 0=Monday, 1=Tuesday, ..., 4=Thursday
        assert weekday in [1, 3], f"Expected Tuesday or Thursday, got weekday {weekday}"


def test_preserve_monthly_first_monday():
    """Test that monthly patterns with week offset are preserved."""
    mem = MemoryTimeline()

    # Create pattern: First Monday of each month
    pattern = RecurringPattern(
        freq="monthly",
        day="monday",
        week=1,  # First week
        tz="UTC"
    )

    results = mem.add(pattern)
    assert results[0].success

    # Fetch first 6 months of 2025
    start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2025, 7, 1, tzinfo=timezone.utc).timestamp())

    intervals = list(mem[start:end])

    # Should have 6 first Mondays
    assert len(intervals) == 6

    # Verify each is the first Monday of its month
    for ivl in intervals:
        dt = datetime.fromtimestamp(ivl.start, tz=timezone.utc)
        assert dt.weekday() == 0, "Should be Monday"
        assert dt.day <= 7, "Should be in first week"
        # Check it's actually the first Monday
        first_monday = (7 - dt.weekday()) % 7 + 1 if dt.weekday() != 0 else dt.day
        assert dt.day == first_monday or (dt.day - first_monday) % 7 == 0


def test_preserve_monthly_last_friday():
    """Test that monthly patterns with negative week (last) are preserved."""
    mem = MemoryTimeline()

    # Create pattern: Last Friday of each month
    pattern = RecurringPattern(
        freq="monthly",
        day="friday",
        week=-1,  # Last week
        tz="UTC"
    )

    results = mem.add(pattern)
    assert results[0].success

    # Fetch first 6 months of 2025
    start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2025, 7, 1, tzinfo=timezone.utc).timestamp())

    intervals = list(mem[start:end])

    # Should have 6 last Fridays
    assert len(intervals) == 6

    # Verify each is the last Friday of its month
    for ivl in intervals:
        dt = datetime.fromtimestamp(ivl.start, tz=timezone.utc)
        assert dt.weekday() == 4, "Should be Friday"
        # Check it's in the last week (day >= 22 typically)
        assert dt.day >= 22, f"Last Friday should be late in month, got day {dt.day}"


def test_preserve_day_of_month():
    """Test that day_of_month patterns are preserved."""
    mem = MemoryTimeline()

    # Create pattern: 1st and 15th of each month
    pattern = RecurringPattern(
        freq="monthly",
        day_of_month=[1, 15],
        tz="UTC"
    )

    results = mem.add(pattern)
    assert results[0].success

    # Fetch first 3 months of 2025
    start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2025, 4, 1, tzinfo=timezone.utc).timestamp())

    intervals = list(mem[start:end])

    # Should have 6 intervals (2 per month × 3 months)
    assert len(intervals) == 6

    # Verify they're on the 1st or 15th
    for ivl in intervals:
        dt = datetime.fromtimestamp(ivl.start, tz=timezone.utc)
        assert dt.day in [1, 15], f"Expected day 1 or 15, got {dt.day}"


def test_preserve_yearly_month():
    """Test that yearly patterns with specific months are preserved."""
    mem = MemoryTimeline()

    # Create pattern: June 15th every year
    pattern = RecurringPattern(
        freq="yearly",
        month=6,  # June
        day_of_month=15,
        tz="UTC"
    )

    results = mem.add(pattern)
    assert results[0].success

    # Fetch 2025-2027
    start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2028, 1, 1, tzinfo=timezone.utc).timestamp())

    intervals = list(mem[start:end])

    # Should have 3 intervals (one per year)
    assert len(intervals) == 3

    # Verify they're all June 15th
    for ivl in intervals:
        dt = datetime.fromtimestamp(ivl.start, tz=timezone.utc)
        assert dt.month == 6, f"Expected June, got month {dt.month}"
        assert dt.day == 15, f"Expected day 15, got {dt.day}"


def test_preserve_start_time():
    """Test that start time (time of day) is preserved."""
    mem = MemoryTimeline()

    # Create pattern: Mondays at 9:30 AM
    pattern = RecurringPattern(
        freq="weekly",
        day="monday",
        start=9 * HOUR + 30 * MINUTE,  # 9:30 AM
        duration=HOUR,  # 1 hour duration
        tz="UTC"
    )

    results = mem.add(pattern)
    assert results[0].success

    # Fetch January 2025
    jan_start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    jan_end = int(datetime(2025, 2, 1, tzinfo=timezone.utc).timestamp())

    intervals = list(mem[jan_start:jan_end])

    assert len(intervals) > 0

    # Verify start times are 9:30 AM
    for ivl in intervals:
        dt = datetime.fromtimestamp(ivl.start, tz=timezone.utc)
        assert dt.hour == 9, f"Expected 9 AM, got {dt.hour}"
        assert dt.minute == 30, f"Expected 30 minutes, got {dt.minute}"
        assert dt.second == 0

        # Verify duration is 1 hour
        assert ivl.end is not None
        duration = ivl.end - ivl.start
        assert duration == HOUR, f"Expected 1 hour duration, got {duration}"


def test_preserve_exdates():
    """Test that exdates (excluded dates) are preserved."""
    from dataclasses import dataclass

    @dataclass(frozen=True, kw_only=True)
    class Event(Interval):
        recurring_event_id: str | None = None

    mem = MemoryTimeline()

    # Create pattern: Every Monday with Event class that supports recurring_event_id
    pattern = RecurringPattern(
        freq="weekly",
        day="monday",
        interval_class=Event,
        tz="UTC"
    )

    # Add pattern
    results = mem.add(pattern)
    assert results[0].success

    # Fetch January 2025
    jan_start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    jan_end = int(datetime(2025, 2, 1, tzinfo=timezone.utc).timestamp())

    intervals_before = list(mem[jan_start:jan_end])
    assert len(intervals_before) >= 4

    # Find the second Monday (should have recurring_event_id)
    second_monday = intervals_before[1]
    assert second_monday.start is not None
    assert hasattr(second_monday, "recurring_event_id")
    assert second_monday.recurring_event_id is not None

    # Remove it (adds to exdates)
    remove_results = mem.remove(second_monday)
    assert remove_results[0].success

    # Fetch again - should have one fewer interval
    intervals_after = list(mem[jan_start:jan_end])
    assert len(intervals_after) == len(intervals_before) - 1

    # Verify the removed one is gone
    removed_start = second_monday.start
    assert removed_start is not None
    for ivl in intervals_after:
        assert ivl.start != removed_start, "Excluded date should not appear"


def test_preserve_interval_parameter():
    """Test that interval (every N units) is preserved."""
    mem = MemoryTimeline()

    # Create pattern: Every other Tuesday (bi-weekly)
    pattern = RecurringPattern(
        freq="weekly",
        day="tuesday",
        interval=2,  # Every 2 weeks
        tz="UTC"
    )

    results = mem.add(pattern)
    assert results[0].success

    # Fetch first 2 months of 2025
    start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2025, 3, 1, tzinfo=timezone.utc).timestamp())

    intervals = list(mem[start:end])

    # Should have fewer intervals than weekly (about half)
    assert len(intervals) >= 2

    # Verify spacing is approximately 2 weeks (14 days)
    if len(intervals) >= 2:
        for i in range(len(intervals) - 1):
            current = intervals[i]
            next_ivl = intervals[i + 1]
            assert current.start is not None
            assert next_ivl.start is not None
            spacing = next_ivl.start - current.start
            # Should be approximately 14 days (allow some tolerance)
            days = spacing / DAY
            assert 13 <= days <= 15, f"Expected ~14 days spacing, got {days}"


def test_preserve_quarterly_pattern():
    """Test that quarterly patterns (every 3 months) are preserved."""
    mem = MemoryTimeline()

    # Create pattern: 1st of every 3 months (quarterly)
    pattern = RecurringPattern(
        freq="monthly",
        day_of_month=1,
        interval=3,  # Every 3 months
        tz="UTC"
    )

    results = mem.add(pattern)
    assert results[0].success

    # Fetch 2025
    start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())

    intervals = list(mem[start:end])

    # Should have 4 intervals (quarterly)
    assert len(intervals) == 4

    # Verify they're on the 1st of Jan, Apr, Jul, Oct
    expected_months = [1, 4, 7, 10]
    for ivl, expected_month in zip(intervals, expected_months):
        dt = datetime.fromtimestamp(ivl.start, tz=timezone.utc)
        assert dt.month == expected_month, (
            f"Expected month {expected_month}, got {dt.month}"
        )
        assert dt.day == 1, f"Expected day 1, got {dt.day}"


def test_preserve_complex_pattern():
    """Test that complex patterns with multiple parameters are preserved."""
    mem = MemoryTimeline()

    # Create complex pattern: Second Tuesday of March, June, September, December
    pattern = RecurringPattern(
        freq="monthly",
        day="tuesday",
        week=2,  # Second week
        day_of_month=None,  # Use day of week instead
        month=[3, 6, 9, 12],  # Q1, Q2, Q3, Q4 months
        interval=1,
        tz="UTC"
    )

    # Actually, monthly with month filter requires yearly freq
    # Let's use yearly with month filter instead
    pattern = RecurringPattern(
        freq="yearly",
        month=[3, 6, 9, 12],  # March, June, September, December
        day="tuesday",
        week=2,  # Second Tuesday
        tz="UTC"
    )

    results = mem.add(pattern)
    assert results[0].success

    # Fetch 2025-2026
    start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2027, 1, 1, tzinfo=timezone.utc).timestamp())

    intervals = list(mem[start:end])

    # Should have 8 intervals (4 months × 2 years)
    assert len(intervals) == 8

    # Verify they're all second Tuesdays of the specified months
    for ivl in intervals:
        dt = datetime.fromtimestamp(ivl.start, tz=timezone.utc)
        assert dt.month in [3, 6, 9, 12], (
            f"Expected March/Jun/Sep/Dec, got month {dt.month}"
        )
        assert dt.weekday() == 1, "Should be Tuesday"
        # Check it's in second week (day 8-14)
        assert 8 <= dt.day <= 14, f"Second Tuesday should be day 8-14, got {dt.day}"


def test_pattern_equivalence_before_and_after_add():
    """Test that pattern generates same intervals before and after adding."""
    # Create original pattern
    original_pattern = RecurringPattern(
        freq="weekly",
        day="wednesday",
        start=14 * HOUR,  # 2 PM
        duration=2 * HOUR,  # 2 hours
        tz="UTC"
    )

    # Generate intervals from original
    jan_start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    jan_end = int(datetime(2025, 2, 1, tzinfo=timezone.utc).timestamp())

    original_intervals = list(original_pattern[jan_start:jan_end])

    # Add to timeline
    mem = MemoryTimeline()
    results = mem.add(original_pattern)
    assert results[0].success

    # Fetch from timeline
    timeline_intervals = list(mem[jan_start:jan_end])

    # Should generate same intervals
    assert len(timeline_intervals) == len(original_intervals)

    # Compare each interval
    for orig, stored in zip(original_intervals, timeline_intervals):
        assert orig.start == stored.start
        assert orig.end == stored.end


def test_preserve_timezone():
    """Test that timezone is preserved."""
    mem = MemoryTimeline()

    # Create pattern in Pacific timezone
    pattern = RecurringPattern(
        freq="daily",
        start=9 * HOUR,  # 9 AM
        tz="US/Pacific"
    )

    results = mem.add(pattern)
    assert results[0].success

    # Fetch a few days (Jan 1-4, which should give us 4 intervals)
    # Use Jan 1 00:00 UTC to Jan 4 23:59 UTC to get exactly 4 days
    start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2025, 1, 5, tzinfo=timezone.utc).timestamp())

    intervals = list(mem[start:end])

    # Should have at least 4 intervals
    assert len(intervals) >= 4

    # Verify times are in Pacific timezone
    # Filter to intervals that actually start within our query window
    # (some might overlap from before due to duration)
    pacific_tz = ZoneInfo("US/Pacific")
    query_start_pacific = datetime(2025, 1, 1, tzinfo=pacific_tz)

    for ivl in intervals:
        dt_utc = datetime.fromtimestamp(ivl.start, tz=timezone.utc)
        # Convert to Pacific to verify
        dt_pacific = dt_utc.astimezone(pacific_tz)

        # Only check intervals that start on or after Jan 1 in Pacific time
        if dt_pacific >= query_start_pacific:
            assert dt_pacific.hour == 9, (
                f"Expected 9 AM Pacific, got {dt_pacific.hour} for {dt_pacific}"
            )
            assert dt_pacific.minute == 0, (
                f"Expected 0 minutes, got {dt_pacific.minute}"
            )

