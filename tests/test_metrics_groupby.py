"""Tests for the group_by parameter in metrics functions."""

from datetime import date

import pytest

from calgebra import Interval, timeline
from calgebra.metrics import count_intervals, coverage_ratio, total_duration


class TestGroupByValidation:
    """Test period/group_by validation."""

    def test_valid_hour_hour_of_day(self):
        t = timeline(Interval(start=0, end=3600))
        # Should not raise
        total_duration(t, 0, 86400, period="hour", group_by="hour_of_day")

    def test_valid_day_day_of_week(self):
        t = timeline(Interval(start=0, end=3600))
        # Should not raise
        total_duration(t, 0, 86400 * 7, period="day", group_by="day_of_week")

    def test_invalid_day_hour_of_day(self):
        """Can't extract hour from a day period."""
        t = timeline(Interval(start=0, end=3600))
        with pytest.raises(ValueError, match="Invalid group_by"):
            total_duration(t, 0, 86400, period="day", group_by="hour_of_day")

    def test_invalid_full_group_by(self):
        """group_by not valid with period='full'."""
        t = timeline(Interval(start=0, end=3600))
        with pytest.raises(ValueError, match="group_by requires period"):
            total_duration(t, 0, 86400, period="full", group_by="hour_of_day")


class TestTotalDurationGroupBy:
    """Test total_duration with group_by."""

    def test_hour_of_day_histogram(self):
        """Events at same hour across different days should aggregate."""
        # Jan 1 2025 9am-10am UTC and Jan 2 2025 9am-10am UTC
        t = timeline(
            Interval(start=1735722000, end=1735725600),  # 9am-10am day 1
            Interval(start=1735808400, end=1735812000),  # 9am-10am day 2
        )
        result = total_duration(
            t,
            date(2025, 1, 1),
            date(2025, 1, 3),
            period="hour",
            group_by="hour_of_day",
            tz="UTC",
        )
        result_dict = dict(result)
        # 2 hours at 9am (2 days × 1 hour)
        assert result_dict.get(9) == 7200

    def test_day_of_week_histogram(self):
        """Events on same weekday across weeks should aggregate."""
        # Two consecutive Wednesdays (Jan 1 2025 = Wednesday)
        t = timeline(
            Interval(start=1735689600, end=1735693200),  # Wed Jan 1 00:00-01:00
            Interval(start=1736294400, end=1736298000),  # Wed Jan 8 00:00-01:00
        )
        result = total_duration(
            t,
            date(2025, 1, 1),
            date(2025, 1, 15),
            period="day",
            group_by="day_of_week",
            tz="UTC",
        )
        result_dict = dict(result)
        # Wednesday = weekday 2, should have 2 hours total
        assert result_dict.get(2) == 7200

    def test_all_buckets_included_with_zeros(self):
        """All hour buckets should appear, even empty ones with zero value."""
        t = timeline(Interval(start=1735722000, end=1735725600))  # 9am-10am only
        result = total_duration(
            t,
            date(2025, 1, 1),
            date(2025, 1, 2),
            period="hour",
            group_by="hour_of_day",
            tz="UTC",
        )
        result_dict = dict(result)
        # All 24 hours should be present
        assert len(result_dict) == 24
        # Hour 9 has data
        assert result_dict.get(9) == 3600
        # Other hours are zero
        assert result_dict.get(8) == 0
        assert result_dict.get(10) == 0


class TestCountIntervalsGroupBy:
    """Test count_intervals with group_by."""

    def test_hour_of_day_count(self):
        """Count intervals per hour of day."""
        t = timeline(
            Interval(start=1735722000, end=1735722100),  # 9am event day 1
            Interval(start=1735808400, end=1735808500),  # 9am event day 2
            Interval(start=1735725600, end=1735725700),  # 10am event day 1
        )
        result = count_intervals(
            t,
            date(2025, 1, 1),
            date(2025, 1, 3),
            period="hour",
            group_by="hour_of_day",
            tz="UTC",
        )
        result_dict = dict(result)
        assert result_dict.get(9) == 2  # Two 9am events
        assert result_dict.get(10) == 1  # One 10am event


class TestCoverageRatioGroupBy:
    """Test coverage_ratio with group_by."""

    def test_hour_of_day_coverage(self):
        """Coverage ratio should sum numerator and denominator correctly."""
        # 100% coverage at 9am on day 1, 50% coverage at 9am on day 2
        t = timeline(
            Interval(start=1735722000, end=1735725600),  # 9am-10am (100%) day 1
            Interval(start=1735808400, end=1735810200),  # 9am-9:30am (50%) day 2
        )
        result = coverage_ratio(
            t,
            date(2025, 1, 1),
            date(2025, 1, 3),
            period="hour",
            group_by="hour_of_day",
            tz="UTC",
        )
        result_dict = dict(result)
        # 9am bucket: (3600 + 1800) / (3600 + 3600) = 5400/7200 = 0.75
        assert result_dict.get(9) == pytest.approx(0.75)


class TestGroupByDayOfMonth:
    """Test day_of_month grouping."""

    def test_day_of_month_histogram(self):
        """Events on same day of month across months should aggregate."""
        # 1st of Jan and 1st of Feb (both day_of_month=1)
        t = timeline(
            Interval(start=1735689600, end=1735693200),  # Jan 1 00:00-01:00
            Interval(start=1738368000, end=1738371600),  # Feb 1 00:00-01:00
        )
        result = total_duration(
            t,
            date(2025, 1, 1),
            date(2025, 2, 15),
            period="day",
            group_by="day_of_month",
            tz="UTC",
        )
        result_dict = dict(result)
        assert result_dict.get(1) == 7200  # 2 hours on day 1
