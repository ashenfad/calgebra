"""Tests for at_tz helper function."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from calgebra import at_tz


def test_at_tz_with_date_string():
    """Test creating datetime from date string (midnight in specified timezone)."""
    at = at_tz("US/Pacific")
    result = at("2024-01-01")

    expected = datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("US/Pacific"))
    assert result == expected
    assert result.tzinfo == ZoneInfo("US/Pacific")


def test_at_tz_with_datetime_string():
    """Test creating datetime from datetime string."""
    at = at_tz("US/Pacific")
    result = at("2024-01-01T15:30:00")

    expected = datetime(2024, 1, 1, 15, 30, 0, tzinfo=ZoneInfo("US/Pacific"))
    assert result == expected


def test_at_tz_with_datetime_string_with_seconds():
    """Test creating datetime from datetime string with seconds."""
    at = at_tz("US/Pacific")
    result = at("2024-01-01T15:30:45")

    expected = datetime(2024, 1, 1, 15, 30, 45, tzinfo=ZoneInfo("US/Pacific"))
    assert result == expected


def test_at_tz_with_year_month_day():
    """Test creating datetime from year, month, day components."""
    at = at_tz("US/Pacific")
    result = at(2024, 1, 1)

    expected = datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("US/Pacific"))
    assert result == expected


def test_at_tz_with_full_components():
    """Test creating datetime from full datetime components."""
    at = at_tz("US/Pacific")
    result = at(2024, 1, 1, 15, 30, 45)

    expected = datetime(2024, 1, 1, 15, 30, 45, tzinfo=ZoneInfo("US/Pacific"))
    assert result == expected


def test_at_tz_different_timezones():
    """Test that different factories create different timezone-aware datetimes."""
    pacific = at_tz("US/Pacific")
    eastern = at_tz("US/Eastern")

    pacific_dt = pacific("2024-01-01T12:00:00")
    eastern_dt = eastern("2024-01-01T12:00:00")

    # Same wall-clock time, different timezones
    assert pacific_dt.hour == eastern_dt.hour
    assert pacific_dt.tzinfo != eastern_dt.tzinfo

    # Different actual timestamps (3 hours apart)
    assert pacific_dt.timestamp() != eastern_dt.timestamp()


def test_at_tz_utc_timezone():
    """Test creating datetime in UTC timezone."""
    at = at_tz("UTC")
    result = at("2024-01-01T12:00:00")

    expected = datetime(2024, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert result == expected


def test_at_tz_rejects_string_with_timezone():
    """Test that strings with timezone info raise an error."""
    at = at_tz("US/Pacific")

    with pytest.raises(ValueError, match="already has timezone"):
        at("2024-01-01T12:00:00Z")

    with pytest.raises(ValueError, match="already has timezone"):
        at("2024-01-01T12:00:00+00:00")

    with pytest.raises(ValueError, match="already has timezone"):
        at("2024-01-01T12:00:00-05:00")


def test_at_tz_rejects_invalid_date_string():
    """Test that invalid date strings raise an error."""
    at = at_tz("US/Pacific")

    with pytest.raises(ValueError, match="Invalid date/datetime string"):
        at("not-a-date")

    with pytest.raises(ValueError, match="Invalid date/datetime string"):
        at("2024-13-01")  # Invalid month


def test_at_tz_rejects_invalid_arguments():
    """Test that invalid argument patterns raise an error."""
    at = at_tz("US/Pacific")

    with pytest.raises(TypeError, match="at\\(\\) accepts either"):
        at()  # No arguments

    with pytest.raises(TypeError, match="at\\(\\) accepts either"):
        at(12.5)  # Float instead of int or string

    with pytest.raises(TypeError, match="at\\(\\) accepts either"):
        at([2024, 1, 1])  # List instead of args


def test_at_tz_rejects_explicit_tzinfo_in_components():
    """Test that explicit tzinfo in component arguments raises an error."""
    at = at_tz("US/Pacific")

    with pytest.raises(TypeError, match="Cannot specify tzinfo"):
        at(2024, 1, 1, tzinfo=ZoneInfo("US/Eastern"))


def test_at_tz_invalid_timezone_name():
    """Test that invalid timezone names raise an error."""
    with pytest.raises(Exception):  # ZoneInfo raises different exceptions
        at_tz("Invalid/Timezone")


def test_at_tz_with_timeline_slicing():
    """Test using at_tz with timeline slicing."""
    from calgebra import Interval, timeline

    at = at_tz("US/Pacific")

    # Create a timeline
    tl = timeline(
        Interval(start=1704085200, end=1704171599),  # 2024-01-01 in Pacific
    )

    # Query using at_tz helper
    start = at("2024-01-01")
    end = at("2024-01-02")

    results = list(tl[start:end])
    assert len(results) == 1


def test_at_tz_cross_timezone_query():
    """Test querying with different timezones in same query."""
    from calgebra import Interval, timeline

    pacific = at_tz("US/Pacific")
    eastern = at_tz("US/Eastern")

    # Create timeline
    tl = timeline(
        Interval(start=1704067200, end=1735689599),  # 2024 in UTC
    )

    # Query with mixed timezones (should work since both convert to timestamps)
    results = list(tl[pacific("2024-01-01") : eastern("2024-12-31")])
    assert len(results) == 1


def test_at_tz_readme_example():
    """Test the pattern shown in documentation."""
    from calgebra import Interval, timeline

    at = at_tz("US/Pacific")

    # Create timeline
    tl = timeline(
        Interval(start=1704085200, end=1706759999),
    )

    # Use at() for ergonomic querying
    results = list(tl[at("2024-01-01") : at("2024-01-31")])
    assert len(results) == 1


def test_at_tz_preserves_dst_behavior():
    """Test that DST transitions are handled correctly by ZoneInfo."""
    at = at_tz("US/Pacific")

    # Before DST (PST = UTC-8)
    winter = at(2024, 1, 1, 12, 0, 0)
    assert winter.utcoffset().total_seconds() == -8 * 3600

    # After DST (PDT = UTC-7)
    summer = at(2024, 7, 1, 12, 0, 0)
    assert summer.utcoffset().total_seconds() == -7 * 3600
