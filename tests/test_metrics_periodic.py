"""Tests for period-based aggregation API in metrics module."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from calgebra import Interval, timeline
from calgebra.metrics import (
    count_intervals,
    coverage_ratio,
    max_duration,
    min_duration,
    total_duration,
)


class TestBoundCoercion:
    """Test _coerce_bound helper via public API."""

    def test_int_bounds(self):
        """Unix timestamps pass through unchanged."""
        t = timeline(Interval(start=1000, end=2000))
        result = total_duration(t, start=0, end=3000)
        assert len(result) == 1
        # Just check the value, not the exact date label
        assert result[0][1] == 1000

    def test_date_bounds(self):
        """Date objects convert to midnight in specified timezone."""
        # Nov 1-2, 2025 UTC
        t = timeline(Interval(start=1761955200, end=1762041600))  # Nov 1, 2025
        result = total_duration(
            t, start=date(2025, 11, 1), end=date(2025, 11, 3), tz="UTC"
        )
        assert len(result) == 1
        assert result[0][1] == 86400  # 1 day

    def test_datetime_bounds_timezone_aware(self):
        """Timezone-aware datetime works correctly."""
        utc = ZoneInfo("UTC")
        t = timeline(Interval(start=1000, end=2000))
        result = total_duration(
            t,
            start=datetime(1970, 1, 1, 0, 0, tzinfo=utc),
            end=datetime(1970, 1, 1, 1, 0, tzinfo=utc),
        )
        assert len(result) == 1
        assert result[0][1] == 1000

    def test_datetime_bounds_naive_raises(self):
        """Naive datetime raises TypeError."""
        t = timeline(Interval(start=1000, end=2000))
        with pytest.raises(TypeError, match="Naive datetime not allowed"):
            total_duration(
                t,
                start=datetime(1970, 1, 1, 0, 0),  # No timezone!
                end=datetime(1970, 1, 1, 1, 0),
            )

    def test_mixed_bound_types(self):
        """Can mix different bound types."""
        t = timeline(Interval(start=1000, end=2000))
        result = total_duration(
            t,
            start=1000,  # int
            end=datetime.fromtimestamp(3000, tz=timezone.utc),  # datetime
        )
        assert len(result) == 1


class TestPeriodFull:
    """Test period='full' (exact bounds, no snapping)."""

    def test_full_single_interval(self):
        """Full period returns single aggregate."""
        t = timeline(Interval(start=1000, end=2000))
        result = coverage_ratio(t, start=0, end=3000, period="full")
        assert len(result) == 1
        date_label, ratio = result[0]
        assert ratio == pytest.approx(1000 / 3000)

    def test_full_uses_exact_bounds(self):
        """Full period doesn't snap to calendar."""
        # 3pm Monday to 9am Friday
        t = timeline(Interval(start=1000, end=2000))
        result = total_duration(t, start=500, end=2500, period="full")
        assert len(result) == 1
        assert result[0][1] == 1000  # Exactly the overlap


class TestPeriodDay:
    """Test period='day' aggregations."""

    def test_daily_snaps_to_midnight(self):
        """Daily periods align to full calendar days."""
        # Nov 1-3, 2025 UTC - intervals on Nov 1 and Nov 2
        t = timeline(
            Interval(start=1761955200, end=1762041600),  # Nov 1, 2025 full day
            Interval(start=1762041600, end=1762128000),  # Nov 2, 2025 full day
        )
        result = total_duration(
            t, start=date(2025, 11, 1), end=date(2025, 11, 4), period="day"
        )
        assert len(result) == 3
        assert result[0] == (date(2025, 11, 1), 86400)
        assert result[1] == (date(2025, 11, 2), 86400)
        assert result[2] == (date(2025, 11, 3), 0)  # Empty day

    def test_daily_empty_periods_return_zero(self):
        """Empty days return 0 coverage."""
        t = timeline(Interval(start=1761955200, end=1762041600))  # Nov 1, 2025 only
        result = coverage_ratio(
            t, start=date(2025, 11, 1), end=date(2025, 11, 5), period="day"
        )
        assert len(result) == 4
        assert result[0][1] == 1.0  # Nov 1: full coverage
        assert result[1][1] == 0.0  # Nov 2: empty
        assert result[2][1] == 0.0  # Nov 3: empty
        assert result[3][1] == 0.0  # Nov 4: empty

    def test_daily_partial_day_intervals(self):
        """Intervals are clipped to day boundaries."""
        # Interval spans midnight Nov 1->Nov 2, 2025
        # Nov 1 22:00 UTC -> Nov 2 02:00 UTC
        t = timeline(
            Interval(start=1762034400, end=1762048800)
        )
        result = total_duration(
            t,
            start=date(2025, 11, 1),
            end=date(2025, 11, 3),
            period="day",
            tz="UTC",
        )
        assert len(result) == 2
        # Nov 1 gets 2 hours (22:00-24:00)
        assert result[0][1] == 7200
        # Nov 2 gets 2 hours (00:00-02:00)
        assert result[1][1] == 7200


class TestPeriodWeek:
    """Test period='week' aggregations (ISO weeks: Mon-Sun)."""

    def test_weekly_snaps_to_monday(self):
        """Weekly periods align to ISO week starts (Monday)."""
        # Nov 4, 2025 is a Tuesday
        # Should snap back to Nov 3 (Monday)
        t = timeline(Interval(start=1762214400, end=1762300800))  # Nov 4, 2025 full day
        result = total_duration(
            t,
            start=date(2025, 11, 4),  # Tuesday
            end=date(2025, 11, 11),  # Next Tuesday
            period="week",
            tz="UTC",
        )
        # Query from Nov 4-11 snaps to weeks:
        # - Week 1: Nov 3 (Mon) - Nov 9 (Sun) - contains Nov 4
        # - Week 2: Nov 10 (Mon) - Nov 16 (Sun) - contains Nov 10-11
        assert len(result) == 2
        assert result[0][0] == date(2025, 11, 3)  # First week starts Monday Nov 3
        assert result[0][1] == 86400  # One day of data (Nov 4)
        assert result[1][0] == date(2025, 11, 10)  # Second week starts Monday Nov 10
        assert result[1][1] == 0  # No data in second week


class TestPeriodMonth:
    """Test period='month' aggregations."""

    def test_monthly_snaps_to_first_of_month(self):
        """Monthly periods align to calendar months."""
        # Nov 15, 2025 - Dec 5, 2025
        t = timeline(
            Interval(start=1763164800, end=1763251200)  # Nov 15, 2025 full day
        )
        result = total_duration(
            t,
            start=date(2025, 11, 15),
            end=date(2025, 12, 5),
            period="month",
            tz="UTC",
        )
        # Should return Nov (starting Nov 1) and Dec (starting Dec 1)
        assert len(result) == 2
        assert result[0][0] == date(2025, 11, 1)
        assert result[1][0] == date(2025, 12, 1)

    def test_monthly_year_rollover(self):
        """Monthly periods handle year boundaries."""
        t = timeline(Interval(start=1767225600, end=1767312000))  # Jan 1, 2026
        result = total_duration(
            t,
            start=date(2025, 12, 15),
            end=date(2026, 1, 15),
            period="month",
            tz="UTC",
        )
        assert len(result) == 2
        assert result[0][0] == date(2025, 12, 1)
        assert result[1][0] == date(2026, 1, 1)


class TestPeriodYear:
    """Test period='year' aggregations."""

    def test_yearly_snaps_to_jan_1(self):
        """Yearly periods align to calendar years."""
        t = timeline(Interval(start=1735689600, end=1767225600))  # 2025 full year
        result = total_duration(
            t,
            start=date(2025, 6, 1),  # Mid-year start
            end=date(2026, 6, 1),
            period="year",
            tz="UTC",
        )
        assert len(result) == 2
        assert result[0][0] == date(2025, 1, 1)
        assert result[1][0] == date(2026, 1, 1)


class TestTimezoneHandling:
    """Test timezone-aware period boundaries."""

    def test_daily_different_timezone(self):
        """Daily periods respect specified timezone."""
        # Nov 1, 2025 in US/Pacific vs UTC
        pacific = ZoneInfo("US/Pacific")

        # Midnight Nov 1 Pacific = 8am Nov 1 UTC
        nov1_pacific_start = datetime(2025, 11, 1, 0, 0, tzinfo=pacific)
        nov1_utc_ts = int(nov1_pacific_start.timestamp())

        t = timeline(Interval(start=nov1_utc_ts, end=nov1_utc_ts + 3600))

        result = coverage_ratio(
            t,
            start=date(2025, 11, 1),
            end=date(2025, 11, 2),
            period="day",
            tz="US/Pacific",
        )
        assert len(result) == 1
        # Should have coverage since interval is during Nov 1 Pacific

    def test_dst_spring_forward(self):
        """Handle DST spring forward (23-hour day)."""
        # March 10, 2024 spring forward in US/Pacific (2am -> 3am)
        pacific = ZoneInfo("US/Pacific")

        # Create interval covering the full "day"
        march10_start = datetime(2024, 3, 10, 0, 0, tzinfo=pacific)
        march11_start = datetime(2024, 3, 11, 0, 0, tzinfo=pacific)

        # This day is only 23 hours in wall-clock time
        day_duration = int(march11_start.timestamp() - march10_start.timestamp())
        assert day_duration == 23 * 3600  # 23 hours, not 24

        t = timeline(
            Interval(
                start=int(march10_start.timestamp()),
                end=int(march11_start.timestamp()),
            )
        )

        result = total_duration(
            t,
            start=date(2024, 3, 10),
            end=date(2024, 3, 11),
            period="day",
            tz="US/Pacific",
        )
        assert len(result) == 1
        assert result[0][1] == 23 * 3600  # Covers the entire 23-hour day

    def test_dst_fall_back(self):
        """Handle DST fall back (25-hour day)."""
        # November 3, 2024 fall back in US/Pacific (2am -> 1am)
        pacific = ZoneInfo("US/Pacific")

        nov3_start = datetime(2024, 11, 3, 0, 0, tzinfo=pacific)
        nov4_start = datetime(2024, 11, 4, 0, 0, tzinfo=pacific)

        # This day is 25 hours in wall-clock time
        day_duration = int(nov4_start.timestamp() - nov3_start.timestamp())
        assert day_duration == 25 * 3600  # 25 hours

        t = timeline(
            Interval(
                start=int(nov3_start.timestamp()),
                end=int(nov4_start.timestamp()),
            )
        )

        result = total_duration(
            t,
            start=date(2024, 11, 3),
            end=date(2024, 11, 4),
            period="day",
            tz="US/Pacific",
        )
        assert len(result) == 1
        assert result[0][1] == 25 * 3600  # Covers the entire 25-hour day


class TestAllMetricsFunctions:
    """Test all metrics functions with period API."""

    def setup_method(self):
        """Create test timeline."""
        self.timeline = timeline(
            Interval(start=1000, end=2000),  # 1000s duration
            Interval(start=3000, end=3500),  # 500s duration
            Interval(start=5000, end=8000),  # 3000s duration
        )

    def test_total_duration_aggregates(self):
        """total_duration sums all interval durations."""
        result = total_duration(self.timeline, start=0, end=10000, period="full")
        assert len(result) == 1
        assert result[0][1] == 4500  # 1000 + 500 + 3000

    def test_count_intervals_counts(self):
        """count_intervals counts all overlapping intervals."""
        result = count_intervals(self.timeline, start=0, end=10000, period="full")
        assert len(result) == 1
        assert result[0][1] == 3

    def test_max_duration_finds_longest(self):
        """max_duration returns longest interval."""
        result = max_duration(self.timeline, start=0, end=10000, period="full")
        assert len(result) == 1
        assert result[0][1] == Interval(start=5000, end=8000)

    def test_min_duration_finds_shortest(self):
        """min_duration returns shortest interval."""
        result = min_duration(self.timeline, start=0, end=10000, period="full")
        assert len(result) == 1
        assert result[0][1] == Interval(start=3000, end=3500)

    def test_coverage_ratio_computes_fraction(self):
        """coverage_ratio computes fraction of window covered."""
        result = coverage_ratio(self.timeline, start=0, end=10000, period="full")
        assert len(result) == 1
        assert result[0][1] == pytest.approx(4500 / 10000)

    def test_empty_window_returns_none_or_zero(self):
        """Empty windows return appropriate null values."""
        empty_timeline = timeline()

        total = total_duration(empty_timeline, start=0, end=1000, period="full")
        assert total[0][1] == 0

        count = count_intervals(empty_timeline, start=0, end=1000, period="full")
        assert count[0][1] == 0

        max_dur = max_duration(empty_timeline, start=0, end=1000, period="full")
        assert max_dur[0][1] is None

        min_dur = min_duration(empty_timeline, start=0, end=1000, period="full")
        assert min_dur[0][1] is None

        coverage = coverage_ratio(empty_timeline, start=0, end=1000, period="full")
        assert coverage[0][1] == 0.0


class TestPerformance:
    """Test that materialization happens once."""

    def test_single_fetch_for_multiple_periods(self):
        """Timeline is fetched once even for many periods."""
        # This is hard to test directly without mocking,
        # but we can verify the behavior is correct
        t = timeline(
            Interval(start=1761955200, end=1762041600),  # Nov 1, 2025
            Interval(start=1762300800, end=1762387200),  # Nov 5, 2025
        )

        # Get coverage for 30 days
        result = coverage_ratio(
            t,
            start=date(2025, 11, 1),
            end=date(2025, 12, 1),
            period="day",
            tz="UTC",
        )

        # Should have 30 results
        assert len(result) == 30

        # Nov 1 and Nov 5 should have coverage, rest should be 0
        assert result[0][1] == 1.0  # Nov 1
        assert result[4][1] == 1.0  # Nov 5
        assert result[1][1] == 0.0  # Nov 2 (empty)
