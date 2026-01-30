from calgebra.ical import file_to_timeline, timeline_to_file


def test_numbered_weekdays(tmp_path):
    # Test "1MO" (first Monday) parsing
    ics_content = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//calgebra//
BEGIN:VEVENT
UID:recur1
DTSTART:20250106T090000Z
RRULE:FREQ=MONTHLY;BYDAY=1MO
SUMMARY:Monthly Team Meeting
END:VEVENT
END:VCALENDAR"""

    p = tmp_path / "recur.ics"
    p.write_bytes(ics_content)

    t = file_to_timeline(p)
    assert len(t._recurring_patterns) == 1

    from dateutil.rrule import MO

    _, pattern = t._recurring_patterns[0]
    # Check that it correctly parsed the numbered day
    assert pattern.freq == "monthly"
    assert pattern.week is None
    # pattern.day should be strings now (passed from ical)
    assert pattern.day == ["1MO"]

    # Check internal parsing
    wd = pattern.rrule_kwargs["byweekday"][0]
    assert wd.weekday == MO.weekday
    assert wd.n == 1

    # Round trip check
    out = tmp_path / "recur_out.ics"
    timeline_to_file(t, out)

    # Read back
    with open(out, "r") as f:
        content = f.read()

    # Verify RRULE string in output
    assert "FREQ=MONTHLY" in content
    # Order of params in RRULE might vary but BYDAY=1MO should remain
    # OR it might be reconstructed. RecurringPattern.to_rrule_string()
    # uses dateutil logic which outputs "BYDAY=1MO".
    assert "BYDAY=1MO" in content
