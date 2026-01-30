from datetime import datetime, timezone

from dateutil.rrule import SU

from calgebra import recurring
from calgebra.ical import file_to_timeline, timeline_to_file
from calgebra.recurrence import RecurringPattern

UTC = timezone.utc


def test_bysetpos_last_weekday():
    """Test using BYSETPOS to select the last weekday of the month."""
    # Pattern: Last weekday (Mon-Fri) of the month
    # RFC: FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1
    pattern = recurring(freq="monthly", day=["MO", "TU", "WE", "TH", "FR"], tz="UTC")
    # Manually inject advanced kwargs since recurring() helper doesn't expose them yet
    # but RecurringPattern supports them.
    # We can also instantiate RecurringPattern directly.
    pattern = RecurringPattern(
        freq="monthly", day=["MO", "TU", "WE", "TH", "FR"], bysetpos=-1, tz="UTC"
    )

    rrule_str = pattern.to_rrule_string()
    assert "FREQ=MONTHLY" in rrule_str
    assert "BYSETPOS=-1" in rrule_str
    assert "BYDAY=MO,TU,WE,TH,FR" in rrule_str

    # Verify logic (Jan 2025: Last weekday is Fri 31st)
    occurrences = list(
        pattern.fetch(
            start=int(datetime(2025, 1, 1, tzinfo=UTC).timestamp()),
            end=int(datetime(2025, 2, 1, tzinfo=UTC).timestamp()),
        )
    )

    assert len(occurrences) == 1
    dt = datetime.fromtimestamp(occurrences[0].start, tz=UTC)
    assert dt.date().isoformat() == "2025-01-31"  # Friday


def test_byyearday():
    """Test BYYEARDAY."""
    pattern = RecurringPattern(
        freq="yearly",
        byyearday=[1, 100],  # 1st and 100th day of year
        tz="UTC",
    )
    rrule_str = pattern.to_rrule_string()
    assert "BYYEARDAY=1,100" in rrule_str

    occurrences = list(
        pattern.fetch(
            start=int(datetime(2025, 1, 1, tzinfo=UTC).timestamp()),
            end=int(datetime(2026, 1, 1, tzinfo=UTC).timestamp()) - 1,
        )
    )
    assert len(occurrences) == 2
    # Jan 1
    assert datetime.fromtimestamp(occurrences[0].start, tz=UTC).day == 1
    # 100th day (April 10 for non-leap)
    dt_100 = datetime.fromtimestamp(occurrences[1].start, tz=UTC)
    assert dt_100.timetuple().tm_yday == 100


def test_ical_roundtrip_advanced(tmp_path):
    """Test that advanced RRULEs survive round-trip to/from .ics file."""
    fpath = tmp_path / "advanced.ics"

    pat = RecurringPattern(
        freq="monthly",
        day=["MO"],
        bysetpos=1,  # First Monday
        wkst="SU",
        tz="UTC",
        interval=2,  # Bi-monthly
    )

    from calgebra import timeline

    tl = timeline(pat)

    timeline_to_file(tl, fpath)

    loaded_tl = file_to_timeline(fpath)
    # Extract the pattern
    # It should be preserved as a symbolic pattern
    patterns = loaded_tl._recurring_patterns
    assert len(patterns) == 1

    loaded_pat = patterns[0][1]  # (key, pat)

    # Check args
    # Note: parsing might normalize types, but values should match
    assert loaded_pat.freq == "monthly"
    assert loaded_pat.interval == 2
    # bysetpos might be list [1] if sanitized
    if isinstance(loaded_pat.rrule_kwargs["bysetpos"], list):
        assert loaded_pat.rrule_kwargs["bysetpos"][0] == 1
    else:
        assert loaded_pat.rrule_kwargs["bysetpos"] == 1

    assert loaded_pat.rrule_kwargs["wkst"] == SU  # wkst is day object or int
