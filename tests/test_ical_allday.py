from calgebra.ical import file_to_timeline, timeline_to_file


def test_all_day_event(tmp_path):
    # Create ICS with all-day event
    ics_content = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//calgebra//
BEGIN:VEVENT
UID:allday1
DTSTART;VALUE=DATE:20250101
DTEND;VALUE=DATE:20250102
SUMMARY:New Years Day
END:VEVENT
END:VCALENDAR"""

    p = tmp_path / "allday.ics"
    p.write_bytes(ics_content)

    # Load
    t = file_to_timeline(p)
    assert len(t._static_intervals) == 1
    ev = t._static_intervals[0]

    assert ev.is_all_day
    assert ev.summary == "New Years Day"

    # Save back
    out = tmp_path / "allday_out.ics"
    timeline_to_file(t, out)

    # Read output content to verify VALUE=DATE
    _ = out.read_bytes()
    # icalendar library might format it differently, but should have VALUE=DATE
    # or just be date. Actually, icalendar usually serializes date objects as
    # plain dates if type is correct.
    # Let's check via parsing again.

    t2 = file_to_timeline(out)
    ev2 = t2._static_intervals[0]
    assert ev2.is_all_day
    assert ev2.summary == "New Years Day"

    # Check duration (should be 1 day = 86400s)
    assert ev2.end - ev2.start == 86400
