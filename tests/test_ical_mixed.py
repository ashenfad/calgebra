from dateutil.rrule import MO, TU

from calgebra.ical import file_to_timeline


def test_mixed_recurrence(tmp_path):
    # Test "1MO,2TU" (first Monday AND second Tuesday) parsing
    # This proves that we can handle mixed weeks, which was previously impossible.
    ics_content = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//calgebra//
BEGIN:VEVENT
UID:recur_mixed
DTSTART:20250106T090000Z
RRULE:FREQ=MONTHLY;BYDAY=1MO,2TU
SUMMARY:Mixed Recurrence
END:VEVENT
END:VCALENDAR"""

    p = tmp_path / "mixed.ics"
    p.write_bytes(ics_content)

    t = file_to_timeline(p)
    assert len(t._recurring_patterns) == 1

    _, pattern = t._recurring_patterns[0]

    # Check parsing
    assert pattern.freq == "monthly"
    assert pattern.week is None
    assert len(pattern.day) == 2

    # Verify exact structure
    # Verify exact structure in rrule_kwargs
    byweekday = pattern.rrule_kwargs["byweekday"]

    # Order might vary depending on parsing, but set should match
    days = {(d.weekday, d.n) for d in byweekday}
    expected = {(MO.weekday, 1), (TU.weekday, 2)}
    assert days == expected

    # Check strings in .day
    day_strs = set(pattern.day)
    # icalendar/dateutil might normalize strings differently?
    # ical.py uses str(vWeekday).
    # expected strings: "1MO", "2TU"
    assert "1MO" in day_strs
    assert "2TU" in day_strs
