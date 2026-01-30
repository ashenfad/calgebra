import pytest

from calgebra import Interval, pprint


def test_interval_format_basic() -> None:
    # 2025-01-01 12:00:00 UTC
    start = 1735732800
    # 2025-01-01 13:00:00 UTC
    end = 1735736400

    ivl = Interval(start=start, end=end)

    # Default is UTC
    formatted = ivl.format()
    assert formatted == "2025-01-01 12:00:00 -> 2025-01-01 13:00:00"


def test_interval_format_custom_tz() -> None:
    # 2025-01-01 12:00:00 UTC is 04:00:00 in US/Pacific (PST)
    start = 1735732800
    end = 1735736400
    ivl = Interval(start=start, end=end)

    formatted = ivl.format(tz="US/Pacific")
    assert formatted == "2025-01-01 04:00:00 -> 2025-01-01 05:00:00"


def test_interval_format_custom_fmt() -> None:
    start = 1735732800
    end = 1735736400
    ivl = Interval(start=start, end=end)

    formatted = ivl.format(fmt="%H:%M")
    assert formatted == "12:00 -> 13:00"


def test_interval_format_unbounded() -> None:
    ivl_start = Interval(start=1735732800, end=None)
    assert ivl_start.format().startswith("2025-01-01 12:00:00 -> +∞")

    ivl_end = Interval(start=None, end=1735736400)
    assert ivl_end.format().endswith("-> 2025-01-01 13:00:00")

    ivl_none = Interval(start=None, end=None)
    assert ivl_none.format() == "-∞ -> +∞"


def test_interval_str_representation() -> None:
    """Ensure __str__ remains the raw debug representation."""
    start = 1000
    end = 2000
    ivl = Interval(start=start, end=end)

    # Should show raw integers and duration
    s = str(ivl)
    assert "Interval(1000→2000, 1000s)" in s

    # Unbounded
    ivl_unbounded = Interval(start=None, end=None)
    assert "Interval(-∞→+∞, unbounded)" in str(ivl_unbounded)


def test_pprint(capsys: pytest.CaptureFixture[str]) -> None:
    ivls = [
        Interval(start=1735732800, end=1735736400),
        Interval(start=1735736400, end=1735740000),
    ]

    pprint(ivls, tz="UTC")

    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")

    assert len(lines) == 2
    assert lines[0] == "2025-01-01 12:00:00 -> 2025-01-01 13:00:00"
    assert lines[1] == "2025-01-01 13:00:00 -> 2025-01-01 14:00:00"
