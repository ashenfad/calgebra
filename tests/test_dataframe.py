"""Tests for to_dataframe() helper."""

from calgebra import Interval, to_dataframe
from calgebra.ical import ICalEvent


class TestToDataframe:
    """Tests for to_dataframe() function."""

    def test_basic_intervals(self):
        """Basic intervals produce day, time, duration columns."""
        intervals = [
            Interval(start=0, end=3600),  # 1 hour at epoch
            Interval(start=86400, end=90000),  # 1 hour next day
        ]
        df = to_dataframe(intervals, tz="UTC")

        assert list(df.columns) == ["day", "time", "duration"]
        assert len(df) == 2
        assert df["duration"].iloc[0] == "1h"

    def test_ical_events_have_calendar_name_first(self):
        """ICalEvent type puts calendar_name first."""
        events = [
            ICalEvent(
                start=0,
                end=3600,
                calendar_name="Test Cal",
                summary="Meeting",
            )
        ]
        df = to_dataframe(events, tz="UTC")

        # Calendar name should be first
        assert df.columns[0] == "calendar_name"
        assert df["calendar_name"].iloc[0] == "Test Cal"

    def test_empty_columns_dropped(self):
        """Columns with all None/empty values are dropped."""
        events = [
            ICalEvent(start=0, end=3600, summary="Test", location=None),
            ICalEvent(start=3600, end=7200, summary="Test2", location=""),
        ]
        df = to_dataframe(events, tz="UTC")

        # Location should be dropped (all empty)
        assert "location" not in df.columns

    def test_include_overrides_defaults(self):
        """include parameter overrides default columns."""
        events = [ICalEvent(start=0, end=3600, summary="Test", calendar_name="Cal")]
        df = to_dataframe(events, include=["summary", "duration"])

        assert list(df.columns) == ["summary", "duration"]

    def test_exclude_removes_columns(self):
        """exclude parameter removes columns from defaults."""
        intervals = [Interval(start=0, end=3600)]
        df = to_dataframe(intervals, exclude=["time"])

        assert "time" not in df.columns
        assert "day" in df.columns
        assert "duration" in df.columns

    def test_raw_mode_returns_datetime(self):
        """raw=True returns datetime objects instead of strings."""
        from datetime import datetime

        intervals = [Interval(start=0, end=3600)]
        df = to_dataframe(intervals, tz="UTC", raw=True)

        assert isinstance(df["day"].iloc[0], datetime)
        assert df["duration"].iloc[0] == 3600  # Seconds, not formatted

    def test_empty_input_returns_empty_dataframe(self):
        """Empty input returns empty DataFrame."""
        df = to_dataframe([])

        assert len(df) == 0

    def test_unbounded_intervals_included(self):
        """Unbounded intervals are included with placeholder values."""
        intervals = [Interval(start=None, end=3600)]
        df = to_dataframe(intervals, tz="UTC")

        assert len(df) == 1
        assert df["day"].iloc[0] == "—"
        assert df["duration"].iloc[0] == "—"

    def test_duration_formatting(self):
        """Duration formats correctly for various lengths."""
        intervals = [
            Interval(start=0, end=30),  # 30 seconds
            Interval(start=0, end=90),  # 1.5 minutes
            Interval(start=0, end=5400),  # 1.5 hours
            Interval(start=0, end=90000),  # 25 hours = 1d + 1h
        ]
        df = to_dataframe(intervals, tz="UTC")

        assert df["duration"].iloc[0] == "30s"
        assert df["duration"].iloc[1] == "1.5m"
        assert df["duration"].iloc[2] == "1.5h"
        assert df["duration"].iloc[3] == "1d"
